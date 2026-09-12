"""
Audit log for panel / API actions.
Primary: SQLite audit_log table.
Also keeps a thin KV mirror for compatibility.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from utils import db as sqldb

logger = logging.getLogger("bovary_bot.audit")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_action(
    *,
    actor_id: Optional[int],
    action: str,
    detail: Optional[Dict[str, Any]] = None,
    source: str = "api",
    success: bool = True,
) -> None:
    """Append an audit entry. Never raises — logging must not break the request."""
    try:
        # Ensure DB is up (also runs JSON migration once)
        from utils.storage import _bootstrap
        _bootstrap()
        sqldb.audit_insert(
            ts=_now_iso(),
            actor_id=actor_id,
            action=action,
            source=source,
            success=success,
            detail=detail or {},
        )
        logger.info(
            "AUDIT %s actor=%s action=%s success=%s detail=%s",
            source,
            actor_id,
            action,
            success,
            detail,
        )
    except Exception:
        logger.exception("Failed to write audit log")


async def log_action_discord(bot, actor_id: Optional[int], action: str, detail: str = "") -> None:
    """Optional Discord mirror to STAFF_LOG_CHANNEL."""
    try:
        channel_id = bot.config.get("STAFF_LOG_CHANNEL") if bot else None
        if not channel_id:
            return
        ch = bot.get_channel(channel_id)
        if not ch:
            return
        who = f"<@{actor_id}>" if actor_id else "system"
        await ch.send(f"📋 **API Audit** · {who} · `{action}` {detail}"[:1900])
    except Exception:
        logger.debug("Could not mirror audit to Discord", exc_info=True)
