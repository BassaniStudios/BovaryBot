"""
Supabase Storage helper for persistent SQLite backups.

Env (required for remote persistence):
  SUPABASE_URL              e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY service_role key (server-side only — never expose to panel)
  SUPABASE_BUCKET           default: bovary-backups

Objects:
  bovary/latest.db          always the most recent valid database
  bovary/bovary_backup_YYYYMMDD_HHMMSS.db  historical copies
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("bovary_bot.supabase_storage")

BACKUP_PREFIX = "bovary_backup_"
BACKUP_SUFFIX = ".db"
LATEST_OBJECT = "bovary/latest.db"


def is_configured() -> bool:
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()
    return bool(url and key)


def _client():
    if not is_configured():
        return None
    try:
        from supabase import create_client
    except ImportError:
        logger.error("Package 'supabase' not installed — run: pip install supabase")
        return None
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()
    return create_client(url, key)


def _bucket_name() -> str:
    return (os.getenv("SUPABASE_BUCKET") or "bovary-backups").strip() or "bovary-backups"


def upload_db(path: Path, *, reason: str = "manual") -> Tuple[bool, str]:
    """
    Upload local SQLite file to Supabase Storage.
    Writes both a timestamped object and overwrites bovary/latest.db.
    Returns (ok, message).
    """
    if not path.exists() or path.stat().st_size < 100:
        return False, "local database missing or empty"

    client = _client()
    if client is None:
        return False, "supabase not configured or package missing"

    bucket = _bucket_name()
    data = path.read_bytes()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    historical = f"bovary/{BACKUP_PREFIX}{ts}{BACKUP_SUFFIX}"

    try:
        storage = client.storage.from_(bucket)

        # Historical copy
        storage.upload(
            historical,
            data,
            file_options={
                "content-type": "application/x-sqlite3",
                "upsert": "true",
            },
        )

        # Always keep a stable "latest" pointer for restore
        storage.upload(
            LATEST_OBJECT,
            data,
            file_options={
                "content-type": "application/x-sqlite3",
                "upsert": "true",
            },
        )
        msg = f"uploaded {historical} + {LATEST_OBJECT} ({len(data):,} bytes, reason={reason})"
        logger.info("Supabase Storage: %s", msg)
        return True, msg
    except Exception as e:
        logger.exception("Supabase upload failed")
        return False, str(e)


def download_latest(dest: Path) -> Tuple[bool, str]:
    """
    Download bovary/latest.db into dest.
    Returns (ok, message).
    """
    client = _client()
    if client is None:
        return False, "supabase not configured or package missing"

    bucket = _bucket_name()
    try:
        storage = client.storage.from_(bucket)
        data = storage.download(LATEST_OBJECT)
        if not data or len(data) < 100:
            return False, "downloaded file empty or too small"
        if data[:16] != b"SQLite format 3\x00":
            return False, "downloaded object is not a SQLite database"

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        msg = f"downloaded {LATEST_OBJECT} → {dest} ({len(data):,} bytes)"
        logger.info("Supabase Storage: %s", msg)
        return True, msg
    except Exception as e:
        # Common: object does not exist yet
        logger.warning("Supabase download of %s failed: %s", LATEST_OBJECT, e)
        return False, str(e)


def list_backups(limit: int = 20) -> list:
    """List recent backup objects under bovary/ (best-effort)."""
    client = _client()
    if client is None:
        return []
    try:
        items = client.storage.from_(_bucket_name()).list("bovary")
        if not items:
            return []
        # items are dicts with name, metadata, etc.
        names = []
        for it in items:
            name = it.get("name") if isinstance(it, dict) else getattr(it, "name", None)
            if name and name.startswith(BACKUP_PREFIX) and name.endswith(BACKUP_SUFFIX):
                names.append(f"bovary/{name}")
        names.sort(reverse=True)
        return names[:limit]
    except Exception:
        logger.exception("Supabase list_backups failed")
        return []
