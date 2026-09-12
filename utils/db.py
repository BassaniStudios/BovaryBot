"""
SQLite storage layer for Bovary Bot.

Modes:
  1. Local file  → data/bovary.db (default, WAL mode)
  2. Turso remote → when TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are set

Drop-in KV API used by storage.load_json / save_json.
Auto-migrates existing data/*.json on first boot (local mode).
Thread-safe (discord.py + Flask threads).

Env:
  DATABASE_PATH          override local path (default: data/bovary.db)
  TURSO_DATABASE_URL     e.g. libsql://xxx.turso.io  (enables remote mode)
  TURSO_AUTH_TOKEN       Turso auth token
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
_conn: Optional[Any] = None
_migrated = False
_remote_mode = False


def is_remote() -> bool:
    """True when connected (or configured) for Turso remote SQLite."""
    return _remote_mode or bool(
        (os.getenv("TURSO_DATABASE_URL") or "").strip()
        and (os.getenv("TURSO_AUTH_TOKEN") or "").strip()
    )


def _db_path() -> Path:
    raw = os.getenv("DATABASE_PATH", "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_DB


def _connect_turso():
    """Open a remote Turso / libSQL connection (sqlite3-compatible API)."""
    url = (os.getenv("TURSO_DATABASE_URL") or "").strip()
    token = (os.getenv("TURSO_AUTH_TOKEN") or "").strip()
    if not url or not token:
        raise RuntimeError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN required for remote mode")

    try:
        import libsql
    except ImportError as e:
        raise RuntimeError(
            "Package 'libsql' is required for Turso. Install with: pip install libsql"
        ) from e

    # libsql.connect supports remote URLs with auth_token
    # API is intentionally close to sqlite3
    try:
        conn = libsql.connect(database=url, auth_token=token)
    except TypeError:
        # Older / alternate signature
        conn = libsql.connect(url, auth_token=token)

    # Row factory if supported
    try:
        conn.row_factory = sqlite3.Row
    except Exception:
        pass

    logger.info("Turso (remote SQLite) connected: %s", url.split("?")[0])
    return conn


def get_connection() -> Any:
    global _conn, _remote_mode
    with _lock:
        if _conn is None:
            if is_remote() and (os.getenv("TURSO_DATABASE_URL") or "").strip():
                _conn = _connect_turso()
                _remote_mode = True
                # PRAGMA WAL is local-file oriented; skip or ignore on remote
                try:
                    _conn.execute("PRAGMA foreign_keys=ON")
                except Exception:
                    pass
            else:
                path = _db_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                _conn = sqlite3.connect(
                    str(path),
                    check_same_thread=False,
                    timeout=30.0,
                )
                _conn.row_factory = sqlite3.Row
                try:
                    _conn.execute("PRAGMA journal_mode=WAL")
                    _conn.execute("PRAGMA synchronous=NORMAL")
                    _conn.execute("PRAGMA foreign_keys=ON")
                except Exception:
                    logger.debug("Local PRAGMA setup partial", exc_info=True)
                _remote_mode = False
                logger.info("SQLite connected (local): %s", path)

            _init_schema(_conn)
        return _conn


def _init_schema(conn: Any) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS kv_store (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            actor_id   INTEGER,
            action     TEXT NOT NULL,
            source     TEXT,
            success    INTEGER NOT NULL DEFAULT 1,
            detail     TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC)",
        """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    ]
    # Prefer executescript when available (local sqlite3); fall back to per-statement.
    if hasattr(conn, "executescript"):
        try:
            script = ";\n".join(s.strip().rstrip(";") for s in statements) + ";"
            conn.executescript(script)
            conn.commit()
            return
        except Exception:
            logger.debug("executescript failed, using individual statements", exc_info=True)
    for sql in statements:
        conn.execute(sql)
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
            try:
                raw = row["value"]
            except Exception:
                raw = row[0]
            return json.loads(raw)
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
            def _get(row, key, idx):
                try:
                    return row[key]
                except Exception:
                    try:
                        return row[idx]
                    except Exception:
                        return None
            try:
                detail = json.loads(_get(r, "detail", 5) or "{}")
            except (json.JSONDecodeError, TypeError):
                detail = {}
            out.append(
                {
                    "ts": _get(r, "ts", 0),
                    "actor_id": _get(r, "actor_id", 1),
                    "action": _get(r, "action", 2),
                    "source": _get(r, "source", 3),
                    "success": bool(_get(r, "success", 4)),
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
        row_k = conn.execute("SELECT COUNT(*) AS c FROM kv_store").fetchone()
        row_a = conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()
        def _count(row):
            if row is None:
                return 0
            try:
                return int(row["c"])
            except Exception:
                try:
                    return int(row[0])
                except Exception:
                    return 0
        keys = _count(row_k)
        audits = _count(row_a)
        size = 0
        path = _db_path()
        if not is_remote() and path.exists():
            size = path.stat().st_size
        return {
            "mode": "turso" if is_remote() else "local",
            "path": (os.getenv("TURSO_DATABASE_URL") or "").split("?")[0] if is_remote() else str(path),
            "kv_documents": keys,
            "audit_rows": audits,
            "size_bytes": size,
        }
