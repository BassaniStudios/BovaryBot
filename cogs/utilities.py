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

    @discord.ui.button(label="◈ MEETS", style=discord.ButtonStyle.secondary, row=1)
    async def meet_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ CAR MEETS",
            description="Announce meets with timezone-aware timestamps and ~30-min reminder.",
            color=CYBER_PINK,
        )
        embed.add_field(name="▸ Commands", value="`/meet`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ STATS", style=discord.ButtonStyle.secondary, row=1)
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ STATISTICS",
            description="Activity tracking · Top chatters · Peak hours (SP) · Top media",
            color=CYBER_CYAN,
        )
        embed.add_field(name="▸ Commands", value="`/stats` `/topmedia`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ TICKETS", style=discord.ButtonStyle.secondary, row=2)
    async def tickets_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ TICKETS",
            description="Support tickets with claim, close, transcript and staff logs.",
            color=CYBER_PURPLE,
        )
        embed.add_field(
            name="▸ Commands",
            value=(
                "`/ticket_panel` `/ticket_config` `/ticket_close`\n"
                "`/ticket_add` `/ticket_remove` `/ticket_rename` `/ticket_transcript`"
            ),
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ AUTO FEEDS", style=discord.ButtonStyle.secondary, row=2)
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

    @discord.ui.button(label="◈ BOOST", style=discord.ButtonStyle.secondary, row=2)
    async def boost_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ BOOST",
            description="Thank-you embeds when someone boosts the server.",
            color=CYBER_PINK,
        )
        embed.add_field(name="▸ Commands", value="`/boost_config`", inline=False)
        await interaction.response.edit_message(embed=embed, view=BackOnly(self.bot))

    @discord.ui.button(label="◈ WEBLOGS", style=discord.ButtonStyle.secondary, row=3)
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

    @discord.ui.button(label="◈ WEB PANEL", style=discord.ButtonStyle.secondary, row=3)
    async def web_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = cyber_embed(
            title="◈ WEB PANEL",
            description="Full external dashboard. Use `/panel` (staff role required) to get the link + access key.",
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
        access_key = self.bot.config.get("PANEL_ACCESS_KEY") or "BOVA-CORE-2026"
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
                f"**Access key:** `{access_key}`\n\n"
                "▸ Sidebar modules: Dashboard · Auto-Role · Embed · Meets · Timestamp\n"
                "▸ Auto Feeds · Tickets · Boost · WebLogs · Stats · Commands\n"
                "▸ Keep link and key private\n"
                "▸ API: set Render URL in panel config.js (BOVA_API.baseUrl)"
            ),
            color=CYBER_GREEN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utilities(bot))
