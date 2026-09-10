"""
HTTP API for the web panel — runs in the same process as the bot.

Security:
  - Header X-API-Key must match PANEL_ACCESS_KEY
  - Header X-Discord-User-Id must be a member with STAFF_API_ROLE_ID (or admin)
  - CORS restricted to PANEL / CORS_ORIGIN
  - Simple per-IP rate limit
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
    if not origins:
        origins = ["*"]
    CORS(app, origins=origins, supports_credentials=False, allow_headers=["Content-Type", "X-API-Key", "X-Discord-User-Id"])
    logger.info("API CORS origins: %s", origins)


def start_api(bot, host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    init_api(bot)
    port = int(port or os.getenv("PORT", os.getenv("API_PORT", "8080")))
    t = Thread(target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False), daemon=True)
    t.start()
    logger.info("API listening on %s:%s", host, port)


def _api_key() -> str:
    if _bot:
        return _bot.config.get("PANEL_ACCESS_KEY") or os.getenv("PANEL_ACCESS_KEY", "BOVA-CORE-2026")
    return os.getenv("PANEL_ACCESS_KEY", "BOVA-CORE-2026")


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


def _run(coro):
    """Schedule coroutine on the bot loop and wait for result."""
    if not _bot or not _bot.loop:
        raise RuntimeError("Bot not ready")
    fut = asyncio.run_coroutine_threadsafe(coro, _bot.loop)
    return fut.result(timeout=30)


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
            return jsonify({"error": "rate_limited"}), 429
        key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if key != _api_key():
            return jsonify({"error": "unauthorized", "detail": "invalid api key"}), 401
        uid_raw = request.headers.get("X-Discord-User-Id") or (request.json or {}).get("discord_user_id")
        if not uid_raw:
            return jsonify({"error": "unauthorized", "detail": "missing X-Discord-User-Id"}), 401
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "unauthorized", "detail": "bad user id"}), 401
        try:
            allowed = _run(_user_allowed(uid))
        except Exception as e:
            logger.exception("auth check failed")
            return jsonify({"error": "auth_check_failed", "detail": str(e)}), 503
        if not allowed:
            return jsonify({"error": "forbidden", "detail": "missing staff role"}), 403
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    return jsonify({
        "service": "Bova's Bot API",
        "status": "online",
        "docs": "Private API — staff role required",
    })


@app.route("/health")
def health():
    ready = bool(_bot and _bot.is_ready())
    return jsonify({
        "status": "ok" if ready else "starting",
        "bot_ready": ready,
        "uptime_seconds": int((datetime.now(timezone.utc) - _started_at).total_seconds()),
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


# Backward-compatible names used by old keep_alive imports
def keep_alive():
    """Deprecated: use start_api(bot) from bot.py."""
    port = int(os.getenv("PORT", os.getenv("API_PORT", "8080")))
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False), daemon=True)
    t.start()
