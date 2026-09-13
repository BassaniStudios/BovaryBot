"""Utilities cog: ping, info, timestamp, help panel, web panel link."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import SERVER_TZ, tz_from_offset

logger = logging.getLogger("bovary_bot.utilities")

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

    @discord.ui.button(label="◈ AUTO-ROLE", style=discord.ButtonStyle.secondary, row=1)
    async def ar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ AUTO-ROLE",
            description="Button roles — add multiple roles via slash or web panel.",
            color=CYBER_PURPLE,
        )
        embed.add_field(
            name="▸ Commands",
            value="`/autorole_panel` `/autorole_add` `/autorole_remove` `/autorole_list` `/autorole_config`",
            inline=False,
        )
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

    @discord.ui.button(label="◈ AUTO FEEDS", style=discord.ButtonStyle.secondary, row=3)
    async def af_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ AUTO FEEDS",
            description="Scheduled messages — interval or fixed daily time · plain or embed.",
            color=CYBER_GREEN,
        )
        embed.add_field(
            name="▸ Commands",
            value="`/autofeed_add` `/autofeed_list` `/autofeed_remove` `/autofeed_toggle`",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ BOOST", style=discord.ButtonStyle.secondary, row=4)
    async def boost_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ BOOST",
            description="Thank-you embeds when someone boosts the server.",
            color=CYBER_PINK,
        )
        embed.add_field(name="▸ Commands", value="`/boost_config`", inline=False)
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
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        embed = cyber_embed(
            title="◈ PONG",
            description=f"```ansi\n\u001b[0;32m> LATENCY: {latency}ms\n```",
            color=CYBER_GREEN,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="info", description="Bot, server and user information")
    async def info(self, interaction: discord.Interaction):
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
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="timestamp", description="Generate a Discord timestamp")
    @app_commands.describe(
        date_time="DD/MM/YYYY HH:MM or DD/MM/YYYY. Empty = now.",
        timezone_offset="UTC offset hours (default -3 = São Paulo)",
    )
    async def timestamp(
        self,
        interaction: discord.Interaction,
        date_time: Optional[str] = None,
        timezone_offset: float = -3.0,
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
                        ephemeral=True,
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
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.exception("timestamp error")
            await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)

    @app_commands.command(name="help", description="Bova's Bot cyberpunk control panel")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=_main_embed(),
            view=MainPanelView(self.bot),
            ephemeral=True,
        )

    @app_commands.command(name="panel", description="[STAFF] Get the web panel link (role-restricted)")
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
                "▸ Sidebar modules: Dashboard · Auto-Role · Embed · Meets · Timestamp\n"
                "▸ Auto Feeds · Tickets · Boost · WebLogs · Stats · Commands\n"
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
    @app_commands.describe(user="User (optional)")
    async def userinfo(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        # Defer immediately so Discord never shows "application did not respond"
        await interaction.response.defer()
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
            await interaction.followup.send(embed=embed)
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

    @app_commands.command(name="say", description="[STAFF] Make the bot say something")
    @app_commands.describe(message="Message to send", channel="Channel (optional)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Invalid channel.", ephemeral=True)
            return
        await ch.send(message[:2000])
        await interaction.response.send_message("✅ Sent.", ephemeral=True)

    @app_commands.command(name="bova", description="[STAFF] Post the official Bova's Bot GIF")
    @app_commands.describe(channel="Channel (optional)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def bova(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Canal inválido.", ephemeral=True)
            return

        embed = discord.Embed(color=CYBER_CYAN)
        embed.set_image(url=BOVA_GIF_URL)
        embed.set_footer(text="Bova's Bot")
        await ch.send(embed=embed)
        await interaction.response.send_message("✅ GIF enviado.", ephemeral=True)

    @app_commands.command(name="bovasay", description="[STAFF] Post text + official Bova's Bot GIF")
    @app_commands.describe(
        message="Text to send with the GIF",
        channel="Channel (optional)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def bovasay(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Canal inválido.", ephemeral=True)
            return

        embed = discord.Embed(
            description=message[:4096],
            color=CYBER_CYAN,
        )
        embed.set_image(url=BOVA_GIF_URL)
        embed.set_footer(text="Bova's Bot")
        await ch.send(embed=embed)
        await interaction.response.send_message("✅ Mensagem + GIF enviados.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utilities(bot))
