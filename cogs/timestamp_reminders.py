"""Automatic reminders for Discord relative timestamps.

Detects <t:UNIX:R> in guild messages and embeds, persists pending reminders
in SQLite, and sends a configurable reminder in the SAME channel shortly before
the event. Staff can configure it with slash commands or the web panel.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.timestamp_reminders")
REMINDERS_FILE = "timestamp_reminders.json"
CONFIG_FILE = "timestamp_reminder_config.json"
TIMESTAMP_RE = re.compile(r"<t:\s*(\d{9,12})\s*:\s*[rR]\s*>")
MAX_REMINDERS = 1000
REMINDER_MARKER = "⏰ **Reminder:**"
CLEANUP_AFTER_SECONDS = 14 * 24 * 3600
DEFAULT_TEXT = (
    "⏰ **Reminder:** this announcement starts in approximately **{minutes} minutes** — "
    "<t:{timestamp}:R>.\n[Open announcement]({jump_url})"
)


class TimestampReminders(commands.Cog):
    """Detect <t:...:R> timestamps and send automatic reminders."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders: List[Dict[str, Any]] = load_json(REMINDERS_FILE, [])
        if not isinstance(self.reminders, list):
            self.reminders = []
        self._config = self._load_config()
        self._apply_config()
        self._normalize()
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()
        self._save()

    def _load_config(self) -> Dict[str, Any]:
        raw = load_json(CONFIG_FILE, {})
        if not isinstance(raw, dict):
            raw = {}
        return {
            "enabled": bool(raw.get("enabled", self.bot.config.get("TIMESTAMP_REMINDER_ENABLED", True))),
            "minutes": self._clamp_minutes(raw.get("minutes", self.bot.config.get("TIMESTAMP_REMINDER_MINUTES", 30))),
            "text": str(raw.get("text") or self.bot.config.get("TIMESTAMP_REMINDER_TEXT") or DEFAULT_TEXT)[:1800],
        }

    @staticmethod
    def _clamp_minutes(value: Any) -> int:
        try:
            return max(1, min(1440, int(value)))
        except (TypeError, ValueError):
            return 30

    def _apply_config(self) -> None:
        self.bot.config["TIMESTAMP_REMINDER_ENABLED"] = bool(self._config["enabled"])
        self.bot.config["TIMESTAMP_REMINDER_MINUTES"] = int(self._config["minutes"])
        self.bot.config["TIMESTAMP_REMINDER_TEXT"] = str(self._config["text"])

    def _save_config(self) -> None:
        save_json(CONFIG_FILE, self._config)
        self._apply_config()

    def get_config(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self._config["enabled"]),
            "minutes": int(self._config["minutes"]),
            "text": str(self._config["text"]),
            "pending": sum(1 for x in self.reminders if not x.get("reminder_sent")),
        }

    def configure(self, *, enabled: bool | None = None, minutes: int | None = None, text: str | None = None) -> Dict[str, Any]:
        if enabled is not None:
            self._config["enabled"] = bool(enabled)
        if minutes is not None:
            self._config["minutes"] = self._clamp_minutes(minutes)
        if text is not None:
            cleaned = text.strip()[:1800]
            if cleaned:
                self._config["text"] = cleaned
        self._save_config()
        return self.get_config()

    def _enabled(self) -> bool:
        return bool(self._config.get("enabled", True))

    def _minutes(self) -> int:
        return self._clamp_minutes(self._config.get("minutes", 30))

    def _text(self, timestamp: int, jump_url: str) -> str:
        template = str(self._config.get("text") or DEFAULT_TEXT)
        try:
            return template.format(
                minutes=self._minutes(),
                timestamp=timestamp,
                jump_url=jump_url,
            )[:2000]
        except (KeyError, ValueError):
            logger.warning("Invalid timestamp reminder template; using default")
            return DEFAULT_TEXT.format(minutes=self._minutes(), timestamp=timestamp, jump_url=jump_url)

    def _save(self) -> None:
        save_json(REMINDERS_FILE, self.reminders)

    def _normalize(self) -> None:
        now = datetime.now(timezone.utc).timestamp()
        clean: List[Dict[str, Any]] = []
        seen = set()
        for item in self.reminders:
            if not isinstance(item, dict):
                continue
            try:
                message_id = int(item.get("message_id"))
                channel_id = int(item.get("channel_id"))
                timestamp = int(item.get("timestamp"))
            except (TypeError, ValueError):
                continue
            if timestamp < now - CLEANUP_AFTER_SECONDS:
                continue
            key = (message_id, timestamp)
            if key in seen:
                continue
            seen.add(key)
            item["message_id"] = message_id
            item["channel_id"] = channel_id
            item["timestamp"] = timestamp
            item["reminder_sent"] = bool(item.get("reminder_sent", False))
            clean.append(item)
        self.reminders = sorted(clean, key=lambda x: x["timestamp"])[-MAX_REMINDERS:]

    @staticmethod
    def _timestamp_text(message: discord.Message) -> str:
        parts: List[str] = [message.content or ""]
        for embed in message.embeds:
            parts.extend([
                embed.title or "",
                embed.description or "",
                getattr(embed.footer, "text", "") or "",
                getattr(embed.author, "name", "") or "",
            ])
            for field in embed.fields:
                parts.append(getattr(field, "name", "") or "")
                parts.append(getattr(field, "value", "") or "")
        return "\n".join(parts)

    @classmethod
    def _extract_timestamps(cls, message: discord.Message) -> List[int]:
        text = cls._timestamp_text(message)
        values = []
        seen = set()
        for match in TIMESTAMP_RE.finditer(text):
            ts = int(match.group(1))
            if 1 <= ts <= 4102444800 and ts not in seen:
                values.append(ts)
                seen.add(ts)
        return values

    def _upsert_message(self, message: discord.Message) -> bool:
        if not self._enabled() or not message.guild:
            return False
        timestamps = self._extract_timestamps(message)
        now = datetime.now(timezone.utc).timestamp()
        valid_future = [ts for ts in timestamps if ts > now]
        message_id = message.id
        changed = False

        old = self.reminders
        new = [
            item for item in old
            if not (
                item.get("message_id") == message_id
                and not item.get("reminder_sent")
                and item.get("timestamp") not in valid_future
            )
        ]
        if len(new) != len(old):
            changed = True
        self.reminders = new

        existing = {(item.get("message_id"), item.get("timestamp")) for item in self.reminders}
        for ts in valid_future:
            key = (message_id, ts)
            if key in existing:
                continue
            self.reminders.append({
                "guild_id": message.guild.id,
                "channel_id": message.channel.id,
                "message_id": message.id,
                "author_id": message.author.id if message.author else None,
                "timestamp": ts,
                "reminder_sent": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            existing.add(key)
            changed = True

        if len(self.reminders) > MAX_REMINDERS:
            self.reminders = sorted(self.reminders, key=lambda x: x.get("timestamp", 0))[-MAX_REMINDERS:]
            changed = True
        return changed

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if REMINDER_MARKER in (message.content or ""):
            return
        try:
            if self._upsert_message(message):
                self._save()
        except Exception:
            logger.exception("Failed to register timestamp reminder from message %s", getattr(message, "id", "?"))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild:
            return
        if REMINDER_MARKER in (after.content or ""):
            return
        try:
            if self._timestamp_text(before) == self._timestamp_text(after):
                return
            if self._upsert_message(after):
                self._save()
        except Exception:
            logger.exception("Failed to update timestamp reminder for message %s", getattr(after, "id", "?"))

    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        if not self._enabled():
            return

        now = datetime.now(timezone.utc).timestamp()
        target_seconds = self._minutes() * 60
        lower_bound = max(0, target_seconds - 90)
        upper_bound = target_seconds
        changed = False

        for item in list(self.reminders):
            if item.get("reminder_sent"):
                continue
            try:
                start = int(item.get("timestamp"))
                channel_id = int(item.get("channel_id"))
                message_id = int(item.get("message_id"))
            except (TypeError, ValueError):
                continue

            delta = start - now
            if not (lower_bound <= delta <= upper_bound):
                continue

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

            try:
                jump_url = f"https://discord.com/channels/{item.get('guild_id')}/{channel_id}/{message_id}"
                await channel.send(
                    self._text(start, jump_url),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                item["reminder_sent"] = True
                item["reminder_sent_at"] = datetime.now(timezone.utc).isoformat()
                changed = True
                logger.info("Timestamp reminder sent: message=%s channel=%s start=%s", message_id, channel_id, start)
            except (discord.Forbidden, discord.HTTPException):
                logger.exception("Failed to send timestamp reminder for message %s", message_id)

        cutoff = now - CLEANUP_AFTER_SECONDS
        before = len(self.reminders)
        self.reminders = [item for item in self.reminders if int(item.get("timestamp", 0) or 0) >= cutoff]
        if len(self.reminders) != before:
            changed = True
        if changed:
            self._save()

    @reminder_loop.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="timestamp_reminder_config", description="Configure automatic timestamp reminders")
    @app_commands.describe(
        enabled="Enable or disable automatic reminders",
        minutes="Minutes before the event (1-1440)",
        text="Optional English reminder template; {minutes}, {timestamp}, {jump_url} are supported",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def timestamp_reminder_config(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        minutes: app_commands.Range[int, 1, 1440] | None = None,
        text: str | None = None,
    ):
        cfg = self.configure(enabled=enabled, minutes=minutes, text=text)
        state = "ON" if cfg["enabled"] else "OFF"
        await interaction.response.send_message(
            f"✅ Timestamp reminders: **{state}** · **{cfg['minutes']} min** before\n"
            f"Template: `{cfg['text']}`",
            ephemeral=True,
        )

    @app_commands.command(name="timestamp_reminder_status", description="Show automatic timestamp reminder status")
    async def timestamp_reminder_status(self, interaction: discord.Interaction):
        cfg = self.get_config()
        state = "ON" if cfg["enabled"] else "OFF"
        await interaction.response.send_message(
            f"⏰ **Timestamp Reminder**\nStatus: **{state}**\n"
            f"Trigger: **{cfg['minutes']} minutes** before\n"
            f"Pending reminders: **{cfg['pending']}**\n"
            f"Language: **English**",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TimestampReminders(bot))
