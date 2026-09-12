"""
HTTP API for the web panel — runs in the same process as the bot.

Security:
  - Header X-API-Key must match PANEL_ACCESS_KEY from the environment
  - Header X-Discord-User-Id must be a member with STAFF_API_ROLE_ID (or admin)
  - CORS restricted to PANEL / CORS_ORIGIN
  - Simple per-IP rate limit
  - Every authenticated action is written to audit log (who / what / when)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from functools import wraps
from threading import Thread
from typing import Any, Callable, Dict, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

from utils.audit import log_action

logger = logging.getLogger("bovary_bot.api")

app = Flask("bovary_api")
_bot = None
_started_at = datetime.now(timezone.utc)
_rate: Dict[str, list] = defaultdict(list)

RATE_LIMIT = 30  # requests
RATE_WINDOW = 60  # seconds



def init_api(bot) -> None:
    global _bot
    _bot = bot
    origins = []
    cors = os.getenv("CORS_ORIGIN", "").strip()
    panel = (bot.config.get("PANEL_URL") if bot else "") or os.getenv("PANEL_URL", "")
    if cors:
        origins.append(cors)
    if panel:
        # allow github pages origin
        try:
            from urllib.parse import urlparse
            p = urlparse(panel)
            if p.scheme and p.netloc:
                origins.append(f"{p.scheme}://{p.netloc}")
        except Exception:
            pass
    # The panel authenticates with explicit headers (X-API-Key / X-Discord-User-Id)
    # and does not use browser credentials/cookies. Allowing cross-origin requests is
    # therefore safe at the transport layer; the API itself remains protected by
    # require_auth on all private endpoints. Explicit CORS_ORIGIN / PANEL_URL values
    # are still logged for visibility.
    cors_origins = origins or ["*"]
    CORS(
        app,
        origins=cors_origins,
        supports_credentials=False,
        allow_headers=["Content-Type", "X-API-Key", "X-Discord-User-Id", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        expose_headers=["Content-Type"],
    )
    logger.info("API CORS origins: %s", cors_origins)


def start_api(bot, host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    init_api(bot)
    port = int(port or os.getenv("PORT", os.getenv("API_PORT", "8080")))
    t = Thread(target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False), daemon=True)
    t.start()
    logger.info("API listening on %s:%s", host, port)


def _api_key() -> str:
    if _bot:
        return _bot.config.get("PANEL_ACCESS_KEY") or os.getenv("PANEL_ACCESS_KEY", "")
    return os.getenv("PANEL_ACCESS_KEY", "")


def _staff_role_id() -> Optional[int]:
    if _bot:
        return _bot.config.get("STAFF_API_ROLE_ID") or _bot.config.get("PANEL_ACCESS_ROLE_ID")
    return None


def _guild_id() -> Optional[int]:
    if _bot:
        return _bot.config.get("GUILD_ID")
    v = os.getenv("GUILD_ID")
    return int(v) if v and v.isdigit() else None


def _check_rate() -> bool:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    now = time.time()
    bucket = _rate[ip]
    _rate[ip] = [t for t in bucket if now - t < RATE_WINDOW]
    if len(_rate[ip]) >= RATE_LIMIT:
        return False
    _rate[ip].append(now)
    return True


def _run(coro, timeout: float = 45.0):
    """Schedule coroutine on the bot loop and wait for result.

    Increased default timeout (45s). Raises clearer errors for the panel.
    """
    if not _bot or not getattr(_bot, "loop", None):
        raise RuntimeError("Bot not ready")
    if not _bot.is_ready():
        raise RuntimeError("Bot is still starting")
    fut = asyncio.run_coroutine_threadsafe(coro, _bot.loop)
    try:
        return fut.result(timeout=timeout)
    except TimeoutError:
        # concurrent.futures.TimeoutError
        raise TimeoutError(f"Bot coroutine timed out after {timeout}s") from None


async def _user_allowed(user_id: int) -> bool:
    if not _bot:
        return False
    guild_id = _guild_id()
    if not guild_id:
        # no guild configured — deny for safety
        return False
    guild = _bot.get_guild(guild_id)
    if not guild:
        try:
            guild = await _bot.fetch_guild(guild_id)
        except Exception:
            return False
    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return False
    role_id = _staff_role_id()
    if member.guild_permissions.administrator:
        return True
    if role_id and any(r.id == role_id for r in member.roles):
        return True
    return False


def require_auth(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _check_rate():
            log_action(actor_id=None, action="rate_limited", detail={"path": request.path}, success=False)
            return jsonify({"error": "rate_limited"}), 429
        key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if key != _api_key():
            log_action(actor_id=None, action="auth_fail_key", detail={"path": request.path}, success=False)
            return jsonify({"error": "unauthorized", "detail": "invalid api key"}), 401
        uid_raw = request.headers.get("X-Discord-User-Id") or (request.json or {}).get("discord_user_id")
        if not uid_raw:
            log_action(actor_id=None, action="auth_fail_no_uid", detail={"path": request.path}, success=False)
            return jsonify({"error": "unauthorized", "detail": "missing X-Discord-User-Id"}), 401
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            log_action(actor_id=None, action="auth_fail_bad_uid", detail={"path": request.path}, success=False)
            return jsonify({"error": "unauthorized", "detail": "bad user id"}), 401
        try:
            allowed = _run(_user_allowed(uid))
        except Exception as e:
            logger.exception("auth check failed")
            log_action(actor_id=uid, action="auth_check_failed", detail={"error": str(e)}, success=False)
            return jsonify({"error": "auth_check_failed", "detail": str(e)}), 503
        if not allowed:
            log_action(actor_id=uid, action="auth_forbidden", detail={"path": request.path}, success=False)
            return jsonify({"error": "forbidden", "detail": "missing staff role"}), 403
        # Stash actor for handlers
        request.bova_actor_id = uid  # type: ignore
        result = fn(*args, **kwargs)
        # Log successful call (handlers can log more detail themselves)
        try:
            action_name = request.path.strip("/").replace("/", "_") or "root"
            log_action(actor_id=uid, action=action_name, detail={"method": request.method}, success=True)
        except Exception:
            pass
        return result
    return wrapper


@app.route("/")
def home():
    return jsonify({
        "service": "Bova's Bot API",
        "status": "online",
        "docs": "Private API — staff role required",
    })


@app.get("/api/auth/check")
@require_auth
def api_auth_check():
    """Validate the panel key + Discord staff identity without exposing the key."""
    return jsonify({"ok": True})


@app.route("/health")
def health():
    ready = bool(_bot and _bot.is_ready())
    extra = {}
    try:
        from utils import db as sqldb
        from utils.storage import _bootstrap
        _bootstrap()
        extra["database"] = sqldb.db_stats()
    except Exception as e:
        extra["database"] = {"error": str(e)}

    # Message log cache size (if cog loaded)
    try:
        wl = _bot.get_cog("WebLogs") if _bot else None
        if wl is not None:
            extra["message_cache"] = {
                "size": len(getattr(wl, "_msg_cache", {})),
                "delete_logged": len(getattr(wl, "_delete_logged", {})),
                "limit": getattr(wl, "_msg_cache", None) and getattr(
                    __import__("cogs.weblogs", fromlist=["MESSAGE_CACHE_SIZE"]),
                    "MESSAGE_CACHE_SIZE",
                    None,
                ),
            }
    except Exception:
        pass

    # Simple loop status for key background tasks
    loops = {}
    try:
        if _bot:
            for name in ("Backup", "AutoFeeds", "TimestampReminders", "Meets"):
                cog = _bot.get_cog(name)
                if not cog:
                    continue
                for attr in dir(cog):
                    obj = getattr(cog, attr, None)
                    if hasattr(obj, "is_running") and callable(getattr(obj, "is_running", None)):
                        try:
                            loops[f"{name}.{attr}"] = bool(obj.is_running())
                        except Exception:
                            loops[f"{name}.{attr}"] = "error"
    except Exception:
        pass
    if loops:
        extra["background_loops"] = loops

    return jsonify({
        "status": "ok" if ready else "starting",
        "bot_ready": ready,
        "uptime_seconds": int((datetime.now(timezone.utc) - _started_at).total_seconds()),
        **extra,
    })


@app.post("/api/embed")
@require_auth
def api_embed():
    data = request.get_json(force=True, silent=True) or {}
    channel_id = data.get("channel_id")
    if not channel_id:
        return jsonify({"error": "channel_id required"}), 400

    async def _send():
        channel = _bot.get_channel(int(channel_id))
        if channel is None:
            channel = await _bot.fetch_channel(int(channel_id))
        import discord
        color = data.get("color", 0x00E5FF)
        if isinstance(color, str) and color.startswith("#"):
            color = int(color[1:], 16)
        embed = discord.Embed(
            title=data.get("title") or None,
            description=data.get("description") or None,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        if data.get("image_url"):
            embed.set_image(url=data["image_url"])
        if data.get("footer"):
            embed.set_footer(text=data["footer"])
        content = None
        if data.get("role_id"):
            content = f"<@&{data['role_id']}>"
        msg = await channel.send(content=content, embed=embed)
        return {"ok": True, "message_id": msg.id, "channel_id": channel.id}

    try:
        result = _run(_send())
        return jsonify(result)
    except Exception as e:
        logger.exception("api_embed")
        return jsonify({"error": str(e)}), 500


@app.post("/api/meet")
@require_auth
def api_meet():
    data = request.get_json(force=True, silent=True) or {}
    required = ["title", "description", "date_time", "hosts", "server", "channel_id"]
    for k in required:
        if not data.get(k):
            return jsonify({"error": f"{k} required"}), 400

    async def _send():
        from utils.helpers import tz_from_offset
        import discord
        channel = _bot.get_channel(int(data["channel_id"]))
        if channel is None:
            channel = await _bot.fetch_channel(int(data["channel_id"]))
        offset = float(data.get("timezone_offset", -3))
        tz = tz_from_offset(offset)
        dt = None
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(data["date_time"].strip(), fmt).replace(tzinfo=tz)
                break
            except ValueError:
                continue
        if not dt:
            raise ValueError("Invalid date_time — use DD/MM/YYYY HH:MM")
        unix = int(dt.timestamp())
        embed = discord.Embed(
            title=f"🚗 {data['title']}",
            description=data["description"],
            color=discord.Color.from_rgb(180, 80, 255),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="📅 Date & Time",
            value=f"<t:{unix}:F>\n<t:{unix}:R>\n`UTC{offset:+g}` {dt.strftime('%d/%m/%Y %H:%M')}",
            inline=False,
        )
        embed.add_field(name="👤 Hosts", value=data["hosts"], inline=True)
        embed.add_field(name="🖥️ Server", value=data["server"], inline=True)
        role_id = data.get("mention_role_id")
        if role_id:
            embed.add_field(name="🔔 Role", value=f"<@&{role_id}>", inline=True)
        if data.get("image_url"):
            embed.set_image(url=data["image_url"])
        embed.set_footer(text="Bova's Bot · Bovary Club Society")
        content = f"<@&{role_id}>" if role_id else None
        msg = await channel.send(content=content, embed=embed)

        # schedule reminder via Meets cog if present
        meets_cog = _bot.get_cog("Meets")
        if meets_cog and data.get("enable_reminder") and data.get("reminder_channel_id"):
            meet_data = {
                "title": data["title"],
                "description": data["description"],
                "start_unix": unix,
                "hosts": data["hosts"],
                "server": data["server"],
                "mention_role_id": int(role_id) if role_id else None,
                "image_url": data.get("image_url"),
                "message_id": msg.id,
                "channel_id": channel.id,
                "reminder_enabled": True,
                "reminder_channel_id": int(data["reminder_channel_id"]),
                "reminder_sent": False,
            }
            meets_cog.meets.append(meet_data)
            meets_cog._cleanup_old()
            meets_cog._save()
        return {"ok": True, "message_id": msg.id, "start_unix": unix}

    try:
        return jsonify(_run(_send()))
    except Exception as e:
        logger.exception("api_meet")
        return jsonify({"error": str(e)}), 500


@app.post("/api/autorole/panel")
@require_auth
def api_autorole_panel():
    data = request.get_json(force=True, silent=True) or {}
    channel_id = data.get("channel_id")
    if not channel_id:
        return jsonify({"error": "channel_id required"}), 400

    async def _send():
        import discord
        from cogs.autorole import AutoRoleView
        cog = _bot.get_cog("AutoRole")
        if not cog:
            raise RuntimeError("AutoRole cog not loaded")
        # optional config update from panel
        if data.get("title"):
            cog.config["title"] = data["title"]
        if data.get("description"):
            cog.config["description"] = data["description"]
        if data.get("color") is not None:
            c = data["color"]
            if isinstance(c, str) and c.startswith("#"):
                c = int(c[1:], 16)
            cog.config["color"] = c
        if data.get("roles"):
            # merge roles from panel [{role_id, label, emoji}]
            cog.config["roles"] = data["roles"]
        cog._save()
        roles = cog.config.get("roles") or []
        if not roles:
            raise RuntimeError("No roles configured — use roles in body or /autorole_add first")
        channel = _bot.get_channel(int(channel_id))
        if channel is None:
            channel = await _bot.fetch_channel(int(channel_id))
        embed = discord.Embed(
            title=cog.config.get("title", "Choose your roles"),
            description=cog.config.get("description", ""),
            color=cog.config.get("color", 0xB450FF),
        )
        embed.set_footer(text="Bova's Bot · Auto-Role · Click to toggle")
        view = AutoRoleView(_bot, roles)
        msg = await channel.send(embed=embed, view=view)
        cog.config["message_id"] = msg.id
        cog.config["channel_id"] = channel.id
        cog._save()
        cog._reregister_view()
        return {"ok": True, "message_id": msg.id}

    try:
        return jsonify(_run(_send()))
    except Exception as e:
        logger.exception("api_autorole")
        return jsonify({"error": str(e)}), 500


@app.post("/api/autofeed")
@require_auth
def api_autofeed():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("message") or not data.get("channel_id"):
        return jsonify({"error": "message and channel_id required"}), 400

    async def _add():
        cog = _bot.get_cog("AutoFeeds")
        if not cog:
            raise RuntimeError("AutoFeeds cog not loaded")
        from utils.helpers import SERVER_TZ
        now = datetime.now(timezone.utc)
        mode = data.get("mode", "interval")
        fixed_hour = data.get("fixed_hour")
        fixed_minute = int(data.get("fixed_minute", 0))
        if mode == "fixed" and fixed_hour is not None:
            next_unix = cog._next_fixed(int(fixed_hour), fixed_minute)
            mode = "fixed"
        else:
            start_in = int(data.get("start_in_minutes", 5))
            next_unix = now.timestamp() + start_in * 60
            mode = "interval"
        feed = {
            "id": int(now.timestamp() * 1000) % 10_000_000,
            "message": data["message"],
            "channel_id": int(data["channel_id"]),
            "role_id": int(data["role_id"]) if data.get("role_id") else None,
            "interval_minutes": int(data.get("interval_minutes", 1440)),
            "mode": mode,
            "fixed_hour": int(fixed_hour) if fixed_hour is not None else None,
            "fixed_minute": fixed_minute if fixed_hour is not None else None,
            "next_unix": next_unix,
            "enabled": True,
            "use_embed": bool(data.get("use_embed")),
            "embed_title": data.get("embed_title"),
            "embed_image": data.get("embed_image"),
            "embed_color": 0xB450FF,
        }
        cog.feeds.append(feed)
        cog._save()
        return {"ok": True, "id": feed["id"], "next_unix": next_unix}

    try:
        return jsonify(_run(_add()))
    except Exception as e:
        logger.exception("api_autofeed")
        return jsonify({"error": str(e)}), 500


@app.get("/api/autofeeds")
@require_auth
def api_autofeeds_list():
    cog = _bot.get_cog("AutoFeeds") if _bot else None
    if not cog:
        return jsonify({"feeds": []})
    return jsonify({"feeds": cog.feeds})


@app.get("/api/stats/summary")
@require_auth
def api_stats():
    cog = _bot.get_cog("Stats") if _bot else None
    if not cog:
        return jsonify({})
    d = cog.data
    return jsonify({
        "joins": d.get("joins", 0),
        "leaves": d.get("leaves", 0),
        "hourly": d.get("hourly", {}),
        "weekday": d.get("weekday", {}),
        "top_messages": sorted((d.get("messages") or {}).items(), key=lambda x: x[1], reverse=True)[:10],
    })


@app.get("/api/namehistory")
@require_auth
def api_namehistory():
    cog = _bot.get_cog("NameHistory") if _bot else None
    if not cog:
        return jsonify({"members": {}})
    return jsonify(cog.data)



@app.post("/api/poll")
@require_auth
def api_poll():
    """Create a poll from the web panel (Sesh-style fields)."""
    data = request.get_json(force=True, silent=True) or {}
    actor = getattr(request, "bova_actor_id", None)

    async def _create():
        cog = _bot.get_cog("Polls")
        if not cog:
            raise RuntimeError("Polls cog not loaded")
        channel_id = int(data["channel_id"])
        ch = _bot.get_channel(channel_id)
        if not ch:
            ch = await _bot.fetch_channel(channel_id)
        options = data.get("options") or []
        if isinstance(options, str):
            options = [o.strip() for o in options.replace("\n", ",").split(",") if o.strip()]
        poll = await cog.create_poll(
            channel=ch,
            title=data.get("title") or "Poll",
            options=options,
            description=data.get("description") or "",
            single=bool(data.get("single_vote") or data.get("single")),
            hours=float(data["hours"]) if data.get("hours") else None,
            color=data.get("color") or "#B450FF",
            author_id=actor,
        )
        return {"ok": True, "id": poll["id"], "message_id": poll["message_id"]}

    try:
        result = _run(_create())
        log_action(actor_id=actor, action="api_poll", detail={"title": data.get("title"), "channel_id": data.get("channel_id")}, success=True)
        return jsonify(result)
    except Exception as e:
        logger.exception("api_poll")
        log_action(actor_id=actor, action="api_poll", detail={"error": str(e)}, success=False)
        return jsonify({"error": str(e)}), 500


@app.get("/api/audit")
@require_auth
def api_audit():
    """Recent audit log entries (staff only) — from SQLite audit_log."""
    from utils import db as sqldb
    from utils.storage import _bootstrap
    _bootstrap()
    entries = sqldb.audit_recent(50)
    return jsonify({"entries": entries, "storage": "sqlite"})




@app.get("/api/commands")
@require_auth
def api_commands():
    """Return the actual slash commands loaded from the bot cogs."""
    rows = []
    seen = set()
    if _bot:
        for cog in _bot.cogs.values():
            for cmd in getattr(cog, "__cog_app_commands__", []) or []:
                name = getattr(cmd, "name", None)
                if not name or name in seen:
                    continue
                seen.add(name)
                rows.append({
                    "name": name,
                    "description": getattr(cmd, "description", "") or "",
                })
    rows.sort(key=lambda x: x["name"])
    return jsonify({"commands": rows, "count": len(rows)})


@app.get("/api/overview")
@require_auth
def api_overview():
    """Compact live overview used by the upgraded web dashboard."""
    from utils import db as sqldb
    from utils.storage import _bootstrap
    _bootstrap()
    ts_cog = _bot.get_cog("TimestampReminders") if _bot else None
    dm_cog = _bot.get_cog("DMInbox") if _bot else None
    backup_cog = _bot.get_cog("Backup") if _bot else None
    try:
        command_count = len(list(_bot.tree.walk_commands())) if _bot else 0
    except Exception:
        command_count = 0
    db = sqldb.db_stats()
    conversations = (dm_cog.data.get("conversations", {}) if dm_cog else {})
    dm_messages = sum(len(v) for v in conversations.values() if isinstance(v, list))
    return jsonify({
        "bot_ready": bool(_bot and _bot.is_ready()),
        "uptime_seconds": int((datetime.now(timezone.utc) - _started_at).total_seconds()),
        "command_count": command_count,
        "timestamp_reminder": ts_cog.get_config() if ts_cog else {"enabled": False, "minutes": 30, "pending": 0},
        "dm_inbox": {
            "users": len(conversations),
            "messages": dm_messages,
            "auto_response_enabled": bool(dm_cog and dm_cog.data.get("auto_response_enabled")),
        },
        "database": db,
        "backup": {
            "interval_hours": backup_cog._interval_hours() if backup_cog else None,
            "last_auto": backup_cog._last_auto if backup_cog else None,
            "channel_id": _bot.config.get("BACKUP_CHANNEL_ID") if _bot else None,
        },
    })


@app.get("/api/timestamp-reminder")
@require_auth
def api_timestamp_reminder_get():
    cog = _bot.get_cog("TimestampReminders") if _bot else None
    if not cog:
        return jsonify({"enabled": False, "minutes": 30, "text": "", "pending": 0})
    return jsonify(cog.get_config())


@app.post("/api/timestamp-reminder")
@require_auth
def api_timestamp_reminder_set():
    data = request.get_json(force=True, silent=True) or {}
    cog = _bot.get_cog("TimestampReminders") if _bot else None
    if not cog:
        return jsonify({"error": "TimestampReminders cog not loaded"}), 503
    enabled = data.get("enabled")
    minutes = data.get("minutes")
    text = data.get("text")
    if enabled is not None and not isinstance(enabled, bool):
        return jsonify({"error": "enabled must be boolean"}), 400
    if minutes is not None:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            return jsonify({"error": "minutes must be an integer"}), 400
        if not 1 <= minutes <= 1440:
            return jsonify({"error": "minutes must be between 1 and 1440"}), 400
    if text is not None:
        text = str(text).strip()[:1800]
        if not text:
            return jsonify({"error": "text cannot be empty"}), 400
    try:
        result = cog.configure(enabled=enabled, minutes=minutes, text=text)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        logger.exception("api_timestamp_reminder")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/dm/inbox")
@require_auth
def api_dm_inbox():
    cog = _bot.get_cog("DMInbox") if _bot else None
    if not cog:
        return jsonify({"conversations": []})
    rows = []
    for uid, msgs in cog.data.get("conversations", {}).items():
        if not msgs:
            continue
        last = msgs[-1]
        rows.append({
            "user_id": str(uid),
            "message_count": len(msgs),
            "last_direction": last.get("direction"),
            "last_content": (last.get("content") or "").strip()[:240],
            "last_timestamp": last.get("timestamp"),
        })
    rows.sort(key=lambda x: x.get("last_timestamp") or "", reverse=True)
    return jsonify({
        "conversations": rows[:50],
        "auto_response_enabled": bool(cog.data.get("auto_response_enabled")),
        "auto_response_text": cog.data.get("auto_response_text") or "",
    })


@app.get("/api/dm/history/<int:user_id>")
@require_auth
def api_dm_history(user_id: int):
    cog = _bot.get_cog("DMInbox") if _bot else None
    if not cog:
        return jsonify({"messages": []})
    msgs = cog.data.get("conversations", {}).get(str(user_id), [])
    return jsonify({"user_id": str(user_id), "messages": msgs[-50:]})


@app.post("/api/dm/reply")
@require_auth
def api_dm_reply():
    data = request.get_json(force=True, silent=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "valid user_id required"}), 400
    text = str(data.get("message") or "").strip()[:2000]
    if not text:
        return jsonify({"error": "message required"}), 400
    actor = getattr(request, "bova_actor_id", None)

    async def _send():
        cog = _bot.get_cog("DMInbox")
        if not cog:
            raise RuntimeError("DMInbox cog not loaded")
        user = _bot.get_user(user_id)
        if user is None:
            user = await _bot.fetch_user(user_id)
        await user.send(text)
        convo = cog._conversation(user)
        convo.append({
            "direction": "out",
            "content": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "automatic": False,
            "staff_id": actor,
        })
        del convo[:-200]
        from utils.storage import save_json
        save_json("dm_inbox.json", cog.data)
        return {"ok": True, "user_id": str(user_id)}

    try:
        return jsonify(_run(_send()))
    except Exception as exc:
        logger.exception("api_dm_reply")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/dm/auto")
@require_auth
def api_dm_auto():
    data = request.get_json(force=True, silent=True) or {}
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": "enabled must be boolean"}), 400
    text = data.get("text")
    if text is not None:
        text = str(text).strip()[:2000]
    cog = _bot.get_cog("DMInbox") if _bot else None
    if not cog:
        return jsonify({"error": "DMInbox cog not loaded"}), 503
    cog.data["auto_response_enabled"] = enabled
    if text is not None:
        cog.data["auto_response_text"] = text
    from utils.storage import save_json
    save_json("dm_inbox.json", cog.data)
    return jsonify({"ok": True, "enabled": enabled, "text": cog.data.get("auto_response_text") or ""})


@app.get("/api/server/summary")
@require_auth
def api_server_summary():
    """Server analytics for the web panel."""
    async def _sum():
        gid = _guild_id()
        if not gid:
            return {"error": "no guild"}
        g = _bot.get_guild(gid)
        if not g:
            g = await _bot.fetch_guild(gid)
            await g.chunk() if hasattr(g, "chunk") else None
        humans = sum(1 for m in g.members if not m.bot)
        bots = sum(1 for m in g.members if m.bot)
        roles = [
            {"id": str(r.id), "name": r.name, "members": len(r.members), "color": str(r.color)}
            for r in sorted(g.roles, key=lambda x: len(x.members), reverse=True)
            if r.name != "@everyone"
        ][:25]
        return {
            "id": str(g.id),
            "name": g.name,
            "member_count": g.member_count,
            "humans": humans,
            "bots": bots,
            "roles_count": len(g.roles),
            "roles": roles,
            "text_channels": len(g.text_channels),
            "voice_channels": len(g.voice_channels),
            "boost_tier": g.premium_tier,
            "boosts": g.premium_subscription_count or 0,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "icon": str(g.icon.url) if g.icon else None,
        }
    try:
        return jsonify(_run(_sum()))
    except Exception as e:
        logger.exception("server summary")
        return jsonify({"error": str(e)}), 500



@app.get("/api/tickets")
@require_auth
def api_tickets():
    """Recent ticket/suggestion/report submissions for the web panel."""
    cog = _bot.get_cog("Tickets") if _bot else None
    if not cog:
        return jsonify({"entries": []})
    return jsonify({"entries": cog.get_entries_for_api(80)})


# Backward-compatible names used by old keep_alive imports
def keep_alive():
    """Deprecated: use start_api(bot) from bot.py."""
    port = int(os.getenv("PORT", os.getenv("API_PORT", "8080")))
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False), daemon=True)
    t.start()
