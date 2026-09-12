"""WebLogs — structured event logging with dedicated channels and toggles."""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.weblogs")
FILE = "weblogs.json"

# How many recent messages to keep in memory for reliable delete/edit logs.
# Discord only gives full content for cached messages; raw events need this.
MESSAGE_CACHE_SIZE = 5000


class WebLogs(commands.Cog):
    """
    Logs estruturados (única fonte — sem duplicar com events.py):
    - Joins / leaves  → LOG_CHANNEL_ID (Info)
    - Nick / name history alerts → BOT_ROOM_CHANNEL_ID (namehistory cog)
    - Message edit/delete → MESSAGE_LOG_CHANNEL_ID only
      (🗑️┃msg-log-only-leaders — serviço separado, sem filtro de cargos)
    - Other weblogs (channel create/delete, admin)
      → WEBLOGS_CHANNEL_ID
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
        # message_id -> snapshot dict (content, author, attachments, etc.)
        self._msg_cache: OrderedDict[int, Dict[str, Any]] = OrderedDict()

    def _save(self):
        save_json(FILE, self.config)

    def _info_channel(self) -> Optional[discord.abc.GuildChannel]:
        """Joins / leaves only."""
        return safe_get_channel(self.bot, self.bot.config.get("LOG_CHANNEL_ID"))

    def _bot_room(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("BOT_ROOM_CHANNEL_ID"))

    def _weblogs_channel(self) -> Optional[discord.abc.GuildChannel]:
        """General WebLogs: channel/admin events only.

        Message edit/delete logging is intentionally kept separate in
        MESSAGE_LOG_CHANNEL_ID. This prevents the detailed message logger
        from being mixed into the general WebLogs stream.
        """
        return safe_get_channel(self.bot, self.bot.config.get("WEBLOGS_CHANNEL_ID"))

    def _msg_log(self) -> Optional[discord.abc.GuildChannel]:
        """Dedicated detailed message log channel ONLY.

        Default: 🗑️┃msg-log-only-leaders (1432715549116207248).
        Independent service — logs go only here, no role filters.
        """
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
        await self._send_embed(self._weblogs_channel(), embed)

    async def log_message(self, title: str, description: str, color: Optional[discord.Color] = None):
        embed = make_embed(title=title, description=description, color=color or discord.Color.red())
        await self._send_embed(self._msg_log(), embed)

    # ── Message cache (for reliable delete/edit details) ──────────────────

    def _snapshot_message(self, message: discord.Message) -> Dict[str, Any]:
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
        img_url = None
        for a in message.attachments:
            ct = a.content_type or ""
            name = (a.filename or "").lower()
            if ct.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                img_url = a.url
                break
        if not img_url:
            for e in message.embeds:
                if e.image and e.image.url:
                    img_url = e.image.url
                    break
                if e.thumbnail and e.thumbnail.url:
                    img_url = e.thumbnail.url
                    break
        return {
            "id": message.id,
            "channel_id": message.channel.id if message.channel else None,
            "guild_id": message.guild.id if message.guild else None,
            "content": message.content or "",
            "author_id": author.id if author else None,
            "author_name": str(author) if author else "Unknown",
            "author_mention": author.mention if author else "Unknown",
            "author_bot": bool(author and author.bot),
            "author_avatar": author.display_avatar.url if author and getattr(author, "display_avatar", None) else None,
            "attachments": atts,
            "image_url": img_url,
            "jump_url": getattr(message, "jump_url", None),
        }

    def _cache_put(self, message: discord.Message) -> None:
        if not message or not message.guild:
            return
        if message.author and message.author.bot:
            return
        snap = self._snapshot_message(message)
        self._msg_cache[message.id] = snap
        self._msg_cache.move_to_end(message.id)
        while len(self._msg_cache) > MESSAGE_CACHE_SIZE:
            self._msg_cache.popitem(last=False)

    def _cache_get(self, message_id: int) -> Optional[Dict[str, Any]]:
        return self._msg_cache.get(message_id)

    def _cache_pop(self, message_id: int) -> Optional[Dict[str, Any]]:
        return self._msg_cache.pop(message_id, None)

    def _attachment_lines_from_list(self, atts: List[Dict[str, Any]]) -> List[str]:
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

    def _attachment_lines(self, message: discord.Message) -> List[str]:
        return self._attachment_lines_from_list([
            {
                "id": getattr(a, "id", None),
                "filename": a.filename,
                "url": a.url,
                "size": getattr(a, "size", 0) or 0,
                "content_type": a.content_type,
            }
            for a in message.attachments
        ])

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

    # ── Config command ────────────────────────────────────────────────────

    @app_commands.command(name="weblogs_config", description="Configure WebLogs toggles")
    @app_commands.describe(
        member_join="Log member joins to Info channel",
        member_leave="Log member leaves to Info channel",
        message_delete="Log message deletes (only to msg-log channel)",
        message_edit="Log message edits (only to msg-log channel)",
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

    # ── Member logs ───────────────────────────────────────────────────────

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

    # ── Message cache filler ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Keep recent guild messages in memory so delete/edit logs have content."""
        self._cache_put(message)

    # ── Message delete (raw + cached — only to MESSAGE_LOG_CHANNEL_ID) ────

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if not self.config.get("message_delete"):
            return
        if not payload.guild_id:
            return
        if payload.channel_id == self._ignore_id():
            return

        # Prefer cached snapshot (full content + attachments)
        snap = self._cache_pop(payload.message_id)
        if snap and snap.get("author_bot"):
            return

        channel = self.bot.get_channel(payload.channel_id)
        channel_mention = channel.mention if channel else f"`#{payload.channel_id}`"

        if snap:
            content = (snap.get("content") or "").strip() or "*No text content*"
            if len(content) > 900:
                content = content[:897] + "..."
            author_value = f"{snap.get('author_mention', 'Unknown')}\n`{snap.get('author_id', '—')}`"
            atts = self._attachment_lines_from_list(snap.get("attachments") or [])
            img = snap.get("image_url")
            avatar = snap.get("author_avatar")
        else:
            # Uncached: still log what Discord gives us (id + channel)
            content = "*Content not available (message was not in bot cache)*"
            author_value = "Unknown (uncached)"
            atts = []
            img = None
            avatar = None

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.from_rgb(255, 70, 90),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Channel", value=channel_mention, inline=True)
        embed.add_field(name="Author", value=author_value, inline=True)
        embed.add_field(name="Message ID", value=f"`{payload.message_id}`", inline=True)
        embed.add_field(name="Content", value=content, inline=False)
        if atts:
            embed.add_field(name="Attachments", value="\n".join(atts)[:1000], inline=False)
        if img:
            embed.set_image(url=img)
        if avatar:
            embed.set_thumbnail(url=avatar)
        embed.set_footer(text="Bova's Bot · Message Log · Attachments may expire")
        await self._send_embed(self._msg_log(), embed)

    # Keep on_message_delete as thin fallback (raw usually fires first / always)
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # If raw already handled via cache, nothing left to do.
        # Only act if we still have a full message object and raw did not run
        # (edge cases). Avoid double-post by checking cache was already popped.
        if not self.config.get("message_delete") or not message.guild:
            return
        if message.id in self._msg_cache:
            # Raw has not processed yet; leave it for on_raw_message_delete
            return
        # Already consumed by raw — skip to prevent duplicate embeds
        return

    # ── Message edit (raw + cached — only to MESSAGE_LOG_CHANNEL_ID) ──────

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if not self.config.get("message_edit"):
            return
        if not payload.guild_id:
            return
        if payload.channel_id == self._ignore_id():
            return

        before_snap = self._cache_get(payload.message_id)
        data = payload.data or {}

        # After state from payload
        after_content = data.get("content")
        if after_content is None and before_snap:
            after_content = before_snap.get("content", "")
        after_content = after_content if after_content is not None else ""

        # Attachments after
        after_atts_raw = data.get("attachments") or []
        after_atts = []
        for a in after_atts_raw:
            after_atts.append({
                "id": a.get("id"),
                "filename": a.get("filename"),
                "url": a.get("url") or a.get("proxy_url"),
                "size": a.get("size") or 0,
                "content_type": a.get("content_type"),
            })

        if before_snap:
            if before_snap.get("author_bot"):
                return
            before_content = before_snap.get("content") or ""
            before_atts = before_snap.get("attachments") or []
            author_value = f"{before_snap.get('author_mention', 'Unknown')}\n`{before_snap.get('author_id', '—')}`"
            avatar = before_snap.get("author_avatar")
            img = before_snap.get("image_url")
        else:
            # No before snapshot — still log if content changed in payload
            before_content = ""
            before_atts = []
            author_id = data.get("author", {}).get("id") if isinstance(data.get("author"), dict) else None
            author_value = f"Unknown\n`{author_id or '—'}`"
            avatar = None
            img = None
            # If we have zero useful before data and no content change visible, skip noise
            if after_content == "" and not after_atts:
                return

        # Skip pure embed-only updates with no content/attachment change
        if before_content == after_content and not before_atts and not after_atts:
            return
        if before_content == after_content:
            before_ids = {a.get("id") for a in before_atts}
            after_ids = {a.get("id") for a in after_atts}
            if before_ids == after_ids:
                return

        before_c = (before_content or "").strip() or "*empty*"
        after_c = (after_content or "").strip() or "*empty*"
        if len(before_c) > 500:
            before_c = before_c[:497] + "..."
        if len(after_c) > 500:
            after_c = after_c[:497] + "..."

        channel = self.bot.get_channel(payload.channel_id)
        channel_mention = channel.mention if channel else f"`#{payload.channel_id}`"

        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.from_rgb(255, 160, 40),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Channel", value=channel_mention, inline=True)
        embed.add_field(name="Author", value=author_value, inline=True)
        jump = f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}"
        embed.add_field(name="Jump", value=f"[Open message]({jump})", inline=True)
        embed.add_field(name="Before", value=before_c, inline=False)
        embed.add_field(name="After", value=after_c, inline=False)

        before_lines = self._attachment_lines_from_list(before_atts)
        after_lines = self._attachment_lines_from_list(after_atts)
        if before_lines:
            embed.add_field(name="Attachments (before)", value="\n".join(before_lines)[:1000], inline=False)
        if after_lines:
            embed.add_field(name="Attachments (after)", value="\n".join(after_lines)[:1000], inline=False)

        before_ids = {a.get("id") for a in before_atts}
        after_ids = {a.get("id") for a in after_atts}
        added = [a.get("filename") for a in after_atts if a.get("id") not in before_ids]
        removed = [a.get("filename") for a in before_atts if a.get("id") not in after_ids]
        if added:
            embed.add_field(name="Added files", value="\n".join(f"• `{n}`" for n in added if n)[:1000], inline=True)
        if removed:
            embed.add_field(name="Removed files", value="\n".join(f"• `{n}`" for n in removed if n)[:1000], inline=True)

        # Prefer after image if any
        for a in after_atts:
            ct = a.get("content_type") or ""
            name = (a.get("filename") or "").lower()
            if ct.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                img = a.get("url")
                break
        if img:
            embed.set_image(url=img)
        if avatar:
            embed.set_thumbnail(url=avatar)
        embed.set_footer(text="Bova's Bot · Message Log")
        await self._send_embed(self._msg_log(), embed)

        # Refresh cache with after state if we can
        if before_snap:
            updated = dict(before_snap)
            updated["content"] = after_content
            updated["attachments"] = after_atts
            for a in after_atts:
                ct = a.get("content_type") or ""
                name = (a.get("filename") or "").lower()
                if ct.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    updated["image_url"] = a.get("url")
                    break
            self._msg_cache[payload.message_id] = updated
            self._msg_cache.move_to_end(payload.message_id)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Keep cache in sync; actual logging is done by on_raw_message_edit
        # so we do not double-post embeds.
        if after and after.guild and not (after.author and after.author.bot):
            self._cache_put(after)

    # ── Channel create/delete → general weblogs channel ───────────────────

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
