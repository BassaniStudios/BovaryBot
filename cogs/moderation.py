"""
Moderation cog: delete message, purge.
Kick/ban intentionally removed per project requirements.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel

logger = logging.getLogger("bovary_bot.moderation")


class Moderation(commands.Cog):
    """Moderation commands (no kick/ban)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_msg_log(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("MESSAGE_LOG_CHANNEL_ID"))

    @app_commands.command(
        name="delete",
        description="Delete a message by ID anonymously",
    )
    @app_commands.describe(
        channel="Channel where the message is located",
        message_id="ID of the message to delete",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def delete_msg(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
    ):
        try:
            msg_id = int(message_id.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Message ID must be a valid number.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        if not channel.permissions_for(interaction.guild.me).manage_messages:
            await interaction.followup.send(
                "🚫 I do not have permission to delete messages in this channel.",
                ephemeral=True,
            )
            return

        try:
            message = await channel.fetch_message(msg_id)
            await message.delete()
            await interaction.followup.send(
                "✅ Message removed successfully.",
                ephemeral=True,
            )

            msg_log = self._get_msg_log()
            if msg_log:
                embed = make_embed(
                    title="🧹 Message deleted via command",
                    description=(
                        f"**Channel:** {channel.mention}\n"
                        f"**Message ID:** `{msg_id}`\n"
                        f"**Executor:** {interaction.user.mention} (`{interaction.user.id}`)"
                    ),
                    color=discord.Color.blurple(),
                )
                embed.set_footer(text="Action executed anonymously for the end user")
                await msg_log.send(embed=embed)

        except discord.NotFound:
            await interaction.followup.send("⚠️ Message not found.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "🚫 I do not have permission to delete messages in this channel.",
                ephemeral=True,
            )
        except Exception as e:
            logger.exception("Error deleting message")
            await interaction.followup.send(f"❌ An error occurred: `{e}`", ephemeral=True)

    @app_commands.command(
        name="purge",
        description="Delete a number of messages in the current channel",
    )
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
    ):
        if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
            await interaction.response.send_message(
                "🚫 I do not have permission to delete messages in this channel.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(
                f"✅ {len(deleted)} message(s) deleted.",
                ephemeral=True,
            )

            msg_log = self._get_msg_log()
            if msg_log:
                embed = make_embed(
                    title="🧹 Channel purged via command",
                    description=(
                        f"**Channel:** {interaction.channel.mention}\n"
                        f"**Amount:** `{len(deleted)}`\n"
                        f"**Executor:** {interaction.user.mention}"
                    ),
                    color=discord.Color.orange(),
                )
                await msg_log.send(embed=embed)

        except discord.Forbidden:
            await interaction.followup.send(
                "🚫 I do not have permission to delete messages here.",
                ephemeral=True,
            )
        except Exception as e:
            logger.exception("Error in purge command")
            await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)

    @delete_msg.error
    @purge.error
    async def mod_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "🚫 You do not have permission to run this command."
        else:
            msg = "❌ An error occurred while running the command."
            logger.exception("Moderation command error: %s", error)

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
