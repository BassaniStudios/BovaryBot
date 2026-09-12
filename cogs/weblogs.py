"""WebLogs — structured event logging with dedicated channels and toggles."""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict

import discord
from discord import app_commands
from discord.ext import commands

import os

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.weblogs")
FILE = "weblogs.json"

def _message_cache_size() -> int:
    """Configurable message cache size (env MESSAGE_CACHE_SIZE, default 12000)."""
    try:
        raw = os.getenv("MESSAGE_CACHE_SIZE", "12000").strip()
        size = int(raw) if raw else 12000
        return max(1000, min(size, 50_000))  # hard bounds
    except (TypeError, ValueError):
        return 12000

MESSAGE_CACHE_SIZE = _message_cache_size()


class WebLogs(commands.Cog):
    """
    Logs estruturados (única fonte — sem duplicar com events.py):
    - Joins / leaves  → LOG_CHANNEL_ID (Info)
    - Message edit/delete → MESSAGE_LOG_CHANNEL_ID ONLY
      (🗑️┃msg-log-only-leaders — serviço separado, sem filtro de cargos)
    - Channel create/delete / admin → WEBLOGS_CHANNEL_ID
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
        self._msg_cache: OrderedDict[int, Dict[str, Any]] = OrderedDict()
        self._delete_logged: OrderedDict[int, bool] = OrderedDict()

    def _save(self):
        save_json(FILE, self.config)

    def _info_channel(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("LOG_CHANNEL_ID"))

    def _bot_room(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("BOT_ROOM_CHANNEL_ID"))

    def _weblogs_channel(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("WEBLOGS_CHANNEL_ID"))

    def _msg_log(self) -> Optional[discord.abc.GuildChannel]:
        """Dedicated message log ONLY — msg-log-only-leaders (1432715549116207248)."""
        return safe_get_channel(self.bot, self.bot.config.get("MESSAGE_LOG_CHANNEL_ID"))

    def _ignore_id(self) -> Optional[int]:
        return self.bot.config.get("IGNORE_CHANNEL_ID")

    async def _send_embed(self, channel: Optional[discord.abc.GuildChannel], embed: discord.Embed):
        if not channel:
            logger.warning("WebLog skip: channel is None (check MESSAGE_LOG_CHANNEL_ID / env)")
            return
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("WebLog send failed to %s", getattr(channel, "id", "?"))

    async def log_admin(self, title: str, description: str, color: Optional[discord.Color] = None):
        embed = make_embed(title=title, description=description, color=color or discord.Color.orange())
        await self._send_embed(self._weblogs_channel(), embed)

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
            size = getattr(a, "size", 0) or 0
            if size >= 1024 * 1024:
                size_text = f"{size / (1024 * 1024):.1f} MB"
            elif size >= 1024:
                size_text = f"{size / 1024:.1f} KB"
            else:
                size_text = f"{size} B"
            lines.append(
                f"• [{kind}] [{a.filename}]({a.url}) — `{size_text}` — `{a.content_type or 'unknown'}`"
            )
        return lines

    def _attachment_lines_from_snap(self, atts: List[Dict[str, Any]]) -> List[str]:
        lines = []
        for a in atts:
            kind = "file"
            ct = a.get("content_type") or ""
            if ct.startswith("image/"):
                kind = "image"
            elif ct.startswith("video/"):
                kind = "video"
            size = a.get("size") or 0
            if size >= 1024 * 1024:
                size_text = f"{size / (1024 * 1024):.1f} MB"
            elif size >= 1024:
                size_text = f"{size / 1024:.1f} KB"
            else:
                size_text = f"{size} B"
            filename = a.get("filename") or "file"
            url = a.get("url") or ""
            lines.append(f"• [{kind}] [{filename}]({url}) — `{size_text}` — `{ct or 'unknown'}`")
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

    def _snapshot(self, message: discord.Message) -> Dict[str, Any]:
        author = message.author
        atts = []
        for a in message.attachments:
            atts.append({
                "id": getattr(a, "id", None),
                "filename": a.filename,
                "url": a.url,
                "size": getattr(a, "size", 0) or 0,
                "content_type": a.content_type,
            })
        return {
            "id": message.id,
            "channel_id": message.channel.id if message.channel else None,
            "content": message.content or "",
            "author_id": author.id if author else None,
            "author_name": str(author) if author else "Unknown",
            "author_mention": author.mention if author else "Unknown",
            "author_bot": bool(author and author.bot),
            "author_avatar": (
                author.display_avatar.url
                if author and getattr(author, "display_avatar", None)
                else None
            ),
            "attachments": atts,
            "image_url": self._first_image_url(message),
        }

    def _cache_put(self, message: discord.Message) -> None:
        if not message or not message.guild:
            return
        if message.author and message.author.bot:
            return
        self._msg_cache[message.id] = self._snapshot(message)
        self._msg_cache.move_to_end(message.id)
        while len(self._msg_cache) > MESSAGE_CACHE_SIZE:
            self._msg_cache.popitem(last=False)

    def _mark_delete_logged(self, message_id: int) -> None:
        self._delete_logged[message_id] = True
        self._delete_logged.move_to_end(message_id)
        while len(self._delete_logged) > MESSAGE_CACHE_SIZE:
            self._delete_logged.popitem(last=False)

    @app_commands.command(name="weblogs_config", description="Configure WebLogs toggles")
    @app_commands.describe(
        member_join="Log member joins to Info channel",
        member_leave="Log member leaves to Info channel",
        message_delete="Log message deletes (msg-log channel only)",
        message_edit="Log message edits (msg-log channel only)",
        channel_create="Log channel creation (weblogs channel)",
        channel_delete="Log channel deletion (weblogs channel)",
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
        created = member.created_at
        embed = discord.Embed(
            title="🟢 Member Join",
            description=f"Welcome {member.mention}",
            color=discord.Color.from_rgb(80, 220, 120),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤 User", value=f"{member.mention}\n`{member}`", inline=True)
        embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
        embed.add_field(
            name="📅 Account created",
            value=f"{discord.utils.format_dt(created, 'F')}\n({discord.utils.format_dt(created, 'R')})",
            inline=False,
        )
        if member.guild:
            embed.add_field(name="📊 Member count", value=str(member.guild.member_count), inline=True)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_footer(text="Bova's Bot · Member Log")
        await self._send_embed(self._info_channel(), embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self.config.get("member_leave"):
            return
        roles = [r.mention for r in getattr(member, "roles", []) if r.name != "@everyone"][:10]
        embed = discord.Embed(
            title="🔴 Member Leave",
            color=discord.Color.from_rgb(220, 60, 80),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤 User", value=f"`{member}`", inline=True)
        embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
        if getattr(member, "joined_at", None):
            embed.add_field(
                name="📥 Joined",
                value=discord.utils.format_dt(member.joined_at, "R"),
                inline=True,
            )
        if roles:
            embed.add_field(name="🏷️ Roles", value=" ".join(roles)[:500], inline=False)
        if member.guild:
            embed.add_field(name="📊 Members now", value=str(member.guild.member_count), inline=True)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_footer(text="Bova's Bot · Member Log")
        await self._send_embed(self._info_channel(), embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        self._cache_put(message)

    async def _send_delete_embed(
        self,
        *,
        channel_mention: str,
        author_value: str,
        message_id: int,
        content: str,
        atts: List[str],
        img: Optional[str],
        avatar: Optional[str],
    ) -> None:
        if len(content) > 900:
            content = content[:897] + "..."
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.from_rgb(255, 70, 90),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Channel", value=channel_mention, inline=True)
        embed.add_field(name="Author", value=author_value, inline=True)
        embed.add_field(name="Message ID", value=f"`{message_id}`", inline=True)
        embed.add_field(name="Content", value=content or "*No text content*", inline=False)
        if atts:
            embed.add_field(name="Attachments", value="\n".join(atts)[:1000], inline=False)
        if img:
            embed.set_image(url=img)
        if avatar:
            embed.set_thumbnail(url=avatar)
        embed.set_footer(text="Bova's Bot · Message Log · Attachments may expire")
        await self._send_embed(self._msg_log(), embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Fires when the message is still in discord.py cache (full content)."""
        if not self.config.get("message_delete") or not message.guild:
            return
        if message.author and message.author.bot:
            return
        if message.channel and message.channel.id == self._ignore_id():
            return

        content = (message.content or "").strip() or "*No text content*"
        author = message.author
        author_value = (
            f"{author.mention if author else 'Unknown'}\n`{getattr(author, 'id', '—')}`"
        )
        channel_mention = message.channel.mention if message.channel else "Unknown"
        atts = self._attachment_lines(message)
        img = self._first_image_url(message)
        avatar = (
            author.display_avatar.url
            if author and getattr(author, "display_avatar", None)
            else None
        )

        await self._send_delete_embed(
            channel_mention=channel_mention,
            author_value=author_value,
            message_id=message.id,
            content=content,
            atts=atts,
            img=img,
            avatar=avatar,
        )
        self._mark_delete_logged(message.id)
        self._msg_cache.pop(message.id, None)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """Fallback when message is NOT in discord.py cache (uses our cache)."""
        if not self.config.get("message_delete"):
            return
        if not payload.guild_id:
            return
        if payload.channel_id == self._ignore_id():
            return
        if payload.message_id in self._delete_logged:
            return

        snap = self._msg_cache.pop(payload.message_id, None)
        if snap and snap.get("author_bot"):
            return

        channel = self.bot.get_channel(payload.channel_id)
        channel_mention = channel.mention if channel else f"`#{payload.channel_id}`"

        if snap:
            content = (snap.get("content") or "").strip() or "*No text content*"
            author_value = f"{snap.get('author_mention', 'Unknown')}\n`{snap.get('author_id', '—')}`"
            atts = self._attachment_lines_from_snap(snap.get("attachments") or [])
            img = snap.get("image_url")
            avatar = snap.get("author_avatar")
        else:
            content = "*Content not available (message was not in bot cache)*"
            author_value = "Unknown (uncached)"
            atts = []
            img = None
            avatar = None

        await self._send_delete_embed(
            channel_mention=channel_mention,
            author_value=author_value,
            message_id=payload.message_id,
            content=content,
            atts=atts,
            img=img,
            avatar=avatar,
        )
        self._mark_delete_logged(payload.message_id)

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
            value=(
                f"{before.author.mention if before.author else 'Unknown'}\n"
                f"`{getattr(before.author, 'id', '—')}`"
            ),
            inline=True,
        )
        jump = after.jump_url if after else None
        if jump:
            embed.add_field(name="Jump", value=f"[Open message]({jump})", inline=True)
        embed.add_field(name="Before", value=before_c, inline=False)
        embed.add_field(name="After", value=after_c, inline=False)

        before_atts = self._attachment_lines(before)
        after_atts = self._attachment_lines(after)
        if before_atts:
            embed.add_field(name="Attachments (before)", value="\n".join(before_atts)[:1000], inline=False)
        if after_atts:
            embed.add_field(name="Attachments (after)", value="\n".join(after_atts)[:1000], inline=False)

        before_ids = {getattr(a, "id", None) for a in before.attachments}
        after_ids = {getattr(a, "id", None) for a in after.attachments}
        added = [a.filename for a in after.attachments if getattr(a, "id", None) not in before_ids]
        removed = [a.filename for a in before.attachments if getattr(a, "id", None) not in after_ids]
        if added:
            embed.add_field(
                name="Added files",
                value="\n".join(f"• `{name}`" for name in added)[:1000],
                inline=True,
            )
        if removed:
            embed.add_field(
                name="Removed files",
                value="\n".join(f"• `{name}`" for name in removed)[:1000],
                inline=True,
            )

        img = self._first_image_url(after) or self._first_image_url(before)
        if img:
            embed.set_image(url=img)
        if before.author and getattr(before.author, "display_avatar", None):
            embed.set_thumbnail(url=before.author.display_avatar.url)

        embed.set_footer(text="Bova's Bot · Message Log")
        await self._send_embed(self._msg_log(), embed)
        self._cache_put(after)

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
        await self._send_embed(self._weblogs_channel(), embed)

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
        await self._send_embed(self._weblogs_channel(), embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WebLogs(bot))
