"""
Cog de eventos: auto-reações em canais de mídia.
Logs estruturados ficam em weblogs.py (canais separados).
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from utils.helpers import is_media_in_message

logger = logging.getLogger("bovary_bot.events")


class Events(commands.Cog):
    """Listeners leves — apenas auto-reações."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _auto_react_channels(self) -> list:
        return self.bot.config.get("CHANNEL_IDS", [])

    def _auto_reactions(self) -> list:
        return self.bot.config.get("AUTO_REACTIONS", ["❤️", "🔥", "💯", "💥", "🎀"])

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author and message.author.bot:
            return
        if not message.guild:
            return

        # Só processa canais configurados para auto-react (evita custo em todo o servidor)
        channel_ids = self._auto_react_channels()
        if not channel_ids or message.channel.id not in channel_ids:
            return

        try:
            if is_media_in_message(message):
                me = message.guild.me
                if me and message.channel.permissions_for(me).add_reactions:
                    for emoji in self._auto_reactions():
                        try:
                            await message.add_reaction(emoji)
                        except discord.HTTPException:
                            continue
        except Exception:
            logger.exception("Error processing auto-reactions")


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
