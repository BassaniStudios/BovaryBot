"""
Cog do sistema de convites.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.cooldown import CooldownManager

logger = logging.getLogger("bovary_bot.invite")


class InviteView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Request Invite ✉️",
        style=discord.ButtonStyle.blurple,
        custom_id="invite_request_button",
    )
    async def request_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Lida com pedido de convite do botão persistente."""
        user = interaction.user
        now = datetime.now(timezone.utc)
        cooldown_seconds = self.bot.config.get("INVITE_COOLDOWN_SECONDS", 300)
        cooldown_mgr: CooldownManager = self.bot.cooldown_manager

        await interaction.response.defer(ephemeral=True)

        remaining = cooldown_mgr.remaining_seconds(user.id, cooldown_seconds)
        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            await interaction.followup.send(
                f"⏳ Please wait **{minutes}m {seconds}s** before requesting another invite.",
                ephemeral=True,
            )
            return

        staff_channel_id = self.bot.config.get("STAFF_LOG_CHANNEL")
        channel = safe_get_channel(self.bot, staff_channel_id)

        if channel is None and staff_channel_id:
            try:
                channel = await self.bot.fetch_channel(staff_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.exception("Não foi possível acessar STAFF_LOG_CHANNEL=%s", staff_channel_id)
                await interaction.followup.send(
                    "❌ Could not reach the staff channel. Please contact a staff member.",
                    ephemeral=True,
                )
                return

        if channel is None:
            await interaction.followup.send(
                "❌ Staff channel not configured. Contact an administrator.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        role_id = self.bot.config.get("CREW_LEADER_ROLE_ID")
        crew_leader_role = guild.get_role(role_id) if guild and role_id else None

        embed = make_embed(
            title="📨 New Invite Request",
            color=discord.Color.blue(),
        )
        embed.description = (
            f"👤 **User:** {user.mention}\n"
            f"⏰ **Time:** <t:{int(now.timestamp())}:R>"
        )

        try:
            mention = crew_leader_role.mention if crew_leader_role else ""
            await channel.send(
                content=f"{mention} **{user.display_name}** has requested an invitation.",
                embed=embed,
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Falha ao enviar pedido de convite para STAFF_LOG_CHANNEL")
            await interaction.followup.send(
                "❌ Could not send your request to staff. Please try again later.",
                ephemeral=True,
            )
            return

        # Só registra cooldown após sucesso
        cooldown_mgr.set_now(user.id)

        await interaction.followup.send(
            "📨 Invite request sent to staff.",
            ephemeral=True,
        )


class Invite(commands.Cog):
    """Invite panel system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Registra a view persistente
        self.bot.add_view(InviteView(bot))
        logger.info("InviteView persistente registrada.")

    @app_commands.command(
        name="invitepanel",
        description="Send the official invite request panel",
    )
    async def invitepanel(self, interaction: discord.Interaction):
        required = self.bot.config.get("REQUIRED_INVITE_CHANNEL")
        if required and interaction.channel_id != required:
            await interaction.response.send_message(
                f"❌ Use this command only in <#{required}>.",
                ephemeral=True,
            )
            return

        cooldown_min = self.bot.config.get("INVITE_COOLDOWN_SECONDS", 300) // 60

        embed = make_embed(
            title="🚗 Bovary Club – Invitation Request Panel",
            color=discord.Color.from_rgb(80, 120, 255),
        )
        embed.description = (
            "Clique no botão abaixo para solicitar um convite.\n"
            "Seu pedido será encaminhado automaticamente à staff.\n\n"
            f"⏳ *Cooldown: {cooldown_min} minutos*"
        )
        embed.set_image(url="https://i.imgur.com/GTItHzJ.png")

        if interaction.client.user and interaction.client.user.avatar:
            embed.set_thumbnail(url=interaction.client.user.avatar.url)
            embed.set_footer(
                text="Bovary Club Society",
                icon_url=interaction.client.user.avatar.url,
            )

        await interaction.channel.send(embed=embed, view=InviteView(self.bot))
        await interaction.response.send_message("✅ Panel sent.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invite(bot))
