"""
Tickets / Suggestions / Report — easy panel with modals.
Public panel channel ≠ private logging channel.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.tickets")
CONFIG_FILE = "tickets.json"

# Defaults for Bovary Club Society
DEFAULT_PANEL_CHANNEL = 1548175948036186172  # 📚┃tickets-suggestions
DEFAULT_LOG_CHANNEL = 1548176739946074112    # 📚┃ticket-logging

TYPES = {
    "ticket": {"label": "Ticket", "emoji": "🎫", "color": 0xB450FF, "title": "🎫 Support Ticket"},
    "suggestion": {"label": "Suggestions", "emoji": "💡", "color": 0x00DCAF, "title": "💡 Suggestion"},
    "report": {"label": "Report", "emoji": "🚩", "color": 0xFF4060, "title": "🚩 Report"},
}


class SubmissionModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", kind: str):
        meta = TYPES[kind]
        super().__init__(title=meta["label"][:45])
        self.cog = cog
        self.kind = kind
        self.subject = discord.ui.TextInput(
            label="Subject / Assunto",
            placeholder="Short title…",
            max_length=120,
            required=True,
        )
        self.body = discord.ui.TextInput(
            label="Details / Detalhes",
            style=discord.TextStyle.paragraph,
            placeholder="Write everything here. Only staff will see this.",
            max_length=1800,
            required=True,
        )
        self.add_item(self.subject)
        self.add_item(self.body)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.submit_entry(
            interaction,
            kind=self.kind,
            subject=str(self.subject.value).strip(),
            body=str(self.body.value).strip(),
        )


class EasyTicketPanel(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="easy_ticket", row=0)
    async def ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SubmissionModal(self.cog, "ticket"))

    @discord.ui.button(label="Suggestions", style=discord.ButtonStyle.success, emoji="💡", custom_id="easy_suggestion", row=0)
    async def suggestion_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SubmissionModal(self.cog, "suggestion"))

    @discord.ui.button(label="Report", style=discord.ButtonStyle.danger, emoji="🚩", custom_id="easy_report", row=0)
    async def report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SubmissionModal(self.cog, "report"))


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Dict[str, Any] = load_json(CONFIG_FILE, {
            "panel_channel_id": DEFAULT_PANEL_CHANNEL,
            "log_channel_id": DEFAULT_LOG_CHANNEL,
            "panel_title": "Support · Suggestions · Reports",
            "panel_description": (
                "Choose a button below. A private form will open — "
                "**other members will not see** what you write.\n"
                "Staff reads submissions in the logging channel."
            ),
            "entries": [],  # registry for web panel
        })
        # migrate old keys if needed
        if "entries" not in self.config:
            self.config["entries"] = []
        if not self.config.get("log_channel_id"):
            self.config["log_channel_id"] = DEFAULT_LOG_CHANNEL
        if not self.config.get("panel_channel_id"):
            self.config["panel_channel_id"] = DEFAULT_PANEL_CHANNEL
        try:
            self.bot.add_view(EasyTicketPanel(self))
        except Exception:
            pass

    def _save(self):
        # keep last 500 entries
        entries = self.config.get("entries") or []
        if len(entries) > 500:
            self.config["entries"] = entries[-500:]
        save_json(CONFIG_FILE, self.config)

    def _log_channel(self) -> Optional[discord.abc.GuildChannel]:
        cid = self.config.get("log_channel_id") or DEFAULT_LOG_CHANNEL
        return safe_get_channel(self.bot, int(cid)) if cid else None

    async def submit_entry(
        self,
        interaction: discord.Interaction,
        *,
        kind: str,
        subject: str,
        body: str,
    ):
        meta = TYPES.get(kind) or TYPES["ticket"]
        entry = {
            "id": int(datetime.now(timezone.utc).timestamp() * 1000) % 10_000_000_000,
            "kind": kind,
            "subject": subject,
            "body": body,
            "user_id": interaction.user.id,
            "user_tag": str(interaction.user),
            "channel_id": interaction.channel_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "open",
        }
        self.config.setdefault("entries", []).append(entry)
        self._save()

        log_ch = self._log_channel()
        embed = discord.Embed(
            title=meta["title"],
            description=body[:4000],
            color=meta["color"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Subject", value=subject[:256], inline=False)
        embed.add_field(name="Type", value=meta["label"], inline=True)
        embed.add_field(name="From", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
        embed.add_field(name="Entry ID", value=f"`{entry['id']}`", inline=True)
        if interaction.user.display_avatar:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Bova's Bot · Private submission · members cannot see this channel content from the panel")

        if log_ch and isinstance(log_ch, discord.TextChannel):
            try:
                msg = await log_ch.send(embed=embed)
                entry["log_message_id"] = msg.id
                self._save()
            except Exception:
                logger.exception("Failed to post to ticket log channel")
                await interaction.response.send_message(
                    "❌ Could not reach the staff log channel. Tell an admin.",
                    ephemeral=True,
                )
                return
        else:
            await interaction.response.send_message(
                "❌ Log channel not found. Admin must set `/ticket_setup`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Your **{meta['label']}** was sent to staff privately.\n"
            f"Entry ID: `{entry['id']}` — they will follow up if needed.",
            ephemeral=True,
        )

    @app_commands.command(name="ticket_panel", description="Post the easy Ticket / Suggestions / Report panel")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_panel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Text channel only.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"📚 {self.config.get('panel_title', 'Support')}",
            description=self.config.get("panel_description"),
            color=discord.Color.from_rgb(180, 80, 255),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="How it works",
            value=(
                "🎫 **Ticket** — help / support\n"
                "💡 **Suggestions** — ideas for the club\n"
                "🚩 **Report** — report an issue or member\n\n"
                "A form opens in Discord. **Only staff** see the content in the logging channel."
            ),
            inline=False,
        )
        embed.set_footer(text="Bova's Bot · Easy panel")
        await ch.send(embed=embed, view=EasyTicketPanel(self))
        self.config["panel_channel_id"] = ch.id
        self._save()
        await interaction.response.send_message(f"✅ Panel posted in {ch.mention}", ephemeral=True)

    @app_commands.command(name="ticket_setup", description="Set panel/log channels for easy tickets")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        panel_channel: Optional[discord.TextChannel] = None,
        log_channel: Optional[discord.TextChannel] = None,
    ):
        if panel_channel:
            self.config["panel_channel_id"] = panel_channel.id
        if log_channel:
            self.config["log_channel_id"] = log_channel.id
        # ensure defaults
        self.config.setdefault("panel_channel_id", DEFAULT_PANEL_CHANNEL)
        self.config.setdefault("log_channel_id", DEFAULT_LOG_CHANNEL)
        self._save()
        await interaction.response.send_message(
            f"✅ Panel ch: `{self.config.get('panel_channel_id')}` · "
            f"Log ch: `{self.config.get('log_channel_id')}`",
            ephemeral=True,
        )

    @app_commands.command(name="ticket_list", description="[STAFF] List recent submissions")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_list(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 30] = 15):
        entries = list(reversed(self.config.get("entries") or []))[:limit]
        if not entries:
            await interaction.response.send_message("No submissions yet.", ephemeral=True)
            return
        lines = []
        for e in entries:
            lines.append(
                f"`{e.get('id')}` · **{e.get('kind')}** · {e.get('subject', '')[:40]} · <@{e.get('user_id')}>"
            )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    def get_entries_for_api(self, limit: int = 50) -> List[Dict]:
        return list(reversed(self.config.get("entries") or []))[:limit]


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
