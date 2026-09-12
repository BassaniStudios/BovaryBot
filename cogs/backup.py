"""
Backup / restore for Render free (ephemeral disk).

- Automatic: posts bovary.db to BACKUP_CHANNEL_ID on the configured interval.
- Automatic restore: on a fresh/empty deployment, downloads the newest valid
  bovary_backup_*.db from the backup channel before the other cogs load.
- Safety: a database containing data is never overwritten by an automatic restore.
- Manual: /backup_now, /backup_export, /db_status, /backup_hint
"""
from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import DATA_DIR, _bootstrap
from utils import db as sqldb

logger = logging.getLogger("bovary_bot.backup")

KV_NAMES = {
    "stats": "stats",
    "namehistory": "namehistory",
    "tickets": "tickets",
    "polls": "polls",
    "sticky": "sticky",
    "customcmds": "customcmds",
    "autorole": "autorole",
    "autofeeds": "autofeeds",
    "meets": "meets",
    "lastfm": "lastfm",
    "cooldowns": "cooldowns",
    "boost": "boost",
    "weblogs": "weblogs",
    "timestamp_reminder_config": "timestamp_reminder_config",
    "timestamp_reminders": "timestamp_reminders",
    "dm_inbox": "dm_inbox",
}

BACKUP_PREFIX = "bovary_backup_"
BACKUP_SUFFIX = ".db"
MAX_DISCORD_FILE_SIZE = 24_000_000


