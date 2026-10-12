"""
Anti-spam honeypot channel.

Any message posted in the monitored channel triggers an immediate
native Discord timeout (7 days). Immune: bots, owner, crew-leader role,
and users with Administrator permission.

Slash commands (LOCKED — Lider / owner only):
  /antispam         Post the public warning embed in the honeypot channel
  /antispam_toggle  Enable or disable monitoring
  /antispam_status  Health check (channel, permissions, current state)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.antispam")

FILE = "antispam.json"
DEFAULT_HONEYPOT_CHANNEL_ID = 1559213282638827590
TIMEOUT_DAYS = 7
OWNER_USER_ID = 921803925051572266


class AntiSpam(commands.Cog):
    """Honeypot channel: any message → 7-day native timeout."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._state = load_json(FILE, {"enabled": True})
        if "enabled" not in self._state:
            self._state["enabled"] = True
            save_json(FILE, self._state)

    # ── config helpers ────────────────────────────────────────────────────────

    def _honeypot_id(self) -> int:
        return int(
            self.bot.config.get("ANTISPAM_CHANNEL_ID") or DEFAULT_HONEYPOT_CHANNEL_ID
        )

    def _immune_role_id(self) -> int:
        return int(
            self.bot.config.get("CREW_LEADER_ROLE_ID") or 1384173136177791048
        )

    def _weblogs_channel_id(self) -> Optional[int]:
        return self.bot.config.get("WEBLOGS_CHANNEL_ID")

    @property
    def enabled(self) -> bool:
        return bool(self._state.get("enabled", True))

    def _set_enabled(self, value: bool) -> None:
        self._state["enabled"] = bool(value)
        save_json(FILE, self._state)

    def _is_immune(self, member: discord.Member) -> bool:
        if member.bot:
            return True
        if int(member.id) == OWNER_USER_ID:
            return True
        if member.guild_permissions.administrator:
            return True
        immune_role = self._immune_role_id()
        if immune_role and any(r.id == immune_role for r in member.roles):
            return True
        return False

    # ── listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.enabled:
            return
        if not message.guild or not message.author:
            return
        if message.channel.id != self._honeypot_id():
            return
        if not isinstance(message.author, discord.Member):
            return
        if self._is_immune(message.author):
            return

        member = message.author
        guild = message.guild
        content_preview = (message.content or "").strip()
        if len(content_preview) > 900:
            content_preview = content_preview[:900] + "…"
        if not content_preview:
            atts = []
            for a in message.attachments:
                atts.append(a.filename or a.url or "attachment")
            content_preview = f"[media/attachment] {', '.join(atts)}" if atts else "[empty message]"

        # Capture IDs before any await that might fail
        msg_id = message.id
        channel = message.channel

        # 1) Apply timeout immediately
        timeout_until = datetime.now(timezone.utc) + timedelta(days=TIMEOUT_DAYS)
        reason = f"Anti-spam honeypot — message in #{getattr(channel, 'name', 'anti-spam')}"
        timed_out = False
        timeout_error: Optional[str] = None
        try:
            me = guild.me
            if me is None or not me.guild_permissions.moderate_members:
                timeout_error = "Bot lacks Moderate Members permission"
                logger.error(timeout_error)
            elif member.top_role >= me.top_role and guild.owner_id != me.id:
                timeout_error = "Target role hierarchy is higher than or equal to the bot"
                logger.error("%s (member=%s)", timeout_error, member.id)
            else:
                await member.timeout(timeout_until, reason=reason)
                timed_out = True
        except discord.Forbidden:
            timeout_error = "Forbidden (hierarchy or missing permission)"
            logger.exception("Timeout forbidden for %s", member.id)
        except discord.HTTPException as e:
            timeout_error = f"HTTP error: {e}"
            logger.exception("Timeout HTTP error for %s", member.id)
        except Exception as e:
            timeout_error = str(e)
            logger.exception("Timeout failed for %s", member.id)

        # 2) Delete the triggering message (best-effort)
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        except Exception:
            logger.exception("Failed to delete honeypot message %s", msg_id)

        # 3) Public embed in the honeypot channel
        try:
            public = make_embed(
                title="🚫 Automatic timeout applied",
                description=(
                    f"**Member:** {member.mention} (`{member.id}`)\n"
                    f"**Action:** Native Discord timeout — **{TIMEOUT_DAYS} days**\n"
                    f"**Reason:** Message posted in the monitored anti-spam channel"
                ),
                color=discord.Color.dark_red(),
            )
            public.set_thumbnail(url=member.display_avatar.url)
            public.add_field(
                name="Message content",
                value=f"```{content_preview[:1000]}```" if content_preview else "*no text*",
                inline=False,
            )
            public.add_field(
                name="Timeout until",
                value=f"<t:{int(timeout_until.timestamp())}:F> (<t:{int(timeout_until.timestamp())}:R>)",
                inline=False,
            )
            if not timed_out:
                public.add_field(
                    name="⚠️ Timeout status",
                    value=f"Failed: `{timeout_error or 'unknown'}`",
                    inline=False,
                )
            await channel.send(embed=public)
        except Exception:
            logger.exception("Failed to post public honeypot embed")

        # 4) Detailed staff log in WebLogs channel
        try:
            await self._send_staff_log(
                member=member,
                content_preview=content_preview,
                timed_out=timed_out,
                timeout_until=timeout_until,
                timeout_error=timeout_error,
                message_id=msg_id,
            )
        except Exception:
            logger.exception("Failed to send antispam staff log")

    async def _send_staff_log(
        self,
        *,
        member: discord.Member,
        content_preview: str,
        timed_out: bool,
        timeout_until: datetime,
        timeout_error: Optional[str],
        message_id: int,
    ) -> None:
        ch_id = self._weblogs_channel_id()
        channel = safe_get_channel(self.bot, ch_id) if ch_id else None
        if channel is None and ch_id:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception:
                channel = None
        if channel is None:
            logger.warning("Antispam staff log skipped — WEBLOGS_CHANNEL_ID unavailable")
            return

        created = member.created_at
        joined = member.joined_at
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        roles_text = ", ".join(roles[:25]) if roles else "*none*"
        if len(roles) > 25:
            roles_text += f" (+{len(roles) - 25} more)"

        status = (
            f"✅ Timeout applied until <t:{int(timeout_until.timestamp())}:F>"
            if timed_out
            else f"❌ Timeout **failed**: `{timeout_error or 'unknown'}`"
        )

        embed = make_embed(
            title="🛡️ Anti-spam honeypot — member timed out",
            description=(
                f"**Member:** {member.mention} · `{member}` · `{member.id}`\n"
                f"**Channel:** <#{self._honeypot_id()}>\n"
                f"**Message ID:** `{message_id}`\n"
                f"**Status:** {status}"
            ),
            color=discord.Color.dark_red() if timed_out else discord.Color.orange(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Message content",
            value=f"```{content_preview[:1000]}```",
            inline=False,
        )
        embed.add_field(
            name="Account created",
            value=f"<t:{int(created.timestamp())}:F> (<t:{int(created.timestamp())}:R>)",
            inline=True,
        )
        if joined:
            embed.add_field(
                name="Joined server",
                value=f"<t:{int(joined.timestamp())}:F> (<t:{int(joined.timestamp())}:R>)",
                inline=True,
            )
        embed.add_field(
            name="Roles",
            value=roles_text[:1024],
            inline=False,
        )
        embed.add_field(
            name="Account flags",
            value=(
                f"Bot: `{member.bot}` · System: `{member.system}` · "
                f"Pending: `{getattr(member, 'pending', False)}` · "
                f"Timeout already active: `{member.is_timed_out()}`"
            ),
            inline=False,
        )
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("Could not send antispam embed to weblogs channel")

    # ── slash commands (LOCKED via bot.py special_denied) ─────────────────────

    @app_commands.command(
        name="antispam",
        description="[LOCKED] Post the public warning embed in the anti-spam honeypot channel",
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def antispam_warning(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch_id = self._honeypot_id()
        channel = safe_get_channel(self.bot, ch_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception:
                channel = None
        if channel is None:
            await interaction.followup.send(
                f"❌ Honeypot channel `{ch_id}` not found.",
                ephemeral=True,
            )
            return

        embed = make_embed(
            title="⚠️ Monitored channel",
            description=(
                "This channel is monitored by **AutoMod / Bova's Bot**.\n\n"
                "**Any message here results in an automatic timeout.**\n"
                "Do not type, post links, images, or videos.\n\n"
                "If you are not staff, leave this channel immediately."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name="Penalty",
            value=f"Native Discord timeout — **{TIMEOUT_DAYS} days**",
            inline=False,
        )
        try:
            await channel.send(embed=embed)
            await interaction.followup.send(
                f"✅ Warning embed posted in <#{ch_id}>.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "🚫 I cannot send messages in the honeypot channel.",
                ephemeral=True,
            )
        except Exception as e:
            logger.exception("antispam warning post failed")
            await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)

    @app_commands.command(
        name="antispam_toggle",
        description="[LOCKED] Enable or disable anti-spam honeypot monitoring",
    )
    @app_commands.describe(state="Turn monitoring on or off")
    @app_commands.choices(
        state=[
            app_commands.Choice(name="Enable", value="on"),
            app_commands.Choice(name="Disable", value="off"),
        ]
    )
    @app_commands.checks.cooldown(1, 5.0)
    async def antispam_toggle(
        self,
        interaction: discord.Interaction,
        state: app_commands.Choice[str],
    ):
        enabled = state.value == "on"
        self._set_enabled(enabled)
        label = "ENABLED" if enabled else "DISABLED"
        color = discord.Color.green() if enabled else discord.Color.orange()
        embed = make_embed(
            title=f"Anti-spam monitoring {label}",
            description=(
                f"**Channel:** <#{self._honeypot_id()}>\n"
                f"**State:** `{label}`\n"
                f"**Changed by:** {interaction.user.mention}"
            ),
            color=color,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Also log to weblogs
        try:
            wl = self.bot.get_cog("WebLogs")
            if wl and hasattr(wl, "log_admin"):
                await wl.log_admin(
                    f"🛡️ Anti-spam {label}",
                    f"{interaction.user.mention} set honeypot monitoring to **{label}**.",
                    color,
                )
        except Exception:
            logger.exception("Failed to log antispam_toggle")

    @app_commands.command(
        name="antispam_status",
        description="[LOCKED] Check anti-spam honeypot status and bot permissions",
    )
    @app_commands.checks.cooldown(1, 5.0)
    async def antispam_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        ch_id = self._honeypot_id()
        channel = safe_get_channel(self.bot, ch_id) if guild else None
        if channel is None and guild:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception:
                channel = None

        me = guild.me if guild else None
        lines = [
            f"**Monitoring:** `{'ENABLED' if self.enabled else 'DISABLED'}`",
            f"**Honeypot channel:** <#{ch_id}> (`{ch_id}`)",
            f"**Channel found:** `{'yes' if channel else 'NO'}`",
            f"**Timeout duration:** `{TIMEOUT_DAYS} days`",
            f"**Immune role:** `{self._immune_role_id()}`",
            f"**Owner immune ID:** `{OWNER_USER_ID}`",
        ]

        if me and channel and isinstance(channel, discord.abc.GuildChannel):
            perms = channel.permissions_for(me)
            lines.append(
                f"**Bot perms in channel:** "
                f"send=`{perms.send_messages}` embed=`{perms.embed_links}` "
                f"manage_messages=`{perms.manage_messages}`"
            )
            lines.append(
                f"**Moderate Members (guild):** `{me.guild_permissions.moderate_members}`"
            )
        elif me:
            lines.append(
                f"**Moderate Members (guild):** `{me.guild_permissions.moderate_members}`"
            )

        weblogs_id = self._weblogs_channel_id()
        wl_ch = safe_get_channel(self.bot, weblogs_id) if weblogs_id else None
        lines.append(
            f"**WebLogs channel:** `{weblogs_id}` found=`{'yes' if wl_ch else 'NO'}`"
        )

        # Quick permission verdict
        ok = (
            self.enabled
            and channel is not None
            and me is not None
            and me.guild_permissions.moderate_members
        )
        if channel and me and isinstance(channel, discord.abc.GuildChannel):
            p = channel.permissions_for(me)
            ok = ok and p.send_messages and p.manage_messages

        verdict = "✅ Ready" if ok else "⚠️ Check permissions / channel / toggle"
        embed = make_embed(
            title=f"Anti-spam status — {verdict}",
            description="\n".join(lines),
            color=discord.Color.green() if ok else discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpam(bot))
