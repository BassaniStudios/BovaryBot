"""
Cog de eventos: logs de membros, canais, mensagens e auto-reações.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel, is_media_in_message

logger = logging.getLogger("bovary_bot.events")


class Events(commands.Cog):
    """Listeners de eventos do servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _log_channel(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("LOG_CHANNEL_ID"))

    def _msg_log_channel(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("MESSAGE_LOG_CHANNEL_ID"))

    def _ignore_id(self) -> Optional[int]:
        return self.bot.config.get("IGNORE_CHANNEL_ID")

    def _auto_react_channels(self) -> list:
        return self.bot.config.get("CHANNEL_IDS", [])

    def _auto_reactions(self) -> list:
        return self.bot.config.get("AUTO_REACTIONS", ["❤️", "🔥", "💯", "💥", "🎀"])

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = self._log_channel()
        if channel:
            await channel.send(
                f"🟢 **{member}** joined the server! (ID: `{member.id}`)"
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = self._log_channel()
        if channel:
            await channel.send(
                f"🔴 **{member}** left the server. (ID: `{member.id}`)"
            )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        log_channel = self._log_channel()
        if log_channel:
            mention = channel.mention if hasattr(channel, "mention") else channel.name
            await log_channel.send(
                f"🆕 Channel created: **{channel.name}** ({mention})"
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        log_channel = self._log_channel()
        if log_channel:
            await log_channel.send(f"🗑️ Channel deleted: **{channel.name}**")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        try:
            if message.author and message.author.bot:
                return
            if message.channel and message.channel.id == self._ignore_id():
                return

            msg_log = self._msg_log_channel()
            if not msg_log:
                return

            content = message.content or "[no text]"
            # Limita conteúdo muito longo
            if len(content) > 1000:
                content = content[:997] + "..."

            embed = make_embed(
                title="🗑️ Message Deleted",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="Canal",
                value=message.channel.mention if message.channel else "Unknown",
                inline=True,
            )
            author = message.author if message.author else "Unknown"
            embed.add_field(name="Author", value=str(author), inline=True)
            embed.add_field(name="Content", value=content, inline=False)

            if message.author and getattr(message.author, "avatar", None):
                embed.set_thumbnail(url=message.author.avatar.url)

            embed.set_footer(text="Bovary Club Society | Delete log")
            await msg_log.send(embed=embed)

        except Exception:
            logger.exception("Error in on_message_delete")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        try:
            if before.author and before.author.bot:
                return
            if before.content == after.content:
                return
            if before.channel and before.channel.id == self._ignore_id():
                return

            msg_log = self._msg_log_channel()
            if not msg_log:
                return

            before_content = before.content or "[no text]"
            after_content = after.content or "[no text]"
            if len(before_content) > 800:
                before_content = before_content[:797] + "..."
            if len(after_content) > 800:
                after_content = after_content[:797] + "..."

            embed = make_embed(
                title="✏️ Message Edited",
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="Canal",
                value=before.channel.mention if before.channel else "Unknown",
                inline=True,
            )
            embed.add_field(name="Author", value=str(before.author), inline=True)
            embed.add_field(name="Before", value=before_content, inline=False)
            embed.add_field(name="After", value=after_content, inline=False)

            if before.author and getattr(before.author, "avatar", None):
                embed.set_thumbnail(url=before.author.avatar.url)

            embed.set_footer(text="Bovary Club Society | Edit log")
            await msg_log.send(embed=embed)

        except Exception:
            logger.exception("Error in on_message_edit")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author and message.author.bot:
            return
        if not message.guild:
            return

        try:
            if message.channel and message.channel.id in self._auto_react_channels():
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
