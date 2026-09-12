"""
Backup / export for Render free (ephemeral disk).

- Manual: /backup_export, /db_status
- Automatic: posts bovary.db to BACKUP_CHANNEL_ID every BACKUP_INTERVAL_HOURS
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
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
}


class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_auto: Optional[str] = None
        self._last_size: int = -1
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    def _interval_hours(self) -> float:
        h = self.bot.config.get("BACKUP_INTERVAL_HOURS") or 6
        try:
            return max(1.0, float(h))
        except (TypeError, ValueError):
            return 6.0

    def _backup_channel(self) -> Optional[discord.abc.GuildChannel]:
        cid = self.bot.config.get("BACKUP_CHANNEL_ID") or self.bot.config.get("WEBLOGS_CHANNEL_ID")
        if not cid:
            return None
        return self.bot.get_channel(cid)

    async def _send_db_backup(self, channel: discord.abc.GuildChannel, *, reason: str = "manual") -> bool:
        """Post current SQLite file to channel. Returns True on success."""
        _bootstrap()
        # Checkpoint WAL so the main file is consistent
        try:
            conn = sqldb.get_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        except Exception:
            logger.debug("WAL checkpoint failed", exc_info=True)

        path = sqldb._db_path()
        if not path.exists():
            return False
        data = path.read_bytes()
        size = len(data)
        if size == 0:
            return False
        # Discord limit ~25MB for most bots; skip if too large
        if size > 24_000_000:
            await channel.send(
                f"⚠️ Auto-backup skipped: `bovary.db` is {size:,} bytes (over Discord limit)."
            )
            return False

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"bovary_backup_{ts}.db"
        info = sqldb.db_stats()
        embed = discord.Embed(
            title="📦 SQLite auto-backup",
            description=(
                f"**Reason:** {reason}\n"
                f"**Size:** {size:,} bytes\n"
                f"**KV docs:** {info.get('kv_documents', '?')}\n"
                f"**Audit rows:** {info.get('audit_rows', '?')}\n"
                f"**UTC:** `{ts}`\n\n"
                "_Download and keep this file offline. Render free disk is ephemeral._"
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
        logger.info("Auto-backup sent to #%s (%s bytes, %s)", channel.id, size, reason)
        return True

    @tasks.loop(hours=6)
    async def auto_backup_loop(self):
        # Dynamic interval: change hours via env without restarting loop structure
        # (loop period is fixed at start; we skip if too soon based on last run)
        try:
            channel = self._backup_channel()
            if not channel:
                logger.warning("BACKUP_CHANNEL_ID not set / channel not found — skip auto-backup")
                return
            path = sqldb._db_path()
            size = path.stat().st_size if path.exists() else 0
            # Skip if nothing changed since last auto and size same
            if size == self._last_size and self._last_auto:
                logger.info("Auto-backup skipped (unchanged size %s)", size)
                return
            await self._send_db_backup(channel, reason=f"scheduled every ~{self._interval_hours():g}h")
        except Exception:
            logger.exception("Auto-backup failed")

    @auto_backup_loop.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()
        # Align loop interval to config (discord.py allows changing hours at runtime via change_interval)
        hours = self._interval_hours()
        try:
            self.auto_backup_loop.change_interval(hours=hours)
        except Exception:
            pass
        logger.info("Auto-backup loop ready (every %sh → channel %s)", hours, self.bot.config.get("BACKUP_CHANNEL_ID"))
        # First backup ~2 minutes after ready (don't wait full interval)
        import asyncio
        await asyncio.sleep(120)
        try:
            channel = self._backup_channel()
            if channel:
                await self._send_db_backup(channel, reason="startup")
        except Exception:
            logger.exception("Startup backup failed")

    @app_commands.command(name="backup_now", description="[STAFF] Force an immediate SQLite backup to the backup channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = self._backup_channel()
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
            await interaction.followup.send("❌ Backup failed (empty DB?).", ephemeral=True)

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
        ch = self._backup_channel()
        text = (
            f"**Path:** `{info['path']}`\n"
            f"**KV documents:** {info['kv_documents']}\n"
            f"**Audit rows:** {info['audit_rows']}\n"
            f"**Size:** {info['size_bytes']:,} bytes\n"
            f"**Auto-backup channel:** {ch.mention if ch else 'not set'}\n"
            f"**Interval:** every {self._interval_hours():g}h\n"
            f"**Last auto:** `{self._last_auto or 'none yet'}`"
        )
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="backup_hint", description="How auto-backup works on Render free")
    async def backup_hint(self, interaction: discord.Interaction):
        text = (
            "**Auto-backup is ON.**\n\n"
            f"• Every **{self._interval_hours():g} hours** the bot posts `bovary.db` to the backup channel.\n"
            "• Also runs once ~2 min after startup.\n"
            "• Force now: `/backup_now`\n"
            "• Env: `BACKUP_CHANNEL_ID`, `BACKUP_INTERVAL_HOURS` (default 6)\n\n"
            "Download those messages and keep the files offline. "
            "On Render free, a redeploy can wipe the local disk — the channel history is your recovery copy."
        )
        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
