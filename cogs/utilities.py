"""Utilities cog: ping, info, timestamp, help panel, web panel link."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import SERVER_TZ, tz_from_offset

logger = logging.getLogger("bovary_bot.utilities")

VISIBILITY_CHOICES = [
    app_commands.Choice(name="Only you", value="private"),
    app_commands.Choice(name="Post in channel", value="channel"),
]

def is_public(visibility: str) -> bool:
    return visibility == "channel"

CYBER_PURPLE = discord.Color.from_rgb(180, 80, 255)
CYBER_CYAN = discord.Color.from_rgb(0, 220, 255)
CYBER_PINK = discord.Color.from_rgb(255, 60, 160)
CYBER_GREEN = discord.Color.from_rgb(0, 255, 170)
CYBER_RED = discord.Color.from_rgb(255, 40, 80)

# Official Bova GIF (hosted on ImageKit)
BOVA_GIF_URL = "https://ik.imagekit.io/BassaniStudios/bova.gif?updatedAt=1789321996082"


def cyber_embed(title: str, description: str = "", color: discord.Color = CYBER_PURPLE) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="BOVA CORE · Bova's Bot · SYSTEM ONLINE")
    return embed


def _main_embed() -> discord.Embed:
    return cyber_embed(
        title="◈ BOVA CORE — CONTROL PANEL",
        description=(
            "```ansi\n"
            "\u001b[0;35m╔══════════════════════════════════╗\n"
            "\u001b[0;35m║   BOVA'S BOT  ·  SYSTEM ONLINE  ║\n"
            "\u001b[0;35m╚══════════════════════════════════╝\n"
            "\u001b[0;36m> SYSTEM READY · ENGINES ONLINE\n"
            "\u001b[0;37m> Select a module to continue\n"
            "```"
        ),
    )


class MainPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot, *, timeout: Optional[float] = 300):
        super().__init__(timeout=timeout)
        self.bot = bot

    @discord.ui.button(label="◈ MODERATION", style=discord.ButtonStyle.danger, row=0)
    async def mod_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ MODERATION LAYER",
            description="Silent actions · Logged results · Staff only",
            color=CYBER_RED,
        )
        embed.add_field(
            name="▸ Commands",
            value="`/delete` — Delete message by ID\n`/purge` — Purge 1–100 messages",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ UTILITIES", style=discord.ButtonStyle.success, row=0)
    async def util_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ UTILITIES",
            description="Latency · Info · Timestamps",
            color=CYBER_GREEN,
        )
        embed.add_field(name="▸ Commands", value="`/ping` `/info` `/timestamp`", inline=False)
        await interaction.response.edit_message(embed=embed, view=UtilPanel(self.bot))

    @discord.ui.button(label="◈ INVITES", style=discord.ButtonStyle.primary, row=0)
    async def inv_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ ACCESS SYSTEM",
            description="Invite request panel with persistent cooldown",
            color=CYBER_CYAN,
        )
        embed.add_field(name="▸ Commands", value="`/invitepanel`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ REMINDERS", style=discord.ButtonStyle.secondary, row=1)
    async def reminders_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ TIMESTAMP REMINDERS",
            description="Detects `<t:UNIX:R>` in messages and embeds and reminds the same channel before the event.",
            color=CYBER_CYAN,
        )
        embed.add_field(name="▸ Commands", value="`/timestamp_reminder_config` `/timestamp_reminder_status`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ MEETS", style=discord.ButtonStyle.secondary, row=2)
    async def meet_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ CAR MEETS",
            description="Announce meets with timezone-aware timestamps and ~30-min reminder.",
            color=CYBER_PINK,
        )
        embed.add_field(name="▸ Commands", value="`/meet`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ STATS", style=discord.ButtonStyle.secondary, row=2)
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ STATISTICS",
            description="Activity tracking · Top chatters · Peak hours (SP) · Top media",
            color=CYBER_CYAN,
        )
        embed.add_field(name="▸ Commands", value="`/stats` `/topmedia`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ TICKETS", style=discord.ButtonStyle.secondary, row=3)
    async def tickets_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ TICKETS",
            description="Support tickets with claim, close, transcript and staff logs.",
            color=CYBER_PURPLE,
        )
        embed.add_field(
            name="▸ Commands",
            value="`/ticket_panel` `/ticket_setup` `/ticket_list`",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ WEBLOGS", style=discord.ButtonStyle.secondary, row=4)
    async def wl_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ WEBLOGS",
            description=(
                "Structured logs with toggles.\n"
                "Joins/leaves → Info channel\n"
                "Admin actions → bot-room\n"
                "Message delete/edit → message log"
            ),
            color=CYBER_CYAN,
        )
        embed.add_field(name="▸ Commands", value="`/weblogs_config`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ WEB PANEL", style=discord.ButtonStyle.secondary, row=4)
    async def web_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ WEB PANEL",
            description="Full external dashboard. Use `/panel` (staff role required) to get the panel link. The access key is entered privately on the web panel.",
            color=CYBER_PINK,
        )
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))


class BackOnly(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="◀ BACK", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainPanelView(self.bot))


class UtilPanel(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="▸ Run /ping", style=discord.ButtonStyle.success, row=0)
    async def do_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        latency = round(self.bot.latency * 1000)
        embed = cyber_embed(
            title="◈ PONG",
            description=f"```ansi\n\u001b[0;32m> LATENCY: {latency}ms\n```",
            color=CYBER_GREEN,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀ BACK", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainPanelView(self.bot))


class Utilities(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Show bot latency")
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def ping(self, interaction: discord.Interaction, visibility: str = "private"):
        latency = round(self.bot.latency * 1000)
        embed = cyber_embed(
            title="◈ PONG",
            description=f"```ansi\n\u001b[0;32m> LATENCY: {latency}ms\n```",
            color=CYBER_GREEN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=not is_public(visibility))

    @app_commands.command(name="info", description="Bot, server and user information")
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def info(self, interaction: discord.Interaction, visibility: str = "private"):
        bot_user = interaction.client.user
        server = interaction.guild
        user = interaction.user
        embed = cyber_embed(title="◈ SYSTEM INFO", color=CYBER_CYAN)
        if bot_user and bot_user.avatar:
            embed.set_thumbnail(url=bot_user.avatar.url)
        embed.add_field(
            name="▸ Bot",
            value=(
                f"**Name:** {bot_user.name if bot_user else 'Bova\'s Bot'}\n"
                f"**ID:** `{bot_user.id if bot_user else 'N/A'}`\n"
                f"**Latency:** `{round(self.bot.latency * 1000)}ms`"
            ),
            inline=False,
        )
        if server:
            embed.add_field(
                name="▸ Server",
                value=f"**Name:** {server.name}\n**ID:** `{server.id}`\n**Members:** `{server.member_count}`",
                inline=False,
            )
        embed.add_field(
            name="▸ User",
            value=f"**Name:** {user.display_name}\n**ID:** `{user.id}`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=not is_public(visibility))

    @app_commands.command(name="timestamp", description="Generate a Discord timestamp")
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    @app_commands.describe(
        date_time="DD/MM/YYYY HH:MM or DD/MM/YYYY. Empty = now.",
        timezone_offset="UTC offset hours (default -3 = São Paulo)",
        visibility="How the result should be shown",
    )
    async def timestamp(
        self,
        interaction: discord.Interaction,
        date_time: Optional[str] = None,
        timezone_offset: float = -3.0,
        visibility: str = "private",
    ):
        try:
            tz = tz_from_offset(timezone_offset)
            if not date_time or not date_time.strip():
                dt = datetime.now(tz)
            else:
                date_time = date_time.strip()
                for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
                    try:
                        dt = datetime.strptime(date_time, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    await interaction.response.send_message(
                        "❌ Invalid format. Use `DD/MM/YYYY HH:MM` or `DD/MM/YYYY`.",
                        ephemeral=not is_public(visibility),
                    )
                    return
                dt = dt.replace(tzinfo=tz)
            unix = int(dt.timestamp())
            embed = cyber_embed(title="◈ TIMESTAMP", color=CYBER_CYAN)
            embed.add_field(name=f"▸ Local (UTC{timezone_offset:+g})", value=f"`{dt.strftime('%d/%m/%Y %H:%M:%S')}`", inline=False)
            embed.add_field(name="▸ Unix", value=f"`{unix}`", inline=True)
            embed.add_field(
                name="▸ Discord formats",
                value=(
                    f"`<t:{unix}:F>` → <t:{unix}:F>\n"
                    f"`<t:{unix}:f>` → <t:{unix}:f>\n"
                    f"`<t:{unix}:D>` → <t:{unix}:D>\n"
                    f"`<t:{unix}:t>` → <t:{unix}:t>\n"
                    f"`<t:{unix}:R>` → <t:{unix}:R>"
                ),
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=not is_public(visibility))
        except Exception as e:
            logger.exception("timestamp error")
            await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=not is_public(visibility))

    @app_commands.command(name="help", description="Bova's Bot cyberpunk control panel")
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def help_command(self, interaction: discord.Interaction, visibility: str = "private"):
        await interaction.response.send_message(
            embed=_main_embed(),
            view=MainPanelView(self.bot),
            ephemeral=not is_public(visibility),
        )

    @app_commands.command(name="panel", description="[LOCKED] Get the web panel link")
    async def panel(self, interaction: discord.Interaction):
        role_id = self.bot.config.get("PANEL_ACCESS_ROLE_ID")
        panel_url = self.bot.config.get("PANEL_URL") or "https://bovaryclub.github.io/BovaryBot-Panel/"
        if not role_id:
            await interaction.response.send_message(
                "❌ Panel access role not configured (`PANEL_ACCESS_ROLE_ID`).",
                ephemeral=True,
            )
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Guild only.", ephemeral=True)
            return
        api_role = self.bot.config.get("STAFF_API_ROLE_ID")
        has_role = any(r.id == role_id for r in member.roles)
        has_api_role = api_role and any(r.id == api_role for r in member.roles)
        is_admin = member.guild_permissions.administrator
        if not has_role and not has_api_role and not is_admin:
            embed = cyber_embed(
                title="◈ ACCESS DENIED",
                description="```ansi\n\u001b[0;31m> ACCESS DENIED\n```",
                color=CYBER_RED,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = cyber_embed(
            title="◈ WEB PANEL — ACCESS GRANTED",
            description=(
                f"**Link:** {panel_url}\n\n"
                "▸ Enter the panel access key on the panel login screen. It is intentionally not displayed here.\n"
                "▸ Sidebar modules: Dashboard · Embed · Meets · Timestamp\n"
                "▸ Tickets · WebLogs · Stats · Commands · Audit Tools\n"
                "▸ Keep link and key private\n"
                "▸ API: set Render URL in panel config.js (BOVA_API.baseUrl)"
            ),
            color=CYBER_GREEN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="avatar", description="Show user avatar")
    @app_commands.describe(user="User (optional)")
    async def avatar(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        u = user or interaction.user
        embed = cyber_embed(title=f"Avatar — {u.display_name}", color=CYBER_CYAN)
        embed.set_image(url=u.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="servericon", description="Show server icon")
    async def servericon(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g or not g.icon:
            await interaction.response.send_message("No server icon.", ephemeral=True)
            return
        embed = cyber_embed(title=f"Icon — {g.name}", color=CYBER_CYAN)
        embed.set_image(url=g.icon.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="membercount", description="Server member count")
    async def membercount(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        humans = sum(1 for m in g.members if not m.bot)
        bots = sum(1 for m in g.members if m.bot)
        embed = cyber_embed(
            title="◈ MEMBER COUNT",
            description=f"**Total:** {g.member_count}\n**Humans:** {humans}\n**Bots:** {bots}",
            color=CYBER_GREEN,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Detailed user info")
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    @app_commands.describe(user="User (optional)", visibility="How the result should be shown")
    async def userinfo(self, interaction: discord.Interaction, user: Optional[discord.Member] = None, visibility: str = "private"):
        # Defer immediately so Discord never shows "application did not respond"
        await interaction.response.defer(ephemeral=not is_public(visibility))
        try:
            m = user or interaction.user
            if interaction.guild and not isinstance(m, discord.Member):
                try:
                    m = await interaction.guild.fetch_member(m.id)
                except Exception:
                    m = None
            if not isinstance(m, discord.Member):
                await interaction.followup.send("Guild only / member not found.", ephemeral=True)
                return
            roles = [r.mention for r in m.roles[1:]][:15]
            embed = cyber_embed(title=f"User — {m}", color=CYBER_PURPLE)
            embed.set_thumbnail(url=m.display_avatar.url)
            embed.add_field(name="ID", value=f"`{m.id}`", inline=True)
            embed.add_field(
                name="Joined",
                value=f"<t:{int(m.joined_at.timestamp())}:R>" if m.joined_at else "?",
                inline=True,
            )
            embed.add_field(
                name="Created",
                value=f"<t:{int(m.created_at.timestamp())}:R>",
                inline=True,
            )
            embed.add_field(name="Roles", value=" ".join(roles) if roles else "—", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=not is_public(visibility))
        except Exception as e:
            logger.exception("userinfo failed")
            try:
                await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)
            except Exception:
                pass

    @app_commands.command(name="serverinfo", description="Server information")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        await interaction.response.defer()
        humans = sum(1 for m in g.members if not m.bot)
        bots = sum(1 for m in g.members if m.bot)
        text_c = len(g.text_channels)
        voice_c = len(g.voice_channels)
        cats = len(g.categories)
        boosts = g.premium_subscription_count or 0
        tier = g.premium_tier
        # Role breakdown (top by member count, skip @everyone)
        role_lines = []
        roles_sorted = sorted(
            [r for r in g.roles if r.name != "@everyone"],
            key=lambda r: len(r.members),
            reverse=True,
        )
        for r in roles_sorted[:15]:
            role_lines.append(f"• {r.mention} — **{len(r.members)}**")
        embed = cyber_embed(title=f"◈ SERVER — {g.name}", color=CYBER_CYAN)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        if g.banner:
            embed.set_image(url=g.banner.url)
        embed.add_field(name="🆔 ID", value=f"`{g.id}`", inline=True)
        embed.add_field(name="👑 Owner", value=g.owner.mention if g.owner else "?", inline=True)
        embed.add_field(
            name="📅 Created",
            value=f"<t:{int(g.created_at.timestamp())}:F>\n(<t:{int(g.created_at.timestamp())}:R>)",
            inline=False,
        )
        embed.add_field(
            name="👥 Members",
            value=f"**{g.member_count}** total\n👤 {humans} humans · 🤖 {bots} bots",
            inline=True,
        )
        embed.add_field(
            name="📂 Channels",
            value=f"💬 {text_c} text · 🔊 {voice_c} voice\n📁 {cats} categories · Σ {len(g.channels)}",
            inline=True,
        )
        embed.add_field(
            name="🏷️ Roles",
            value=f"**{len(g.roles)}** roles (incl. @everyone)",
            inline=True,
        )
        embed.add_field(
            name="💎 Boosts",
            value=f"Level **{tier}** · **{boosts}** boosts",
            inline=True,
        )
        embed.add_field(
            name="😀 Emojis / Stickers",
            value=f"{len(g.emojis)} emojis · {len(g.stickers)} stickers",
            inline=True,
        )
        if role_lines:
            embed.add_field(
                name="📊 Top roles by members",
                value="\n".join(role_lines)[:1020],
                inline=False,
            )
        embed.set_footer(text="Bova's Bot · Server analytics")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="say", description="[LOCKED] Make the bot say something")
    @app_commands.describe(message="Message to send", channel="Channel (optional)")
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        # Allow TextChannel, VoiceChannel (text chat), StageChannel and Thread
        # so /say works when used inside a voice channel's text chat
        ch = channel or interaction.channel
        if not isinstance(
            ch,
            (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread),
        ):
            await interaction.response.send_message("Invalid channel.", ephemeral=True)
            return
        await ch.send(message[:2000])
        await interaction.response.send_message("✅ Sent.", ephemeral=True)

    @app_commands.command(
        name="sayfile",
        description="[LOCKED] Make the bot send an image or video file (no embed), like /say",
    )
    @app_commands.describe(
        file="Image or video to send as the bot",
        channel="Channel (optional)",
        caption="Optional text caption above the file",
    )
    async def sayfile(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        channel: Optional[discord.TextChannel] = None,
        caption: Optional[str] = None,
    ):
        # Allow TextChannel, VoiceChannel (text chat), StageChannel and Thread
        # so /sayfile works when used inside a voice channel's text chat
        ch = channel or interaction.channel
        if not isinstance(
            ch,
            (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread),
        ):
            await interaction.response.send_message("Invalid channel.", ephemeral=True)
            return

        # Basic type check – allow image/* and video/*
        ct = (file.content_type or "").lower()
        name = (file.filename or "").lower()
        allowed_ext = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm", ".mkv", ".gifv")
        is_media = ct.startswith(("image/", "video/")) or name.endswith(allowed_ext)
        if not is_media:
            await interaction.response.send_message(
                "Please send only an image or video (png/jpg/gif/webp/mp4/mov/webm…).",
                ephemeral=True,
            )
            return

        # Size soft limit (Discord attachment limit is already enforced by Discord)
        if file.size and file.size > 25 * 1024 * 1024:
            await interaction.response.send_message("File too large (max ~25 MB).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            data = await file.read()
            discord_file = discord.File(
                fp=__import__("io").BytesIO(data),
                filename=file.filename or "media.bin",
            )
            content = (caption or "")[:2000] or None
            await ch.send(content=content, file=discord_file)
            await interaction.followup.send("✅ File sent as the bot (no embed).", ephemeral=True)
        except Exception as e:
            logger.exception("sayfile failed")
            await interaction.followup.send(f"Failed to send: {e}", ephemeral=True)

    @app_commands.command(
        name="bumpy",
        description="Disboard bump reminder (full site automation is not reliably possible)",
    )
    async def bumpy(self, interaction: discord.Interaction):
        """Disboard requires the official Disboard bot /bump command (or the website button while logged in).
        Third-party bots cannot invoke other bots' slash commands or click the site button without
        browser automation + login (fragile, heavy, and against ToS). This command only guides the user.
        """
        embed = cyber_embed(
            title="◈ Disboard Bump",
            description=(
                "**Full automation of the Disboard /bump button is not possible** "
                "in a stable and allowed way from this bot.\n\n"
                "What you can do now:\n"
                "1. In Discord, use the **`/bump`** command from the official **Disboard** bot "
                "(it must be in the server).\n"
                "2. Or open [disboard.org](https://disboard.org) while logged in and click **Bump** on your server.\n\n"
                "Typical Disboard cooldown: **2 hours** between bumps.\n"
                "If an official API or allowed method becomes available, we can integrate it properly."
            ),
            color=CYBER_CYAN,
        )
        embed.set_footer(text="Bova's Bot · /bumpy")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utilities(bot))
