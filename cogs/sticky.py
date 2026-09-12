"""Sticky messages — re-post a message at the bottom of a channel after activity."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.sticky")
FILE = "sticky.json"


class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(FILE, {"channels": {}})
        self._locks: Dict[int, bool] = {}

    def _save(self):
        save_json(FILE, self.data)

    def _entry(self, channel_id: int) -> Optional[Dict]:
        return self.data.get("channels", {}).get(str(channel_id))

    @app_commands.command(name="sticky_set", description="Set a sticky message for this channel")
    @app_commands.describe(content="Message content to keep at the bottom")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_set(self, interaction: discord.Interaction, content: str):
        await interaction.response.defer(ephemeral=True)
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("Text channels only.", ephemeral=True)
            return
        # Delete old sticky if any
        old = self._entry(ch.id)
        if old and old.get("message_id"):
            try:
                m = await ch.fetch_message(old["message_id"])
                await m.delete()
            except Exception:
                pass
        msg = await ch.send(content[:2000])
        self.data.setdefault("channels", {})[str(ch.id)] = {
            "content": content[:2000],
            "message_id": msg.id,
            "author_id": interaction.user.id,
        }
        self._save()
        await interaction.followup.send("✅ Sticky set.", ephemeral=True)

    @app_commands.command(name="sticky_clear", description="Remove sticky from this channel")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_clear(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Text channels only.", ephemeral=True)
            return
        entry = self._entry(ch.id)
        if entry and entry.get("message_id"):
            try:
                m = await ch.fetch_message(entry["message_id"])
                await m.delete()
            except Exception:
                pass
        self.data.get("channels", {}).pop(str(ch.id), None)
        self._save()
        await interaction.response.send_message("✅ Sticky cleared.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        entry = self._entry(message.channel.id)
        if not entry:
            return
        if self._locks.get(message.channel.id):
            return
        self._locks[message.channel.id] = True
        try:
            # Delete previous sticky
            if entry.get("message_id"):
                try:
                    old = await message.channel.fetch_message(entry["message_id"])
                    await old.delete()
                except Exception:
                    pass
            new_msg = await message.channel.send(entry["content"])
            entry["message_id"] = new_msg.id
            self._save()
        except Exception:
            logger.exception("Sticky repost failed in %s", message.channel.id)
        finally:
            self._locks[message.channel.id] = False


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
