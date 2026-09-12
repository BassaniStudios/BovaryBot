"""
Storage helpers — SQLite primary (utils.db), with optional JSON mirror.

API remains load_json / save_json so all existing cogs keep working.
On first use, legacy data/*.json files are migrated into bovary.db.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from utils import db as sqldb

logger = logging.getLogger("bovary_bot.storage")

DATA_DIR = sqldb.DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

# When true, also write a .json mirror next to the DB (useful for manual inspection)
MIRROR_JSON = os.getenv("STORAGE_MIRROR_JSON", "false").lower() in ("1", "true", "yes")

_bootstrapped = False


def _bootstrap() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    try:
        sqldb.get_connection()
        n = sqldb.migrate_json_to_sql()
        if n:
            logger.info("Migrated %d JSON document(s) into SQLite", n)
    except Exception:
        logger.exception("Storage bootstrap failed")
    _bootstrapped = True


def _path(name: str) -> Path:
    return DATA_DIR / name


def load_json(name: str, default: Any = None) -> Any:
    """Load document from SQLite (key = name without .json). Falls back to file if needed."""
    _bootstrap()
    try:
        data = sqldb.kv_get(name, None)
        if data is not None:
            return data
    except Exception:
        logger.exception("SQLite load failed for %s — trying file", name)

    # Fallback: legacy file
    path = _path(name if name.endswith(".json") else f"{name}.json")
    if not path.exists():
        path = _path(name)
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            sqldb.kv_set(name, data)
        except Exception:
            pass
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load %s: %s — trying .bak", name, e)
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            try:
                with open(bak, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return default if default is not None else {}


def save_json(name: str, data: Any) -> None:
    """Persist document to SQLite. Optionally mirror to JSON file."""
    _bootstrap()
    try:
        sqldb.kv_set(name, data)
    except Exception:
        logger.exception("SQLite save failed for %s — falling back to file", name)
        _save_file(name, data)
        return

    if MIRROR_JSON:
        _save_file(name, data)


def _save_file(name: str, data: Any) -> None:
    path = _path(name if name.endswith(".json") else f"{name}.json")
    try:
        if path.exists():
            bak = path.with_suffix(path.suffix + ".bak")
            try:
                os.replace(path, bak)
            except OSError:
                pass
        fd, tmp_name = tempfile.mkstemp(
            dir=str(DATA_DIR), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.error("Failed to write JSON %s: %s", name, e)


def default_autorole() -> Dict:
    return {
        "title": "Choose your roles",
        "description": "React below to get access to the channels you care about.",
        "color": 0xB450FF,
        "roles": [],
        "message_id": None,
        "channel_id": None,
    }


def default_stats() -> Dict:
    return {
        "messages": {},
        "reactions_given": {},
        "joins": 0,
        "leaves": 0,
        "hourly": {str(i): 0 for i in range(24)},
        "weekday": {str(i): 0 for i in range(7)},
        "media_scores": {},
        "weekly_top": None,
        "last_weekly_reset": None,
    }