class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_auto: Optional[str] = None
        self._last_size: int = -1
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    def _interval_hours(self) -> float:
        h = self.bot.config.get("BACKUP_INTERVAL_HOURS") or 24
        try:
            return max(1.0, float(h))
        except (TypeError, ValueError):
            return 24.0

    def _backup_channel(self) -> Optional[discord.abc.GuildChannel]:
        cid = self.bot.config.get("BACKUP_CHANNEL_ID") or self.bot.config.get("WEBLOGS_CHANNEL_ID")
        if not cid:
            return None
        return self.bot.get_channel(cid)

    async def _get_backup_channel(self) -> Optional[discord.abc.Messageable]:
        """Resolve the backup channel even during setup_hook, before cache is warm."""
        channel = self._backup_channel()
        if channel is not None:
            return channel
        cid = self.bot.config.get("BACKUP_CHANNEL_ID") or self.bot.config.get("WEBLOGS_CHANNEL_ID")
        if not cid:
            return None
        try:
            channel = await self.bot.fetch_channel(cid)
            if hasattr(channel, "history"):
                return channel
        except Exception:
            logger.exception("Could not fetch backup channel %s", cid)
        return None

    @staticmethod
    def _sqlite_file_status(path: Path) -> tuple[bool, int, int, str]:
        """Return (usable, kv_count, audit_count, reason) without using the app DB connection."""
        if not path.exists():
            return False, 0, 0, "file does not exist"
        try:
            if path.stat().st_size < 100:
                return False, 0, 0, "file is empty or too small"
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if str(integrity).lower() != "ok":
                    return False, 0, 0, f"integrity_check={integrity}"
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "kv_store" not in tables or "audit_log" not in tables:
                    return False, 0, 0, "expected SQLite tables are missing"
                kv = int(conn.execute("SELECT COUNT(*) FROM kv_store").fetchone()[0])
                audit = int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])
                return True, kv, audit, "ok"
            finally:
                conn.close()
        except Exception as exc:
            return False, 0, 0, f"SQLite validation failed: {exc}"

    @classmethod
    def _db_has_data(cls, path: Path) -> bool:
        usable, kv, audit, reason = cls._sqlite_file_status(path)
        if usable:
            return kv > 0 or audit > 0
        # A corrupt database is not considered safe/usable. It may be recovered
        # from Discord, but it is first preserved as a local .pre_restore copy.
        if path.exists() and path.stat().st_size > 0:
            logger.warning("Local database is not usable: %s", reason)
        return False

    @staticmethod
    def _backup_sort_key(filename: str) -> tuple[int, str]:
        # Current names are bovary_backup_YYYYMMDD_HHMMSS.db. The fallback keeps
        # lexical ordering for any unexpected but correctly-prefixed filenames.
        stamp = filename[len(BACKUP_PREFIX):-len(BACKUP_SUFFIX)]
        try:
            return (1, datetime.strptime(stamp, "%Y%m%d_%H%M%S").strftime("%Y%m%d%H%M%S"))
        except ValueError:
            return (0, stamp)

    async def _find_latest_valid_backup(self, channel: discord.abc.Messageable) -> Optional[tuple[discord.Attachment, str]]:
        """Find the newest valid backup attachment, newest Discord message first."""
        if not hasattr(channel, "history"):
            return None

        checked = 0
        async for message in channel.history(limit=None):
            checked += 1
            candidates = [
                a for a in message.attachments
                if a.filename.startswith(BACKUP_PREFIX) and a.filename.endswith(BACKUP_SUFFIX)
            ]
            if not candidates:
                continue

            # The first matching message is the newest backup message. If it has
            # multiple matching attachments, prefer the newest-looking filename.
            candidates.sort(key=lambda a: self._backup_sort_key(a.filename), reverse=True)
            for attachment in candidates:
                if attachment.size and attachment.size > MAX_DISCORD_FILE_SIZE:
                    logger.warning("Skipping oversized backup %s (%s bytes)", attachment.filename, attachment.size)
                    continue
                try:
                    data = await attachment.read()
                except Exception:
                    logger.exception("Could not download backup attachment %s", attachment.filename)
                    continue

                valid, kv, audit, reason = await self._validate_backup_bytes(data)
                if valid:
                    logger.info(
                        "Found valid backup %s (KV=%s, audit=%s) after checking %s message(s)",
                        attachment.filename, kv, audit, checked,
                    )
                    return attachment, data
                logger.warning("Skipping invalid backup %s: %s", attachment.filename, reason)

        logger.warning("No valid bovary database backup found in backup channel after checking %s message(s)", checked)
        return None

    @staticmethod
    async def _validate_backup_bytes(data: bytes) -> tuple[bool, int, int, str]:
        """Validate a downloaded SQLite database using a temporary file."""
        if len(data) < 100:
            return False, 0, 0, "downloaded file is empty or too small"
        if data[:16] != b"SQLite format 3\x00":
            return False, 0, 0, "not a SQLite database"

        fd, temp_name = tempfile.mkstemp(prefix="bovary-restore-", suffix=".db")
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            temp_path.write_bytes(data)
            valid, kv, audit, reason = Backup._sqlite_file_status(temp_path)
            return valid, kv, audit, reason
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    async def restore_latest_backup_if_needed(self) -> bool:
        """
        Restore the newest valid Discord backup only when the local DB is absent,
        empty, or unusable. Existing populated data is never overwritten.
        """
        path = sqldb._db_path()

        # IMPORTANT: do this before _bootstrap()/get_connection() so a fresh
        # deployment does not create an empty SQLite database and then mistake
        # its schema for real user data.
        if self._db_has_data(path):
            usable, kv, audit, _ = self._sqlite_file_status(path)
            logger.info(
                "Automatic restore skipped: local database already contains data (KV=%s, audit=%s)",
                kv, audit,
            )
            return False

        channel = await self._get_backup_channel()
        if not channel:
            logger.warning("Automatic restore skipped: backup channel is not configured/accessible")
            return False

        found = await self._find_latest_valid_backup(channel)
        if not found:
            return False

        attachment, data = found

        # Re-check immediately before replacement. This protects against a
        # concurrent initialization path creating/populating the DB while the
        # Discord download was in progress.
        if self._db_has_data(path):
            logger.warning("Automatic restore aborted: local DB gained data while backup was downloading")
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_restore = path.with_name(f".{path.name}.restore.tmp")
        preserved = None
        try:
            temp_restore.write_bytes(data)
            valid, kv, audit, reason = self._sqlite_file_status(temp_restore)
            if not valid:
                logger.error("Downloaded backup failed final validation: %s", reason)
                return False

            # Preserve anything that existed locally, even if corrupt, before
            # replacement. This gives a recovery copy instead of silently losing it.
            if path.exists():
                preserved = path.with_name(
                    f"{path.name}.pre_restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bak"
                )
                os.replace(path, preserved)

            # Remove stale WAL/SHM sidecars from an interrupted local SQLite DB.
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{path}{suffix}")
                if sidecar.exists():
                    try:
                        sidecar.unlink()
                    except OSError:
                        logger.warning("Could not remove stale SQLite sidecar %s", sidecar)

            os.replace(temp_restore, path)
            logger.info(
                "Automatic SQLite restore completed from %s (KV=%s, audit=%s, local=%s)",
                attachment.filename, kv, audit, path,
            )
            return True
        except Exception:
            logger.exception("Automatic SQLite restore failed from %s", attachment.filename)
            # If replacement failed after moving the original aside, restore it.
            if not path.exists() and preserved and preserved.exists():
                try:
                    os.replace(preserved, path)
                    logger.info("Original local database restored after failed recovery")
                except Exception:
                    logger.exception("Could not roll back preserved local database")
            return False
        finally:
            try:
                temp_restore.unlink()
            except OSError:
                pass

    async def _send_db_backup(self, channel: discord.abc.GuildChannel, *, reason: str = "manual") -> bool:
        """Post current SQLite file to channel. Returns True on success."""
        _bootstrap()
        try:
            conn = sqldb.get_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        except Exception:
            logger.debug("WAL checkpoint failed", exc_info=True)

        path = sqldb._db_path()
        valid, kv, audit, validation_reason = self._sqlite_file_status(path)
        if not valid:
            logger.warning("Backup refused because local DB is invalid: %s", validation_reason)
            return False

        data = path.read_bytes()
        size = len(data)
        if size > MAX_DISCORD_FILE_SIZE:
            await channel.send(
                f"⚠️ Auto-backup skipped: `bovary.db` is {size:,} bytes (over Discord limit)."
            )
            return False

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{BACKUP_PREFIX}{ts}{BACKUP_SUFFIX}"
        embed = discord.Embed(
            title="📦 SQLite auto-backup",
            description=(
                f"**Reason:** {reason}\n"
                f"**Size:** {size:,} bytes\n"
                f"**KV docs:** {kv}\n"
                f"**Audit rows:** {audit}\n"
                f"**UTC:** `{ts}`\n\n"
                "_This backup is used automatically after a fresh Render deploy._"
            ),
            color=discord.Color.from_rgb(180, 80, 255),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Bova's Bot · Auto Backup")
        await channel.send(
            embed=embed,
            file=discord.File(io.BytesIO(data), filename=filename),
        )
        self._last_auto = ts
        self._last_size = size
        logger.info("Auto-backup sent to #%s (%s bytes, %s reason)", channel.id, size, reason)
        return True

    @tasks.loop(hours=24)
    async def auto_backup_loop(self):
        try:
            channel = await self._get_backup_channel()
            if not channel:
                logger.warning("BACKUP_CHANNEL_ID not set / channel not found — skip auto-backup")
                return
            # Always create the scheduled backup. File size is not a reliable
            # change detector: a SQLite DB can change without changing size.
            await self._send_db_backup(channel, reason=f"scheduled every ~{self._interval_hours():g}h")
        except Exception:
            logger.exception("Auto-backup failed")

    @auto_backup_loop.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()
        hours = self._interval_hours()
        try:
            self.auto_backup_loop.change_interval(hours=hours)
        except Exception:
            pass
        logger.info(
            "Auto-backup loop ready (every %sh → channel %s)",
            hours,
            self.bot.config.get("BACKUP_CHANNEL_ID"),
        )
        import asyncio
        await asyncio.sleep(120)
        try:
            channel = await self._get_backup_channel()
            if channel:
                await self._send_db_backup(channel, reason="startup")
        except Exception:
            logger.exception("Startup backup failed")

    @app_commands.command(name="backup_now", description="[STAFF] Force an immediate SQLite backup to the backup channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_backup_channel()
        if not channel:
            await interaction.followup.send(
                "❌ BACKUP_CHANNEL_ID not configured or channel not found.",
                ephemeral=True,
            )
            return
        ok = await self._send_db_backup(channel, reason=f"manual by {interaction.user}")
        if ok:
            await interaction.followup.send(f"✅ Backup posted in {channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Backup failed (invalid or empty DB?).", ephemeral=True)

    @app_commands.command(name="backup_export", description="[STAFF] Export data from SQLite to Discord (ephemeral DM-style)")
    @app_commands.describe(file="Which: stats, namehistory, tickets, polls, sticky, customcmds, audit, db, all")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_export(self, interaction: discord.Interaction, file: str = "all"):
        await interaction.response.defer(ephemeral=True)
        _bootstrap()
        file = file.strip().lower()
        sent = 0

        if file in ("db", "all"):
            path = sqldb._db_path()
            if path.exists():
                try:
                    conn = sqldb.get_connection()
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.commit()
                except Exception:
                    pass
                data = path.read_bytes()
                if 0 < len(data) <= 7_500_000:
                    await interaction.followup.send(
                        "📦 `bovary.db` (SQLite)",
                        file=discord.File(io.BytesIO(data), filename="bovary.db"),
                        ephemeral=True,
                    )
                    sent += 1

        if file == "audit" or file == "all":
            entries = sqldb.audit_recent(500)
            payload = json.dumps({"entries": entries}, indent=2, ensure_ascii=False).encode()
            await interaction.followup.send(
                "📦 `audit.json` (from SQL)",
                file=discord.File(io.BytesIO(payload), filename="audit.json"),
                ephemeral=True,
            )
            sent += 1

        keys = list(KV_NAMES.values()) if file == "all" else ([KV_NAMES[file]] if file in KV_NAMES else [])
        for key in keys:
            raw = sqldb.export_kv_to_json(key)
            if not raw or len(raw) > 7_500_000:
                continue
            await interaction.followup.send(
                f"📦 `{key}.json`",
                file=discord.File(io.BytesIO(raw), filename=f"{key}.json"),
                ephemeral=True,
            )
            sent += 1

        if sent == 0:
            await interaction.followup.send("Nothing to export.", ephemeral=True)
        else:
            await interaction.followup.send(
                f"✅ Exported {sent} item(s). Prefer `/backup_now` for channel archives.",
                ephemeral=True,
            )

    @app_commands.command(name="db_status", description="[STAFF] SQLite storage status")
    @app_commands.checks.has_permissions(administrator=True)
    async def db_status(self, interaction: discord.Interaction):
        _bootstrap()
        info = sqldb.db_stats()
        ch = await self._get_backup_channel()
        valid, kv, audit, reason = self._sqlite_file_status(sqldb._db_path())
        text = (
            f"**Path:** `{info['path']}`\n"
            f"**KV documents:** {info['kv_documents']}\n"
            f"**Audit rows:** {info['audit_rows']}\n"
            f"**Size:** {info['size_bytes']:,} bytes\n"
            f"**SQLite valid:** {'yes' if valid else 'NO — ' + reason}\n"
            f"**Auto-backup channel:** {ch.mention if ch else 'not set'}\n"
            f"**Interval:** every {self._interval_hours():g}h\n"
            f"**Last auto:** `{self._last_auto or 'none yet'}`"
        )
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="backup_hint", description="How auto-backup works on Render free")
    async def backup_hint(self, interaction: discord.Interaction):
        text = (
            "**Auto-backup + auto-restore is ON.**\n\n"
            f"• Every **{self._interval_hours():g} hours** the bot posts `bovary.db` to the backup channel.\n"
            "• Also creates a startup backup ~2 min after the bot becomes ready.\n"
            "• After a fresh Render deploy, an empty/new `bovary.db` automatically restores the newest valid backup.\n"
            "• A local database containing data is never overwritten by automatic recovery.\n"
            "• Force now: `/backup_now`\n\n"
            "You no longer need to manually download `bovary.db` before deploying."
        )
        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
