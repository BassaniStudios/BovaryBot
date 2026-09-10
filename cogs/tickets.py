"""Ticket / support system (Ticket Tool inspired, simplified)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.tickets")
CONFIG_FILE = "tickets.json"


class TicketPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket_open_btn", emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = self.bot.get_cog("Tickets")
        if cog:
            await cog.create_ticket(interaction)


class TicketControls(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = self.bot.get_cog("Tickets")
        if cog:
            await cog.close_ticket(interaction)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.secondary, custom_id="ticket_claim_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = self.bot.get_cog("Tickets")
        if cog:
            await cog.claim_ticket(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Dict[str, Any] = load_json(CONFIG_FILE, {
            "category_id": None,
            "staff_role_id": None,
            "log_channel_id": None,
            "panel_title": "Support Tickets",
            "panel_description": "Click the button below to open a support ticket.",
            "open_message": "Thanks for opening a ticket. Staff will help you soon.",
            "tickets": {},
        })
        try:
            self.bot.add_view(TicketPanelView(bot))
            self.bot.add_view(TicketControls(bot))
        except Exception:
            logger.exception("Failed to register ticket views")

    def _save(self):
        save_json(CONFIG_FILE, self.config)

    async def create_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return
        # prevent duplicates
        for tid, data in self.config.get("tickets", {}).items():
            if data.get("user_id") == interaction.user.id and data.get("status") == "open":
                ch = guild.get_channel(int(tid))
                if ch:
                    await interaction.response.send_message(
                        f"You already have an open ticket: {ch.mention}", ephemeral=True
                    )
                    return

        category = None
        cat_id = self.config.get("category_id")
        if cat_id:
            category = guild.get_channel(cat_id)

        staff_role_id = self.config.get("staff_role_id")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if staff_role_id:
            role = guild.get_role(staff_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        name = f"ticket-{interaction.user.name}"[:90]
        try:
            channel = await guild.create_text_channel(
                name=name,
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                reason=f"Ticket by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I cannot create channels. Check my permissions.", ephemeral=True
            )
            return

        self.config.setdefault("tickets", {})[str(channel.id)] = {
            "user_id": interaction.user.id,
            "status": "open",
            "claimed_by": None,
            "created": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

        embed = make_embed(
            title="🎫 Ticket opened",
            description=self.config.get("open_message", "Staff will help you soon."),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="User", value=interaction.user.mention)
        mention = f"<@&{staff_role_id}>" if staff_role_id else ""
        await channel.send(
            content=f"{interaction.user.mention} {mention}",
            embed=embed,
            view=TicketControls(self.bot),
        )
        await interaction.response.send_message(
            f"✅ Ticket created: {channel.mention}", ephemeral=True
        )

    async def close_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        data = self.config.get("tickets", {}).get(str(channel.id))
        if not data:
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
            return
        data["status"] = "closed"
        self._save()
        await interaction.response.send_message("🔒 Ticket closed. Channel will be deleted in 5 seconds.")
        try:
            await channel.send("Ticket closed.")
            await channel.delete(reason=f"Closed by {interaction.user}")
        except Exception:
            logger.exception("Ticket close/delete failed")

    async def claim_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        data = self.config.get("tickets", {}).get(str(channel.id))
        if not data:
            await interaction.response.send_message("Not a ticket.", ephemeral=True)
            return
        data["claimed_by"] = interaction.user.id
        self._save()
        await interaction.response.send_message(f"✋ Ticket claimed by {interaction.user.mention}")

    @app_commands.command(name="ticket_panel", description="Post the ticket panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        embed = make_embed(
            title=self.config.get("panel_title", "Support Tickets"),
            description=self.config.get("panel_description", "Click to open a ticket."),
            color=discord.Color.blurple(),
        )
        await interaction.channel.send(embed=embed, view=TicketPanelView(self.bot))
        await interaction.response.send_message("✅ Panel posted.", ephemeral=True)

    @app_commands.command(name="ticket_config", description="Configure ticket system")
    @app_commands.describe(
        category="Category for new tickets",
        staff_role="Staff role that can see tickets",
        log_channel="Optional log channel",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_config(
        self,
        interaction: discord.Interaction,
        category: Optional[discord.CategoryChannel] = None,
        staff_role: Optional[discord.Role] = None,
        log_channel: Optional[discord.TextChannel] = None,
    ):
        if category:
            self.config["category_id"] = category.id
        if staff_role:
            self.config["staff_role_id"] = staff_role.id
        if log_channel:
            self.config["log_channel_id"] = log_channel.id
        self._save()
        await interaction.response.send_message("✅ Ticket config saved.", ephemeral=True)

    @app_commands.command(name="ticket_close", description="Close the current ticket")
    async def ticket_close_cmd(self, interaction: discord.Interaction):
        await self.close_ticket(interaction)

    @app_commands.command(name="ticket_add", description="Add a user to this ticket")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.channel.set_permissions(
            member, view_channel=True, send_messages=True, read_message_history=True
        )
        await interaction.response.send_message(f"Added {member.mention} to the ticket.")

    @app_commands.command(name="ticket_remove", description="Remove a user from this ticket")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"Removed {member.mention} from the ticket.")

    @app_commands.command(name="ticket_rename", description="Rename this ticket channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_rename(self, interaction: discord.Interaction, name: str):
        await interaction.channel.edit(name=name[:90])
        await interaction.response.send_message(f"Renamed to `{name[:90]}`.", ephemeral=True)

    @app_commands.command(name="ticket_transcript", description="Export last messages as a transcript file")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_transcript(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        lines = []
        async for msg in interaction.channel.history(limit=1000, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{ts}] {msg.author}: {msg.content}")
        content = "\n".join(lines) or "(empty)"
        path = f"/tmp/transcript-{interaction.channel.id}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        await interaction.followup.send(
            file=discord.File(path, filename=f"transcript-{interaction.channel.id}.txt"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
