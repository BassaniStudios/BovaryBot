"""
SQLite storage layer for Bovary Bot.

- Single file: data/bovary.db (WAL mode)
- Drop-in KV API used by storage.load_json / save_json
- Auto-migrates existing *.json from data/ on first boot
- Thread-safe (discord.py + Flask threads)

Env:
  DATABASE_PATH  → override path (default: data/bovary.db)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("bovary_bot.db")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_DB = DATA_DIR / "bovary.db"
_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None
_migrated = False


def _db_path() -> Path:
    raw = os.getenv("DATABASE_PATH", "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_DB


def get_connection() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            path = _db_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(
                str(path),
                check_same_thread=False,
                timeout=30.0,
            )
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA synchronous=NORMAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _init_schema(_conn)
            logger.info("SQLite connected: %s", path)
        return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS kv_store (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            actor_id   INTEGER,
            action     TEXT NOT NULL,
            source     TEXT,
            success    INTEGER NOT NULL DEFAULT 1,
            detail     TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


def close_db() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


# ── Key-value (JSON documents) ──────────────────────────────────────────────

def kv_get(key: str, default: Any = None) -> Any:
    """Load a JSON document by key (e.g. 'stats.json' → key 'stats')."""
    key = _normalize_key(key)
    with _lock:
        conn = get_connection()
        row = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default if default is not None else {}
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            logger.warning("Corrupt KV value for key=%s", key)
            return default if default is not None else {}


def kv_set(key: str, data: Any) -> None:
    key = _normalize_key(key)
    payload = json.dumps(data, ensure_ascii=False)
    with _lock:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO kv_store (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, payload),
        )
        conn.commit()


def kv_delete(key: str) -> None:
    key = _normalize_key(key)
    with _lock:
        conn = get_connection()
        conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        conn.commit()


def kv_keys() -> List[str]:
    with _lock:
        conn = get_connection()
        rows = conn.execute("SELECT key FROM kv_store ORDER BY key").fetchall()
        return [r["key"] for r in rows]


def _normalize_key(name: str) -> str:
    name = name.strip()
    if name.endswith(".json"):
        name = name[:-5]
    return name


# ── Audit (native table, not only KV) ───────────────────────────────────────

def audit_insert(
    *,
    ts: str,
    actor_id: Optional[int],
    action: str,
    source: str = "api",
    success: bool = True,
    detail: Optional[Dict] = None,
) -> None:
    with _lock:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO audit_log (ts, actor_id, action, source, success, detail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                actor_id,
                action,
                source,
                1 if success else 0,
                json.dumps(detail or {}, ensure_ascii=False),
            ),
        )
        # Keep last 2000 rows
        conn.execute(
            """
            DELETE FROM audit_log WHERE id NOT IN (
                SELECT id FROM audit_log ORDER BY id DESC LIMIT 2000
            )
            """
        )
        conn.commit()


def audit_recent(limit: int = 50) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT ts, actor_id, action, source, success, detail
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            try:
                detail = json.loads(r["detail"] or "{}")
            except json.JSONDecodeError:
                detail = {}
            out.append(
                {
                    "ts": r["ts"],
                    "actor_id": r["actor_id"],
                    "action": r["action"],
                    "source": r["source"],
                    "success": bool(r["success"]),
                    "detail": detail,
                }
            )
        return out


# ── Migration from legacy JSON files ────────────────────────────────────────

_JSON_CANDIDATES = [
    "stats.json",
    "namehistory.json",
    "tickets.json",
    "polls.json",
    "sticky.json",
    "customcmds.json",
    "audit.json",
    "autorole.json",
    "autofeeds.json",
    "meets.json",
    "lastfm.json",
    "cooldowns.json",
    "boost.json",
    "weblogs.json",
]


def migrate_json_to_sql(force: bool = False) -> int:
    """
    Import data/*.json into kv_store if not already present.
    Returns number of files imported.
    """
    global _migrated
    if _migrated and not force:
        return 0

    with _lock:
        conn = get_connection()
        flag = conn.execute(
            "SELECT value FROM meta WHERE key = 'json_migrated'"
        ).fetchone()
        if flag and flag["value"] == "1" and not force:
            _migrated = True
            return 0

        imported = 0
        for fname in _JSON_CANDIDATES:
            path = DATA_DIR / fname
            if not path.exists():
                continue
            key = _normalize_key(fname)
            existing = conn.execute(
                "SELECT 1 FROM kv_store WHERE key = ?", (key,)
            ).fetchone()
            if existing and not force:
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                payload = json.dumps(data, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO kv_store (key, value, updated_at)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, payload),
                )
                imported += 1
                logger.info("Migrated %s → SQLite key '%s'", fname, key)
            except Exception as e:
                logger.warning("Skip migrate %s: %s", fname, e)

        # Migrate audit.json entries into audit_log table
        audit_path = DATA_DIR / "audit.json"
        if audit_path.exists():
            try:
                with open(audit_path, "r", encoding="utf-8") as f:
                    adata = json.load(f)
                entries = adata.get("entries") or []
                count_before = conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]
                if count_before == 0 and entries:
                    for e in entries[-2000:]:
                        conn.execute(
                            """
                            INSERT INTO audit_log (ts, actor_id, action, source, success, detail)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                e.get("ts") or "",
                                e.get("actor_id"),
                                e.get("action") or "unknown",
                                e.get("source") or "api",
                                1 if e.get("success", True) else 0,
                                json.dumps(e.get("detail") or {}, ensure_ascii=False),
                            ),
                        )
                    logger.info("Migrated %d audit entries into audit_log", len(entries[-2000:]))
            except Exception as e:
                logger.warning("Audit migrate failed: %s", e)

        conn.execute(
            """
            INSERT INTO meta (key, value) VALUES ('json_migrated', '1')
            ON CONFLICT(key) DO UPDATE SET value = '1'
            """
        )
        conn.commit()
        _migrated = True
        if imported:
            logger.info("JSON→SQL migration complete (%d documents)", imported)
        return imported


def export_kv_to_json(key: str) -> Optional[bytes]:
    """Export one KV document as pretty JSON bytes (for /backup_export)."""
    key = _normalize_key(key)
    data = kv_get(key, None)
    if data is None:
        return None
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def db_stats() -> Dict[str, Any]:
    with _lock:
        conn = get_connection()
        keys = conn.execute("SELECT COUNT(*) AS c FROM kv_store").fetchone()["c"]
        audits = conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]
        size = 0
        path = _db_path()
        if path.exists():
            size = path.stat().st_size
        return {
            "path": str(path),
            "kv_documents": keys,
            "audit_rows": audits,
            "size_bytes": size,
        }
