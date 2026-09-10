"""WebLogs — structured event logging to a channel (Carl-bot style basics)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.weblogs")
FILE = "weblogs.json"


class WebLogs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_json(FILE, {
            "channel_id": None,
            "member_join": True,
            "member_leave": True,
            "message_delete": True,
            "message_edit": False,
            "channel_create": True,
            "channel_delete": True,
            "role_updates": False,
            "boosts": True,
        })

    def _save(self):
        save_json(FILE, self.config)

    async def _send(self, title: str, description: str, color: discord.Color):
        ch_id = self.config.get("channel_id") or self.bot.config.get("LOG_CHANNEL_ID")
        if not ch_id:
            return
        channel = self.bot.get_channel(ch_id)
        if not channel:
            return
        embed = make_embed(title=title, description=description, color=color)
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("WebLog send failed")

    @app_commands.command(name="weblogs_config", description="Configure WebLogs channel and toggles")
    @app_commands.describe(channel="Channel where structured logs are posted")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def weblogs_config(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        member_join: Optional[bool] = None,
        member_leave: Optional[bool] = None,
        message_delete: Optional[bool] = None,
    ):
        if channel:
            self.config["channel_id"] = channel.id
        if member_join is not None:
            self.config["member_join"] = member_join
        if member_leave is not None:
            self.config["member_leave"] = member_leave
        if message_delete is not None:
            self.config["message_delete"] = message_delete
        self._save()
        await interaction.response.send_message(
            f"✅ WebLogs saved.\nChannel: `{self.config.get('channel_id')}`\nConfig: `{self.config}`",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if self.config.get("member_join"):
            await self._send(
                "Member Join",
                f"{member.mention} (`{member.id}`)\nAccount created: {discord.utils.format_dt(member.created_at, 'R')}",
                discord.Color.green(),
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if self.config.get("member_leave"):
            await self._send(
                "Member Leave",
                f"**{member}** (`{member.id}`)",
                discord.Color.red(),
            )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not self.config.get("message_delete") or not message.guild:
            return
        if message.author and message.author.bot:
            return
        content = (message.content or "[no text]")[:500]
        await self._send(
            "Message Delete",
            f"**Channel:** {message.channel.mention}\n**Author:** {message.author}\n**Content:** {content}",
            discord.Color.orange(),
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if self.config.get("channel_create"):
            await self._send("Channel Create", f"**{channel.name}** (`{channel.id}`)", discord.Color.blue())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if self.config.get("channel_delete"):
            await self._send("Channel Delete", f"**{channel.name}** (`{channel.id}`)", discord.Color.dark_red())


async def setup(bot: commands.Bot):
    await bot.add_cog(WebLogs(bot))
