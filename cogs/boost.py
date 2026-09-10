"""Boost / server boost thank-you notifications."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.boost")
CONFIG_FILE = "boost.json"

DEFAULT_MSG = (
    "🚀 **Thank you for boosting the server, {user}!**\n\n"
    "Your support keeps **Bovary Club Society** alive — neon nights, clean meets, and good vibes.\n"
    "Welcome to the boosters crew. 💜✨"
)


class Boost(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_json(CONFIG_FILE, {
            "enabled": True,
            "channel_id": None,  # falls back to BOOST_CHANNEL_ID in bot config
            "message": DEFAULT_MSG,
            "embed_color": 0xF47FFF,
        })

    def _save(self):
        save_json(CONFIG_FILE, self.config)

    def _channel_id(self) -> Optional[int]:
        return (
            self.config.get("channel_id")
            or self.bot.config.get("BOOST_CHANNEL_ID")
            or 1384173136638906407
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            await self._send_thanks(after)

    async def _send_thanks(self, member: discord.Member):
        if not self.config.get("enabled", True):
            return
        channel_id = self._channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not channel:
            return
        text = (self.config.get("message") or DEFAULT_MSG).replace("{user}", member.mention)
        color = self.config.get("embed_color", 0xF47FFF)
        embed = discord.Embed(
            title="💜 Server Boost!",
            description=text,
            color=color,
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_image(url=member.display_avatar.url)
        embed.set_footer(text="Bova's Bot · Boost Notification")
        try:
            await channel.send(content=member.mention, embed=embed)
        except Exception:
            logger.exception("Failed to send boost thank-you")

    @app_commands.command(name="boost_config", description="Configure boost thank-you message")
    @app_commands.describe(
        channel="Channel for boost messages (default: dedicated boost channel)",
        message="Message template — use {user} for mention",
        enabled="Enable or disable boost notifications",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def boost_config(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        if channel:
            self.config["channel_id"] = channel.id
        if message:
            self.config["message"] = message
        if enabled is not None:
            self.config["enabled"] = enabled
        self._save()
        await interaction.response.send_message(
            f"✅ Boost config saved.\n"
            f"**Enabled:** {self.config.get('enabled')}\n"
            f"**Channel:** {self._channel_id()}\n"
            f"**Message:** {self.config.get('message', '')[:200]}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Boost(bot))
