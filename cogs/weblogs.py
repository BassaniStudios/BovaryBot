"""WebLogs — structured event logging with dedicated channels.

Message Log (delete/edit) — style inspired by v2.2 that "worked perfectly":
- Always on (no toggle dependency for reliability)
- Fixed channel via MESSAGE_LOG_CHANNEL_ID
- Pure in-memory OrderedDict cache (NO SQL / NO disk for message snapshots)
- History backfill on ready → recovers messages sent while bot was offline
- on_message_delete when discord.py has the message (full object)
- on_raw_message_delete only when OUR cache has a snapshot (never log empty/uncached)
- fetch_channel fallback when get_channel returns None
- Rich media logging: images/videos get explicit flags + size/dims/spoiler even
  when Discord CDN already expired the preview link
"""
from __future__ import annotations

import asyncio
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


def _backfill_per_channel() -> int:
    """How many recent messages to pull per text channel on startup."""
    try:
        raw = os.getenv("MESSAGE_CACHE_BACKFILL", "200").strip()
        n = int(raw) if raw else 200
        return max(0, min(n, 500))  # 0 = disable backfill
    except (TypeError, ValueError):
        return 200


MESSAGE_CACHE_SIZE = _message_cache_size()
BACKFILL_PER_CHANNEL = _backfill_per_channel()


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
        # Pure in-memory cache — intentionally NO SQLite / NO disk.
        # Survives restarts only via history backfill on_ready.
        self._msg_cache: OrderedDict[int, Dict[str, Any]] = OrderedDict()
        self._delete_logged: OrderedDict[int, bool] = OrderedDict()
        self._msg_log_channel: Optional[discord.abc.GuildChannel] = None  # cached resolved channel
        self._backfill_done = False
        self._backfill_task: Optional[asyncio.Task] = None

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

    @staticmethod
    def _fmt_size(size: int) -> str:
        size = size or 0
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    @staticmethod
    def _is_image_att(filename: str, content_type: Optional[str]) -> bool:
        ct = (content_type or "").lower()
        if ct.startswith("image/"):
            return True
        name = (filename or "").lower()
        return name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"))

    @staticmethod
    def _is_video_att(filename: str, content_type: Optional[str]) -> bool:
        ct = (content_type or "").lower()
        if ct.startswith("video/"):
            return True
        name = (filename or "").lower()
        return name.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi"))

    def _attachment_dict(self, a: discord.Attachment) -> Dict[str, Any]:
        """Rich snapshot of a single attachment (no external storage)."""
        return {
            "id": getattr(a, "id", None),
            "filename": a.filename,
            "url": a.url,
            "proxy_url": getattr(a, "proxy_url", None) or a.url,
            "size": getattr(a, "size", 0) or 0,
            "content_type": a.content_type,
            "width": getattr(a, "width", None),
            "height": getattr(a, "height", None),
            "spoiler": bool(getattr(a, "is_spoiler", False)),
            "description": getattr(a, "description", None),
        }

    def _attachment_line(self, a: Dict[str, Any]) -> str:
        filename = a.get("filename") or "file"
        ct = a.get("content_type") or ""
        if self._is_image_att(filename, ct):
            kind = "📷 image"
        elif self._is_video_att(filename, ct):
            kind = "🎬 video"
        else:
            kind = "📎 file"

        size_text = self._fmt_size(a.get("size") or 0)
        url = a.get("proxy_url") or a.get("url") or ""
        dims = ""
        w, h = a.get("width"), a.get("height")
        if w and h:
            dims = f" — `{w}×{h}`"
        spoiler = " 🔒spoiler" if a.get("spoiler") else ""
        link = f"[{filename}]({url})" if url else f"`{filename}`"
        return f"• [{kind}] {link} — `{size_text}`{dims}{spoiler} — `{ct or 'unknown'}`"

    def _attachment_lines(self, message: discord.Message) -> List[str]:
        return [self._attachment_line(self._attachment_dict(a)) for a in message.attachments]

    def _attachment_lines_from_snap(self, atts: List[Dict[str, Any]]) -> List[str]:
        return [self._attachment_line(a) for a in (atts or [])]

    def _first_image_url(self, message: discord.Message) -> Optional[str]:
        """Prefer proxy_url (slightly more resilient) then original url."""
        for a in message.attachments:
            if self._is_image_att(a.filename or "", a.content_type):
                return getattr(a, "proxy_url", None) or a.url
        for e in message.embeds:
            if e.image and e.image.url:
                return e.image.url
            if e.thumbnail and e.thumbnail.url:
                return e.thumbnail.url
        return None

    def _first_image_url_from_snap(self, snap: Dict[str, Any]) -> Optional[str]:
        for a in snap.get("attachments") or []:
            if self._is_image_att(a.get("filename") or "", a.get("content_type")):
                return a.get("proxy_url") or a.get("url")
        return snap.get("image_url")

    def _has_image_attachment(self, atts: List[Dict[str, Any]]) -> bool:
        for a in atts or []:
            if self._is_image_att(a.get("filename") or "", a.get("content_type")):
                return True
        return False

    def _snapshot(self, message: discord.Message) -> Dict[str, Any]:
        author = message.author
        atts = [self._attachment_dict(a) for a in message.attachments]
        stickers = []
        for s in getattr(message, "stickers", []) or []:
            stickers.append({
                "id": getattr(s, "id", None),
                "name": getattr(s, "name", None),
                "url": getattr(s, "url", None),
                "format": str(getattr(s, "format", "")),
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
            "stickers": stickers,
            "image_url": self._first_image_url(message),
            "has_image": any(
                self._is_image_att(a.filename or "", a.content_type) for a in message.attachments
            ),
            "has_video": any(
                self._is_video_att(a.filename or "", a.content_type) for a in message.attachments
            ),
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

    # ── history backfill (no SQL — pure memory recovery after restart) ────────

    def _backfill_channel_ids(self) -> List[int]:
        """Optional whitelist via MESSAGE_CACHE_CHANNELS=id1,id2,... Otherwise all text channels."""
        raw = (os.getenv("MESSAGE_CACHE_CHANNELS") or "").strip()
        if not raw:
            return []
        ids: List[int] = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

    async def _backfill_history(self) -> None:
        """
        After restart: pull recent messages from text channels into the in-memory cache.
        This recovers content for messages that were sent while the bot was offline
        (as long as they still exist when we start). No SQL, no disk.
        """
        if BACKFILL_PER_CHANNEL <= 0:
            logger.info("Message cache backfill disabled (MESSAGE_CACHE_BACKFILL=0)")
            self._backfill_done = True
            return

        await self.bot.wait_until_ready()
        # small delay so other cogs finish setup
        await asyncio.sleep(3)

        guild_id = self.bot.config.get("GUILD_ID")
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if not guild and self.bot.guilds:
            guild = self.bot.guilds[0]
        if not guild:
            logger.warning("Backfill skipped: no guild available")
            self._backfill_done = True
            return

        ignore = self._ignore_id()
        whitelist = set(self._backfill_channel_ids())
        channels: List[discord.TextChannel] = []
        for ch in guild.text_channels:
            if ignore and ch.id == ignore:
                continue
            if whitelist and ch.id not in whitelist:
                continue
            # skip channels the bot cannot read
            me = guild.me
            if me is None:
                continue
            perms = ch.permissions_for(me)
            if not (perms.view_channel and perms.read_message_history):
                continue
            channels.append(ch)

        # Prefer more active channels first (rough heuristic: position / category order is fine)
        total_cached = 0
        errors = 0
        logger.info(
            "Message cache backfill starting: %d channels × up to %d msgs (cache limit %d)",
            len(channels),
            BACKFILL_PER_CHANNEL,
            MESSAGE_CACHE_SIZE,
        )

        for ch in channels:
            if len(self._msg_cache) >= MESSAGE_CACHE_SIZE:
                logger.info("Backfill stopped early — cache full (%d)", len(self._msg_cache))
                break
            try:
                count = 0
                async for msg in ch.history(limit=BACKFILL_PER_CHANNEL):
                    if msg.author and msg.author.bot:
                        continue
                    if msg.id not in self._msg_cache:
                        self._cache_put(msg)
                        count += 1
                        total_cached += 1
                    if len(self._msg_cache) >= MESSAGE_CACHE_SIZE:
                        break
                if count:
                    logger.debug("Backfill %s: +%d messages", ch.name, count)
            except discord.Forbidden:
                errors += 1
                logger.debug("Backfill forbidden in #%s", ch.name)
            except discord.HTTPException as e:
                errors += 1
                logger.warning("Backfill HTTP error in #%s: %s", ch.name, e)
                # gentle backoff on rate limit
                if getattr(e, "status", None) == 429:
                    await asyncio.sleep(2)
            except Exception:
                errors += 1
                logger.exception("Backfill failed in #%s", ch.name)
            # tiny pause between channels to stay under rate limits
            await asyncio.sleep(0.35)

        self._backfill_done = True
        logger.info(
            "Message cache backfill done: +%d msgs | cache size=%d | errors=%d",
            total_cached,
            len(self._msg_cache),
            errors,
        )

    @commands.Cog.listener()
    async def on_ready(self):
        # Start backfill once per process lifetime
        if self._backfill_done or (self._backfill_task and not self._backfill_task.done()):
            return
        self._backfill_task = asyncio.create_task(self._backfill_history())

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
                f"Cache size: `{len(self._msg_cache)}` / `{MESSAGE_CACHE_SIZE}`\n"
                f"Backfill: `{'done' if self._backfill_done else 'running/pending'}` "
                f"(limit/channel: `{BACKFILL_PER_CHANNEL}`)\n"
                f"discord.py max_messages: `{getattr(self.bot, 'max_messages', '?')}`"
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Bova's Bot · Message Log Test · pure in-memory (no SQL)")
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
        has_image: bool = False,
        has_video: bool = False,
        stickers: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if len(content) > 900:
            content = content[:897] + "..."

        # Clear signal when the message was media-only
        if (not content or content == "*No text content*") and (has_image or has_video or atts):
            media_bits = []
            if has_image:
                media_bits.append("📷 image")
            if has_video:
                media_bits.append("🎬 video")
            if not media_bits and atts:
                media_bits.append("📎 file")
            content = f"*No text — message contained {' + '.join(media_bits)}*"

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.from_rgb(255, 70, 90),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Channel", value=channel_mention, inline=True)
        embed.add_field(name="Author", value=author_value, inline=True)
        embed.add_field(name="Message ID", value=f"`{message_id}`", inline=True)
        embed.add_field(name="Content", value=content or "*No text content*", inline=False)

        if has_image or has_video:
            flags = []
            if has_image:
                flags.append("📷 **Image was attached**")
            if has_video:
                flags.append("🎬 **Video was attached**")
            flags.append(
                "_Discord CDN links expire after deletion — preview may not load._"
            )
            embed.add_field(
                name="Media",
                value="\n".join(flags),
                inline=False,
            )

        if atts:
            embed.add_field(
                name="Attachments (details)",
                value="\n".join(atts)[:1000],
                inline=False,
            )

        if stickers:
            lines = []
            for s in stickers[:5]:
                name = s.get("name") or "sticker"
                url = s.get("url")
                if url:
                    lines.append(f"• [{name}]({url})")
                else:
                    lines.append(f"• `{name}`")
            if lines:
                embed.add_field(name="Stickers", value="\n".join(lines), inline=False)

        # Try to show the image while the CDN still serves it
        if img:
            embed.set_image(url=img)
        if avatar:
            embed.set_thumbnail(url=avatar)

        footer = "Bova's Bot · Message Log"
        if has_image or has_video or atts:
            footer += " · Media links may stop working after deletion"
        embed.set_footer(text=footer)

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
        has_image = any(
            self._is_image_att(a.filename or "", a.content_type) for a in message.attachments
        )
        has_video = any(
            self._is_video_att(a.filename or "", a.content_type) for a in message.attachments
        )
        stickers = []
        for s in getattr(message, "stickers", []) or []:
            stickers.append({
                "name": getattr(s, "name", None),
                "url": getattr(s, "url", None),
            })

        await self._send_delete_embed(
            channel_mention=channel_mention,
            author_value=author_value,
            message_id=message.id,
            content=content,
            atts=atts,
            img=img,
            avatar=avatar,
            has_image=has_image,
            has_video=has_video,
            stickers=stickers or None,
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """
        Fallback when message is NOT in discord.py cache.
        Style v2.2: only log when we have real content (our in-memory snapshot).
        Never spam "Content not available" embeds — if we don't know the message, stay silent.
        """
        if not payload.guild_id:
            return
        if payload.channel_id == self._ignore_id():
            return
        # Already handled by on_message_delete (or a previous raw) → skip
        if payload.message_id in self._delete_logged:
            return

        snap = self._msg_cache.pop(payload.message_id, None)
        if not snap:
            # Same as old v2.2: no cache → no log (avoids incomplete "uncached" embeds)
            return
        if snap.get("author_bot"):
            return

        self._mark_delete_logged(payload.message_id)

        channel = self.bot.get_channel(payload.channel_id)
        channel_mention = channel.mention if channel else f"`#{payload.channel_id}`"
        content = (snap.get("content") or "").strip() or "*No text content*"
        author_value = f"{snap.get('author_mention', 'Unknown')}\n`{snap.get('author_id', '—')}`"
        snap_atts = snap.get("attachments") or []
        atts = self._attachment_lines_from_snap(snap_atts)
        img = self._first_image_url_from_snap(snap)
        avatar = snap.get("author_avatar")
        has_image = bool(snap.get("has_image")) or self._has_image_attachment(snap_atts)
        has_video = bool(snap.get("has_video")) or any(
            self._is_video_att(a.get("filename") or "", a.get("content_type"))
            for a in snap_atts
        )

        await self._send_delete_embed(
            channel_mention=channel_mention,
            author_value=author_value,
            message_id=payload.message_id,
            content=content,
            atts=atts,
            img=img,
            avatar=avatar,
            has_image=has_image,
            has_video=has_video,
            stickers=snap.get("stickers") or None,
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
