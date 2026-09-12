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

    @discord.ui.button(label="Meets & Polls", style=discord.ButtonStyle.primary, emoji="📅", custom_id="hub_meets", row=0)
    async def meets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed(
                "📅 Meets & Polls",
                (
                    "**Meets (staff)**\n`/meet` — announce a car meet + reminders\n\n"
                    "**Polls (staff)**\n`/poll` `/poll_end` `/poll_list`\n"
                    "Or use the **web panel → Polls** tab."
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
                    "`/welcome_config` `/welcome_test`\n"
                    "`/autorole_panel` `/autofeed_add`\n"
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

    @app_commands.command(name="commands_panel", description="Post the category command hub (buttons)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def commands_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◈ BOVA COMMAND HUB",
            description=(
                "Pick a **category**. Each button shows the easy options for that area.\n"
                "Members rarely need raw `/` commands — use these guides + specialty panels "
                "(tickets, birthdays, autorole)."
            ),
            color=discord.Color.from_rgb(180, 80, 255),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Bova's Bot · Category panels")
        await interaction.channel.send(embed=embed, view=CategoryHub(self.bot))
        await interaction.response.send_message("✅ Command hub posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandPanels(bot))
