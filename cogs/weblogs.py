"""WebLogs — structured event logging with dedicated channels and toggles."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.weblogs")
FILE = "weblogs.json"


class WebLogs(commands.Cog):
    """
    Logs estruturados (única fonte — sem duplicar com events.py):
    - Joins / leaves  → LOG_CHANNEL_ID (Info)
    - Admin / channels → BOT_ROOM_CHANNEL_ID (bot-room)
    - Message delete/edit → MESSAGE_LOG_CHANNEL_ID
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_json(FILE, {
            "member_join": True,
            "member_leave": True,
            "message_delete": True,
            "message_edit": True,
            "channel_create": True,
            "channel_delete": True,
            "role_updates": False,
            "boosts": True,
        })

    def _save(self):
        save_json(FILE, self.config)

    def _info_channel(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("LOG_CHANNEL_ID"))

    def _bot_room(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("BOT_ROOM_CHANNEL_ID"))

    def _msg_log(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("MESSAGE_LOG_CHANNEL_ID"))

    def _ignore_id(self) -> Optional[int]:
        return self.bot.config.get("IGNORE_CHANNEL_ID")

    async def _send_embed(self, channel: Optional[discord.abc.GuildChannel], embed: discord.Embed):
        if not channel:
            return
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("WebLog send failed to %s", getattr(channel, "id", "?"))

    async def log_admin(self, title: str, description: str, color: Optional[discord.Color] = None):
        embed = make_embed(title=title, description=description, color=color or discord.Color.orange())
        await self._send_embed(self._bot_room(), embed)

    async def log_message(self, title: str, description: str, color: Optional[discord.Color] = None):
        embed = make_embed(title=title, description=description, color=color or discord.Color.red())
        await self._send_embed(self._msg_log(), embed)

    def _attachment_lines(self, message: discord.Message) -> List[str]:
        lines = []
        for a in message.attachments:
            kind = "file"
            if a.content_type:
                if a.content_type.startswith("image/"):
                    kind = "image"
                elif a.content_type.startswith("video/"):
                    kind = "video"
            lines.append(f"• [{kind}] [{a.filename}]({a.url})")
        return lines

    def _first_image_url(self, message: discord.Message) -> Optional[str]:
        for a in message.attachments:
            if a.content_type and a.content_type.startswith("image/"):
                return a.url
            name = (a.filename or "").lower()
            if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                return a.url
        for e in message.embeds:
            if e.image and e.image.url:
                return e.image.url
            if e.thumbnail and e.thumbnail.url:
                return e.thumbnail.url
        return None

    @app_commands.command(name="weblogs_config", description="Configure WebLogs toggles")
    @app_commands.describe(
        member_join="Log member joins to Info channel",
        member_leave="Log member leaves to Info channel",
        message_delete="Log message deletes",
        message_edit="Log message edits",
        channel_create="Log channel creation (bot-room)",
        channel_delete="Log channel deletion (bot-room)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def weblogs_config(
        self,
        interaction: discord.Interaction,
        member_join: Optional[bool] = None,
        member_leave: Optional[bool] = None,
        message_delete: Optional[bool] = None,
        message_edit: Optional[bool] = None,
        channel_create: Optional[bool] = None,
        channel_delete: Optional[bool] = None,
    ):
        mapping = {
            "member_join": member_join,
            "member_leave": member_leave,
            "message_delete": message_delete,
            "message_edit": message_edit,
            "channel_create": channel_create,
            "channel_delete": channel_delete,
        }
        for key, val in mapping.items():
            if val is not None:
                self.config[key] = val
        self._save()
        lines = [f"**{k}:** `{v}`" for k, v in self.config.items()]
        await interaction.response.send_message(
            "✅ WebLogs toggles saved.\n" + "\n".join(lines),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self.config.get("member_join"):
            return
        embed = discord.Embed(
            title="🟢 Member Join",
            description=(
                f"**User:** {member.mention}\n"
                f"**ID:** `{member.id}`\n"
                f"**Account:** {discord.utils.format_dt(member.created_at, 'R')}"
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Bova's Bot · Member Log")
        await self._send_embed(self._info_channel(), embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self.config.get("member_leave"):
            return
        embed = discord.Embed(
            title="🔴 Member Leave",
            description=f"**User:** `{member}`\n**ID:** `{member.id}`",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Bova's Bot · Member Log")
        await self._send_embed(self._info_channel(), embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not self.config.get("message_delete") or not message.guild:
            return
        if message.author and message.author.bot:
            return
        if message.channel and message.channel.id == self._ignore_id():
            return

        content = (message.content or "").strip() or "*No text content*"
        if len(content) > 900:
            content = content[:897] + "..."

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.from_rgb(255, 70, 90),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Channel",
            value=message.channel.mention if message.channel else "Unknown",
            inline=True,
        )
        author = message.author
        embed.add_field(
            name="Author",
            value=f"{author.mention if author else 'Unknown'}\n`{getattr(author, 'id', '—')}`",
            inline=True,
        )
        embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
        embed.add_field(name="Content", value=content, inline=False)

        atts = self._attachment_lines(message)
        if atts:
            embed.add_field(name="Attachments", value="\n".join(atts)[:1000], inline=False)

        img = self._first_image_url(message)
        if img:
            embed.set_image(url=img)

        if author and getattr(author, "display_avatar", None):
            embed.set_thumbnail(url=author.display_avatar.url)

        embed.set_footer(text="Bova's Bot · Message Log · Attachments may expire")
        await self._send_embed(self._msg_log(), embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not self.config.get("message_edit") or not before.guild:
            return
        if before.author and before.author.bot:
            return
        if before.content == after.content and before.attachments == after.attachments:
            return
        if before.channel and before.channel.id == self._ignore_id():
            return

        before_c = (before.content or "").strip() or "*empty*"
        after_c = (after.content or "").strip() or "*empty*"
        if len(before_c) > 500:
            before_c = before_c[:497] + "..."
        if len(after_c) > 500:
            after_c = after_c[:497] + "..."

        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.from_rgb(255, 160, 40),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Channel",
            value=before.channel.mention if before.channel else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Author",
            value=f"{before.author.mention if before.author else 'Unknown'}\n`{getattr(before.author, 'id', '—')}`",
            inline=True,
        )
        jump = after.jump_url if after else None
        if jump:
            embed.add_field(name="Jump", value=f"[Open message]({jump})", inline=True)
        embed.add_field(name="Before", value=before_c, inline=False)
        embed.add_field(name="After", value=after_c, inline=False)

        atts = self._attachment_lines(before)
        if atts:
            embed.add_field(name="Attachments (before)", value="\n".join(atts)[:800], inline=False)

        img = self._first_image_url(before) or self._first_image_url(after)
        if img:
            embed.set_image(url=img)

        if before.author and getattr(before.author, "display_avatar", None):
            embed.set_thumbnail(url=before.author.display_avatar.url)

        embed.set_footer(text="Bova's Bot · Message Log")
        await self._send_embed(self._msg_log(), embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if not self.config.get("channel_create"):
            return
        embed = discord.Embed(
            title="🆕 Channel Created",
            description=f"**Name:** `{channel.name}`\n**ID:** `{channel.id}`\n**Type:** `{channel.type}`",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Bova's Bot · Admin Log")
        await self._send_embed(self._bot_room(), embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not self.config.get("channel_delete"):
            return
        embed = discord.Embed(
            title="🗑️ Channel Deleted",
            description=f"**Name:** `{channel.name}`\n**ID:** `{channel.id}`",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Bova's Bot · Admin Log")
        await self._send_embed(self._bot_room(), embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WebLogs(bot))
