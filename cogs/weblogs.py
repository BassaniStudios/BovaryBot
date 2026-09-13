"""WebLogs — structured event logging with dedicated channels.

Message Log (delete/edit) is intentionally simple and independent of Turso/SQLite:
- Always on (no toggle dependency for reliability)
- Fixed channel via MESSAGE_LOG_CHANNEL_ID
- In-memory cache + raw delete fallback
- fetch_channel fallback when get_channel returns None
"""
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

# Hardcoded production default (same as bot.py / .env.example)
DEFAULT_MSG_LOG_ID = 1432715549116207248


def _message_cache_size() -> int:
    try:
        raw = os.getenv("MESSAGE_CACHE_SIZE", "12000").strip()
        size = int(raw) if raw else 12000
        return max(1000, min(size, 50_000))
    except (TypeError, ValueError):
        return 12000


MESSAGE_CACHE_SIZE = _message_cache_size()


class WebLogs(commands.Cog):
    """
    Logs estruturados:
    - Joins / leaves     → LOG_CHANNEL_ID
    - Message edit/delete → MESSAGE_LOG_CHANNEL_ID ONLY (sempre ativo, estilo antigo)
    - Channel create/delete → WEBLOGS_CHANNEL_ID
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Toggles only for non-message events (message log is always on)
        self.config = load_json(FILE, {
            "member_join": True,
            "member_leave": True,
            "message_delete": True,   # kept for /weblogs_config display, ignored for actual send
            "message_edit": True,
            "channel_create": True,
            "channel_delete": True,
            "role_updates": False,
            "boosts": True,
        })
        self._msg_cache: OrderedDict[int, Dict[str, Any]] = OrderedDict()
        self._delete_logged: OrderedDict[int, bool] = OrderedDict()
        self._msg_log_channel: Optional[discord.abc.GuildChannel] = None  # cached resolved channel

    def _save(self):
        save_json(FILE, self.config)

    def _info_channel(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("LOG_CHANNEL_ID"))

    def _bot_room(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("BOT_ROOM_CHANNEL_ID"))

    def _weblogs_channel(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("WEBLOGS_CHANNEL_ID"))

    def _msg_log_id(self) -> int:
        """Always resolve a concrete channel ID (env → bot config → hardcoded)."""
        cid = self.bot.config.get("MESSAGE_LOG_CHANNEL_ID")
        if cid:
            return int(cid)
        return DEFAULT_MSG_LOG_ID

    def _ignore_id(self) -> Optional[int]:
        return self.bot.config.get("IGNORE_CHANNEL_ID")

    async def _resolve_msg_log(self) -> Optional[discord.abc.Messageable]:
        """
        Resolve the message-log channel robustly.
        1) cached instance
        2) bot.get_channel (fast)
        3) bot.fetch_channel (async, works even if not in cache)
        """
        if self._msg_log_channel is not None:
            return self._msg_log_channel

        cid = self._msg_log_id()
        ch = self.bot.get_channel(cid)
        if ch is not None:
            self._msg_log_channel = ch
            return ch

        try:
            ch = await self.bot.fetch_channel(cid)
            self._msg_log_channel = ch  # type: ignore
            logger.info("Message log channel resolved via fetch_channel: %s", cid)
            return ch
        except discord.NotFound:
            logger.error(
                "MESSAGE_LOG_CHANNEL_ID=%s not found. Check the ID and that the bot can see the channel.",
                cid,
            )
        except discord.Forbidden:
            logger.error(
                "No permission to fetch MESSAGE_LOG_CHANNEL_ID=%s. Give the bot View Channel there.",
                cid,
            )
        except Exception:
            logger.exception("Failed to resolve message log channel %s", cid)
        return None

    async def _send_embed(self, channel: Optional[discord.abc.Messageable], embed: discord.Embed):
        if not channel:
            logger.warning("WebLog skip: channel is None")
            return
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.error(
                "Forbidden sending to channel %s — need Send Messages + Embed Links",
                getattr(channel, "id", "?"),
            )
        except Exception:
            logger.exception("WebLog send failed to %s", getattr(channel, "id", "?"))

    async def log_admin(self, title: str, description: str, color: Optional[discord.Color] = None):
        embed = make_embed(title=title, description=description, color=color or discord.Color.orange())
        await self._send_embed(self._weblogs_channel(), embed)

    async def log_message(self, title: str, description: str, color: Optional[discord.Color] = None):
        embed = make_embed(title=title, description=description, color=color or discord.Color.red())
        ch = await self._resolve_msg_log()
        await self._send_embed(ch, embed)

    # ── attachment / snapshot helpers ─────────────────────────────────────────

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

    # ── slash config ──────────────────────────────────────────────────────────

    @app_commands.command(name="weblogs_config", description="Configure WebLogs toggles")
    @app_commands.describe(
        member_join="Log member joins to Info channel",
        member_leave="Log member leaves to Info channel",
        message_delete="(informational — message log is always on)",
        message_edit="(informational — message log is always on)",
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
            "✅ WebLogs toggles saved.\n"
            "⚠️ Message delete/edit logs are **always active** (independent of toggles).\n"
            + "\n".join(lines),
            ephemeral=True,
        )

    @app_commands.command(name="msglog_test", description="Test the dedicated message-log channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def msglog_test(self, interaction: discord.Interaction):
        """Sends a test embed to MESSAGE_LOG_CHANNEL_ID and reports status."""
        await interaction.response.defer(ephemeral=True)
        cid = self._msg_log_id()
        ch = await self._resolve_msg_log()
        if not ch:
            await interaction.followup.send(
                f"❌ Não consegui resolver o canal `{cid}`.\n"
                "• Confirme MESSAGE_LOG_CHANNEL_ID no env\n"
                "• O bot precisa ter **Ver canal** nesse canal\n"
                "• Veja os logs do bot (Render) para o erro exato",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="✅ Message Log — Teste OK",
            description=(
                f"Canal: {getattr(ch, 'mention', cid)}\n"
                f"ID: `{cid}`\n"
                f"Cache size: `{len(self._msg_cache)}` mensagens"
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Bova's Bot · Message Log Test")
        try:
            await ch.send(embed=embed)
            await interaction.followup.send(
                f"✅ Embed de teste enviado em {getattr(ch, 'mention', cid)}",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Sem permissão para enviar no canal `{cid}`.\n"
                "Dê ao bot: **Ver canal + Enviar mensagens + Incorporar links**",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao enviar: `{e}`", ephemeral=True)

    # ── member join / leave ───────────────────────────────────────────────────

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
        embed.set_footer(text="Bova's Bot · Info Log")
        await self._send_embed(self._info_channel(), embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self.config.get("member_leave"):
            return
        embed = discord.Embed(
            title="🔴 Member Leave",
            description=f"{member} left the server",
            color=discord.Color.from_rgb(220, 80, 80),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤 User", value=f"`{member}`\n`{member.id}`", inline=True)
        if member.joined_at:
            embed.add_field(
                name="📅 Joined",
                value=f"{discord.utils.format_dt(member.joined_at, 'R')}",
                inline=True,
            )
        if member.guild:
            embed.add_field(name="📊 Member count", value=str(member.guild.member_count), inline=True)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Bova's Bot · Info Log")
        await self._send_embed(self._info_channel(), embed)

    # ── MESSAGE LOG (simple, always on) ───────────────────────────────────────

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

        ch = await self._resolve_msg_log()
        await self._send_embed(ch, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Fires when the message is still in discord.py cache (full content)."""
        if not message.guild:
            return
        if message.author and message.author.bot:
            return
        if message.channel and message.channel.id == self._ignore_id():
            return
        # Mark FIRST so concurrent on_raw_message_delete skips (avoids double embed)
        if message.id in self._delete_logged:
            return
        self._mark_delete_logged(message.id)
        self._msg_cache.pop(message.id, None)

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

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """Fallback when message is NOT in discord.py cache (uses our cache)."""
        if not payload.guild_id:
            return
        if payload.channel_id == self._ignore_id():
            return
        # Already handled by on_message_delete (or a previous raw) → skip
        if payload.message_id in self._delete_logged:
            return
        self._mark_delete_logged(payload.message_id)

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


    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild:
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
        ch = await self._resolve_msg_log()
        await self._send_embed(ch, embed)
        self._cache_put(after)

    # ── channel create / delete ───────────────────────────────────────────────

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
