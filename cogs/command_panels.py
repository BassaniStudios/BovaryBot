"""
Painéis por categoria — botões no Discord em vez de decorar /slash.
Os botões abrem instruções rápidas ou disparam fluxos já existentes (ephemeral).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("bovary_bot.command_panels")


def _embed(title: str, body: str, color: int = 0xB450FF) -> discord.Embed:
    e = discord.Embed(
        title=title,
        description=body,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    e.set_footer(text="Bova's Bot · Command panels")
    return e


class CategoryHub(discord.ui.View):
    """Main hub: pick a category panel."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Utils", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="hub_utils", row=0)
    async def utils(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed(
                "🛠️ Utilities",
                (
                    "Slash shortcuts (type `/` and pick):\n"
                    "`/ping` `/info` `/help` `/timestamp`\n"
                    "`/avatar` `/servericon` `/membercount`\n"
                    "`/userinfo` `/serverinfo` `/say` *(staff)*\n\n"
                    "Tip: `/serverinfo` shows roles, boosts, creation date."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Meets", style=discord.ButtonStyle.primary, emoji="📅", custom_id="hub_meets", row=0)
    async def meets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed(
                "📅 Meets",
                (
                    "**Meets (staff)**\n`/meet` — announce a car meet + reminders\n\n"
                    "**Nitro Raffles (staff)**\n`/nitroraffles` `/nitroraffles_result` `/nitroraffles_reset` `/nitroraffles_test`"
                ),
                0x00DCAF,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Tickets", style=discord.ButtonStyle.success, emoji="🎫", custom_id="hub_tickets", row=0)
    async def tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed(
                "🎫 Tickets / Suggestions / Report",
                (
                    "Use the **panel in** `📚┃tickets-suggestions`:\n"
                    "🎫 Ticket · 💡 Suggestions · 🚩 Report\n\n"
                    "A form opens — **only staff** see it in `📚┃ticket-logging`.\n"
                    "Staff: `/ticket_panel` `/ticket_list` `/ticket_setup`"
                ),
                0x50B4FF,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Birthdays", style=discord.ButtonStyle.secondary, emoji="🎂", custom_id="hub_bday", row=1)
    async def bday(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed(
                "🎂 Birthdays",
                (
                    "Use the **birthday panel** buttons (no typing dates):\n"
                    "Birthdays · Register · Edit mine · Zodiac\n\n"
                    "Staff posts it with `/birthday_panel`."
                ),
                0xFF78B4,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="hub_stats", row=1)
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed(
                "📊 Stats",
                "`/stats` — activity overview\n`/topmedia` — top media by reactions\n`/namehistory` — nick history",
                0xFFAA40,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Staff tools", style=discord.ButtonStyle.danger, emoji="🔐", custom_id="hub_staff", row=1)
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not (
            member.guild_permissions.manage_messages or member.guild_permissions.administrator
        ):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_embed(
                "🔐 Staff tools",
                (
                    "`/panel` — web panel link + key\n"
                    "`/memberlog_test` — sample join/leave/kick/ban embeds\n"
                    "`/delete` `/purge`\n"
                    "`/backup_now` `/db_status`\n"
                    "`/sticky_set` `/cmd_add`\n"
                    "`/week_summary` — last 7 days activity snapshot"
                ),
                0xFF4060,
            ),
            ephemeral=True,
        )


class CommandPanels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        try:
            self.bot.add_view(CategoryHub(bot))
        except Exception:
            pass

    @app_commands.command(name="commands_panel", description="[LOCKED] Post the detailed Bova command hub")
    async def commands_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◈ BOVA COMMAND HUB · OPERATIONS",
            description=(
                "A central map of the bot's current systems.\n\n"
                "🔐 **Slash access:** restricted by the bot's staff-role policy.\n"
                "👁️ **Result visibility:** supported report commands can use **Somente você** or **Publicar no canal**.\n"
                "🎫 **Member panels:** Invite requests, Tickets/Suggestions/Reports, Birthdays and arcade panels continue to work through buttons and modals.\n"
                "🛡️ **Background systems:** logging, AutoMod monitoring, timestamp reminders, statistics and activity tracking run independently of slash access."
            ),
            color=discord.Color.from_rgb(180, 80, 255),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="🛠️ Core & Utilities",
            value="`/ping` `/info` `/timestamp` `/help` `/panel` `/avatar` `/servericon` `/membercount` `/userinfo` `/serverinfo` `/say` `/sayfile`",
            inline=False,
        )
        embed.add_field(
            name="📅 Community Operations",
            value="`/invitepanel` · `/meet` · `/nitroraffles` · `/ticket_panel` `/ticket_setup` `/ticket_list` · birthdays",
            inline=False,
        )
        embed.add_field(
            name="📊 Logs & Statistics",
            value="`/stats` `/topmedia` `/week_summary` `/weblogs_config` `/msglog_test` `/memberlog_test` `/namehistory` `/namehistory_export`",
            inline=False,
        )
        embed.add_field(
            name="🕵️ Advanced Audit",
            value="`/member_activity` `/member_invites` `/automod_activity` `/chat_ranking` `/media_ranking` `/role_diff` `/permission_audit` `/mass_action_alert` `/msg_stats` `/log_health` `/guild_snapshot` `/investigate` `/who_deleted` `/peak_hours`",
            inline=False,
        )
        embed.add_field(
            name="🔮 Special Systems",
            value="Nazar Speaks · Love Professor · Timestamp Reminders · Custom Commands · Sticky Messages · Backup/Database",
            inline=False,
        )
        embed.add_field(
            name="🚫 Removed from the current command set",
            value="Auto-Role · Welcome DM · `/boost_config` · AutoFeeds · `/bovasay` · `/member_time` · `/bova` (all removed)",
            inline=False,
        )
        embed.set_footer(text="Bova's Bot · Operations Hub")
        await interaction.channel.send(embed=embed, view=CategoryHub(self.bot))
        await interaction.response.send_message("✅ Detailed command hub posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandPanels(bot))
