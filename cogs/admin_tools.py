"""Advanced staff audit, activity and engagement tools.

All slash commands in this cog are protected by the bot's global staff-role
policy. The listeners intentionally remain active independently of slash-command
permissions so normal member panels (invites, tickets, minigames, etc.) keep
working for everyone.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from utils.db import kv_get, kv_set
from utils.helpers import SERVER_TZ, is_media_in_message, make_embed, safe_get_channel

logger = logging.getLogger("bovary_bot.admin_tools")

TARGET_AUTOMOD_CHANNEL = 1548153354675556412
INVITE_LOG_CHANNEL = 1424436722984423529
MASS_ACTION_LOG_CHANNEL = 1424436722984423529
RANKING_CHANNELS = {1553823431349371042, 1531417799300350073}
MEDIA_CATEGORY_ID = 1384173136853078036
MAX_ACTIVITY_PER_USER = 80
MAX_AUTOMOD_EVENTS = 250
MAX_DELETED_PER_USER = 50


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def user_name(member: Optional[discord.abc.User]) -> str:
    if member is None:
        return "Unknown"
    return getattr(member, "display_name", None) or getattr(member, "name", None) or str(member)


def clip(value: Any, length: int = 180) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= length else text[: length - 1] + "…"


def _member_has_role(member: discord.Member, role_id: int) -> bool:
    return any(r.id == role_id for r in getattr(member, "roles", []))


class AdminTools(commands.Cog):
    """Persistent activity collection + advanced staff slash commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._activity: Dict[str, List[Dict[str, Any]]] = kv_get("member_activity", {}) or {}
        self._media_counts: Dict[str, int] = kv_get("media_upload_counts", {}) or {}
        self._chat_counts: Dict[str, int] = kv_get("ranking_chat_counts", {}) or {}
        self._automod_events: List[Dict[str, Any]] = kv_get("automod_events", []) or []
        self._deleted: Dict[str, List[Dict[str, Any]]] = kv_get("deleted_messages", {}) or {}
        self._role_changes: Dict[str, List[Dict[str, Any]]] = kv_get("role_changes", {}) or {}
        self._engagement: Dict[str, Dict[str, List[int]]] = kv_get("engagement_users", {}) or {}
        self._invite_cache: Dict[str, Dict[str, Any]] = {}
        self._invite_history: List[Dict[str, Any]] = kv_get("invite_history", []) or []
        self._msg_stats: Dict[str, Dict[str, Any]] = kv_get("member_message_stats", {}) or {}
        self._mass_actions: Dict[int, List[Tuple[float, str]]] = defaultdict(list)
        self._mass_alerts: List[Dict[str, Any]] = kv_get("mass_action_alerts", []) or []
        self._save_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        # Give the bot a short interval to finish startup before background
        # snapshots begin; no slash command depends on this task.
        self._save_task = asyncio.create_task(self._periodic_save())

    def cog_unload(self):
        if self._save_task:
            self._save_task.cancel()
        self._save_all()

    async def _periodic_save(self):
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(300)
            self._save_all()

    def _save_all(self):
        try:
            kv_set("member_activity", self._activity)
            kv_set("media_upload_counts", self._media_counts)
            kv_set("ranking_chat_counts", self._chat_counts)
            kv_set("automod_events", self._automod_events[-MAX_AUTOMOD_EVENTS:])
            kv_set("deleted_messages", self._deleted)
            kv_set("role_changes", self._role_changes)
            kv_set("engagement_users", self._engagement)
            kv_set("invite_history", self._invite_history[-2000:])
            kv_set("member_message_stats", self._msg_stats)
            kv_set("mass_action_alerts", self._mass_alerts[-100:])
        except Exception:
            logger.exception("Failed to persist admin tool data")

    def _add_activity(self, user_id: int, kind: str, detail: str, *, channel_id: Optional[int] = None):
        key = str(user_id)
        bucket = self._activity.setdefault(key, [])
        bucket.append({
            "at": now_iso(),
            "kind": kind,
            "detail": clip(detail, 300),
            "channel_id": channel_id,
        })
        del bucket[:-MAX_ACTIVITY_PER_USER]

    def _track_engagement(self, user_id: int, when: Optional[datetime] = None):
        when = when or datetime.now(SERVER_TZ)
        date_key = when.strftime("%Y-%m-%d")
        hour_key = str(when.hour)
        day = self._engagement.setdefault(date_key, {})
        users = day.setdefault(hour_key, [])
        sid = int(user_id)
        if sid not in users:
            users.append(sid)
            if len(users) > 2000:
                del users[:-2000]
        # Retain approximately 35 days of hourly user sets.
        cutoff = (datetime.now(SERVER_TZ).date() - timedelta(days=35)).isoformat()
        for old in list(self._engagement):
            if old < cutoff:
                self._engagement.pop(old, None)

    def _channel(self, channel_id: int):
        return safe_get_channel(self.bot, channel_id)

    async def _send_staff_log(self, title: str, description: str, *, channel_id: int = MASS_ACTION_LOG_CHANNEL, color=discord.Color.orange()):
        channel = self._channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        try:
            await channel.send(embed=make_embed(title=title, description=description, color=color))
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not send staff log to %s", channel_id)

    async def _refresh_invite_cache(self, guild: discord.Guild, *, joining_member: Optional[discord.Member] = None):
        try:
            invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return
        current = {i.code: {"uses": int(getattr(i, "uses", 0) or 0), "inviter_id": getattr(getattr(i, "inviter", None), "id", None), "channel_id": getattr(getattr(i, "channel", None), "id", None)} for i in invites}
        if joining_member:
            for code, row in current.items():
                old = self._invite_cache.get(code, {})
                if int(row.get("uses", 0)) > int(old.get("uses", 0)) and row.get("inviter_id"):
                    await self._send_staff_log(
                        "🎟️ Server invite used",
                        f"**Inviter:** <@{row['inviter_id']}> (`{row['inviter_id']}`)\n"
                        f"**Recipient:** {joining_member.mention} (`{joining_member.id}`)\n"
                        f"**Invite:** `{code}` · **Channel:** <#{row.get('channel_id') or 0}>",
                        channel_id=INVITE_LOG_CHANNEL,
                        color=discord.Color.green(),
                    )
                    self._add_activity(row["inviter_id"], "invite_used", f"Invite {code} was used by {joining_member}", channel_id=row.get("channel_id"))
                    self._add_activity(joining_member.id, "invite_join", f"Joined using invite {code} created by {row['inviter_id']}")
        self._invite_cache = current

    @commands.Cog.listener()
    async def on_ready(self):
        guild_id = self.bot.config.get("GUILD_ID")
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if guild:
            await self._refresh_invite_cache(guild)

    # ── Event collection ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.author or message.author.bot:
            return
        uid = message.author.id
        self._add_activity(uid, "message", f"Message in #{getattr(message.channel, 'name', message.channel.id)}: {clip(message.content, 140)}", channel_id=message.channel.id)
        self._track_engagement(uid)
        stat = self._msg_stats.setdefault(str(uid), {
            "messages": 0, "characters": 0, "media": 0,
            "channels": {}, "hours": {}, "weekdays": {},
        })
        stat["messages"] = int(stat.get("messages", 0)) + 1
        stat["characters"] = int(stat.get("characters", 0)) + len(message.content or "")
        sid = str(message.channel.id)
        stat.setdefault("channels", {})[sid] = int(stat.setdefault("channels", {}).get(sid, 0)) + 1
        local_now = datetime.now(SERVER_TZ)
        stat.setdefault("hours", {})[str(local_now.hour)] = int(stat.setdefault("hours", {}).get(str(local_now.hour), 0)) + 1
        stat.setdefault("weekdays", {})[str(local_now.weekday())] = int(stat.setdefault("weekdays", {}).get(str(local_now.weekday()), 0)) + 1
        if is_media_in_message(message):
            stat["media"] = int(stat.get("media", 0)) + 1

        if message.channel.id in RANKING_CHANNELS:
            key = str(uid)
            self._chat_counts[key] = int(self._chat_counts.get(key, 0)) + 1

        if is_media_in_message(message):
            category_id = getattr(message.channel, "category_id", None)
            if category_id == MEDIA_CATEGORY_ID:
                key = str(uid)
                self._media_counts[key] = int(self._media_counts.get(key, 0)) + 1

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or not payload.user_id:
            return
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        self._track_engagement(payload.user_id)
        self._add_activity(payload.user_id, "reaction", f"Added {payload.emoji} reaction", channel_id=getattr(payload, "channel_id", None))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self._add_activity(member.id, "join", "Joined the server")
        await self._refresh_invite_cache(member.guild, joining_member=member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}
        if before_ids == after_ids:
            return
        added = sorted(after_ids - before_ids)
        removed = sorted(before_ids - after_ids)
        actor_id = None
        actor_name = "Unknown"
        try:
            async for entry in after.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_role_update):
                target = getattr(entry, "target", None)
                if getattr(target, "id", None) == after.id:
                    actor_id = getattr(entry.user, "id", None)
                    actor_name = str(entry.user) if entry.user else "Unknown"
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass
        detail = f"Roles added: {added or 'none'}; removed: {removed or 'none'}; changed by: {actor_name}"
        self._add_activity(after.id, "role_change", detail)
        bucket = self._role_changes.setdefault(str(after.id), [])
        bucket.append({
            "at": now_iso(), "added": added, "removed": removed,
            "actor_id": actor_id, "actor_name": actor_name,
        })
        del bucket[:-50]

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        inviter = getattr(invite, "inviter", None)
        if inviter and getattr(inviter, "id", None):
            self._add_activity(inviter.id, "invite_create", f"Created invite {invite.code} (uses={getattr(invite, 'uses', 0)})", channel_id=getattr(getattr(invite, 'channel', None), 'id', None))
        self._invite_history.append({
            "at": now_iso(),
            "guild_id": getattr(getattr(invite, "guild", None), "id", None),
            "inviter_id": getattr(inviter, "id", None),
            "code": invite.code,
            "channel_id": getattr(getattr(invite, "channel", None), "id", None),
            "max_uses": getattr(invite, "max_uses", 0),
            "max_age": getattr(invite, "max_age", 0),
            "temporary": getattr(invite, "temporary", False),
        })
        del self._invite_history[:-2000]
        details = (
            f"**Inviter:** {inviter.mention if inviter else 'Unknown'} (`{getattr(inviter, 'id', 'unknown')}`)\n"
            f"**Code:** `{invite.code}`\n"
            f"**Channel:** <#{getattr(getattr(invite, 'channel', None), 'id', 0)}>\n"
            f"**Max uses:** `{getattr(invite, 'max_uses', 0)}` · **Max age:** `{getattr(invite, 'max_age', 0)}s`\n"
            f"**Temporary:** `{getattr(invite, 'temporary', False)}`\n"
            f"**Recipient:** Discord does not expose the recipient when an invite is created."
        )
        await self._send_staff_log("📨 Server invite created", details, channel_id=INVITE_LOG_CHANNEL, color=discord.Color.blue())

    @commands.Cog.listener()
    async def on_automod_action(self, action):
        guild = getattr(action, "guild", None)
        if guild is None:
            return
        channel_id = getattr(action, "channel_id", None)
        if channel_id != TARGET_AUTOMOD_CHANNEL:
            return
        user_id = getattr(action, "user_id", None)
        event = {
            "at": now_iso(),
            "guild_id": guild.id,
            "channel_id": channel_id,
            "user_id": user_id,
            "rule_id": getattr(action, "rule_id", None),
            "action": str(getattr(action, "action", "blocked")),
            "content": clip(getattr(action, "content", ""), 300),
            "matched_keyword": clip(getattr(action, "matched_keyword", ""), 120),
            "matched_content": clip(getattr(action, "matched_content", ""), 120),
            "message_id": getattr(action, "message_id", None),
        }
        self._automod_events.append(event)
        del self._automod_events[:-MAX_AUTOMOD_EVENTS]
        if user_id:
            self._add_activity(user_id, "automod", f"AutoMod action in <#{channel_id}>: {event['action']}", channel_id=channel_id)
        member = guild.get_member(user_id) if user_id else None
        mention = member.mention if member else f"`{user_id}`"
        description = (
            f"**Member:** {mention}\n"
            f"**Action:** `{event['action']}`\n"
            f"**Rule:** `{event['rule_id']}`\n"
            f"**Content:** `{clip(event['content'], 500) or '[not supplied by Discord]'}`"
        )
        await self._send_staff_log("🛡️ Discord AutoMod action", description, channel_id=TARGET_AUTOMOD_CHANNEL, color=discord.Color.red())

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or not message.author or message.author.bot:
            return
        snap = {
            "at": now_iso(),
            "message_id": message.id,
            "channel_id": message.channel.id,
            "content": clip(message.content, 1000),
            "author_id": message.author.id,
            "jump_url": message.jump_url,
        }
        bucket = self._deleted.setdefault(str(message.author.id), [])
        bucket.append(snap)
        del bucket[:-MAX_DELETED_PER_USER]
        self._add_activity(message.author.id, "message_delete", f"A message was deleted in #{getattr(message.channel, 'name', message.channel.id)}", channel_id=message.channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        target = after.channel.name if after.channel else "left voice"
        self._add_activity(member.id, "voice", f"Voice state changed: {target}", channel_id=getattr(after.channel, "id", None))

    # ── Helpers for commands ────────────────────────────────────────────────

    async def _resolve_member(self, interaction: discord.Interaction, member: discord.Member) -> discord.Member:
        if member.guild.id != interaction.guild_id:
            raise ValueError("Member must belong to this server.")
        return member

    @staticmethod
    def _role_mentions(member: discord.Member) -> str:
        roles = [r for r in member.roles if r.name != "@everyone"]
        if not roles:
            return "_No roles_"
        return ", ".join(r.mention for r in roles[:30])

    def _recent_deleted(self, user_id: int) -> List[Dict[str, Any]]:
        return list(self._deleted.get(str(user_id), []))[-8:][::-1]

    # ── 1. Member activity ──────────────────────────────────────────────────

    @app_commands.command(name="member_activity", description="Show recent activity recorded for a selected member")
    async def member_activity(self, interaction: discord.Interaction, member: discord.Member):
        rows = list(self._activity.get(str(member.id), []))[-12:][::-1]
        if not rows:
            await interaction.response.send_message(f"No recent tracked activity for **{member.display_name}**.", ephemeral=True)
            return
        lines = []
        for row in rows:
            ts = row.get("at", "")
            try:
                unix = int(datetime.fromisoformat(ts).timestamp())
                when = f"<t:{unix}:R>"
            except Exception:
                when = ts
            channel = f" · <#{row['channel_id']}>" if row.get("channel_id") else ""
            lines.append(f"• **{row.get('kind', 'activity')}**{channel} — {clip(row.get('detail', ''), 180)} · {when}")
        embed = make_embed(title=f"📋 Activity — {member.display_name}", description="\n".join(lines), color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 2. Member invites ───────────────────────────────────────────────────

    @app_commands.command(name="member_invites", description="List invites created by a selected member")
    async def member_invites(self, interaction: discord.Interaction, member: discord.Member):
        try:
            active = await interaction.guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            active = []
        active_codes = {i.code for i in active if getattr(getattr(i, "inviter", None), "id", None) == member.id}
        history = [x for x in self._invite_history if x.get("inviter_id") == member.id]
        seen = set()
        lines = []
        for row in reversed(history):
            code = row.get("code")
            if not code or code in seen:
                continue
            seen.add(code)
            channel = f"<#{row['channel_id']}>" if row.get("channel_id") else "unknown channel"
            current = next((i for i in active if i.code == code), None)
            uses = getattr(current, "uses", 0) if current else "historical"
            lines.append(f"`{code}` · {channel} · uses **{uses}**")
            if len(lines) >= 20:
                break
        if not lines and active_codes:
            lines = [f"`{code}` · active invite" for code in sorted(active_codes)]
        if not lines:
            await interaction.response.send_message(f"No invite history is recorded for **{member.display_name}**.", ephemeral=True)
            return
        embed = make_embed(
            title=f"📨 Invites — {member.display_name}",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Recipient identity is not exposed when an invite is created; this list records the inviter/code/channel.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 3.1 AutoMod activity ────────────────────────────────────────────────

    @app_commands.command(name="automod_activity", description="List recent Discord AutoMod actions for this channel")
    async def automod_activity(self, interaction: discord.Interaction):
        rows = [x for x in self._automod_events if x.get("channel_id") == interaction.channel_id][-15:][::-1]
        if not rows:
            await interaction.response.send_message("No AutoMod actions recorded for this channel yet.", ephemeral=True)
            return
        lines = []
        for x in rows:
            uid = x.get("user_id")
            member = interaction.guild.get_member(uid) if uid else None
            who = member.display_name if member else str(uid or "unknown")
            unix = int(datetime.fromisoformat(x["at"]).timestamp())
            lines.append(f"• **{who}** — `{x.get('action', 'action')}` · <t:{unix}:R> · `{clip(x.get('content', ''), 100)}`")
        embed = make_embed(title="🛡️ AutoMod — Recent Activity", description="\n".join(lines), color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 4. Member local time ────────────────────────────────────────────────

    @app_commands.command(name="member_time", description="Show the best available local-time information for a member")
    async def member_time(self, interaction: discord.Interaction, member: discord.Member):
        # Discord's bot API does not expose a member's timezone, locale or country.
        # Never infer it from IDs, names, avatars or language. If the member has a
        # timezone recorded by another future source, this command can consume it.
        known = kv_get(f"member_timezone:{member.id}", None)
        if isinstance(known, dict) and known.get("timezone"):
            try:
                from zoneinfo import ZoneInfo
                dt = datetime.now(ZoneInfo(str(known["timezone"])))
                country = known.get("country") or "Not provided"
                description = f"**Timezone:** `{known['timezone']}`\n**Local time:** <t:{int(dt.timestamp())}:F>\n**Country:** `{country}`"
            except Exception:
                description = f"**Timezone:** `{known.get('timezone')}`\n**Country:** `{known.get('country') or 'Not provided'}`"
        else:
            description = (
                "Discord does not expose a member's timezone or country to bots.\n\n"
                "I will not guess it from the member's name, language, avatar or ID. "
                "If you later store a timezone for this member, the command can display it."
            )
        embed = make_embed(title=f"🕒 Local Time — {member.display_name}", description=description, color=discord.Color.teal())
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 5. Chat/minigame ranking ────────────────────────────────────────────

    @app_commands.command(name="chat_ranking", description="Top 10 chat and minigame activity in the configured rooms")
    async def chat_ranking(self, interaction: discord.Interaction):
        pairs = sorted(((int(uid), int(count)) for uid, count in self._chat_counts.items()), key=lambda x: x[1], reverse=True)[:10]
        pairs = [(uid, count) for uid, count in pairs if interaction.guild.get_member(uid)]
        if not pairs:
            await interaction.response.send_message("No tracked activity in the configured chat/minigame channels yet.", ephemeral=True)
            return
        first_id, first_count = pairs[0]
        first = interaction.guild.get_member(first_id)
        lines = [f"**1. {user_name(first)}** — `{first_count}` messages"]
        for idx, (uid, count) in enumerate(pairs[1:], 2):
            member = interaction.guild.get_member(uid)
            if member:
                lines.append(f"**{idx}.** {user_name(member)} — `{count}` messages")
        embed = make_embed(title="🏆 TOP 10 — Chat & Mini Games", description="\n".join(lines), color=discord.Color.gold())
        if first:
            embed.set_thumbnail(url=first.display_avatar.url)
            embed.add_field(name="🥇 #1", value=f"**{user_name(first)}**\n`{first_count}` messages", inline=False)
        embed.set_footer(text="Rooms: 1553823431349371042 · 1531417799300350073")
        await interaction.response.send_message(embed=embed)

    # ── 6. Media ranking ────────────────────────────────────────────────────

    @app_commands.command(name="media_ranking", description="Top 10 members sending photos and videos in the media category")
    async def media_ranking(self, interaction: discord.Interaction):
        pairs = sorted(((int(uid), int(count)) for uid, count in self._media_counts.items()), key=lambda x: x[1], reverse=True)[:10]
        pairs = [(uid, count) for uid, count in pairs if interaction.guild.get_member(uid)]
        if not pairs:
            await interaction.response.send_message("No media activity recorded in that category yet.", ephemeral=True)
            return
        first_id, first_count = pairs[0]
        first = interaction.guild.get_member(first_id)
        lines = [f"**1. {user_name(first)}** — `{first_count}` media"]
        for idx, (uid, count) in enumerate(pairs[1:], 2):
            member = interaction.guild.get_member(uid)
            if member:
                lines.append(f"**{idx}.** {user_name(member)} — `{count}` media")
        embed = make_embed(title="📸 TOP 10 — Photos & Videos", description="\n".join(lines), color=discord.Color.magenta())
        if first:
            embed.set_thumbnail(url=first.display_avatar.url)
            embed.add_field(name="🥇 #1", value=f"**{user_name(first)}**\n`{first_count}` photos/videos", inline=False)
        embed.set_footer(text=f"Category: {MEDIA_CATEGORY_ID}")
        await interaction.response.send_message(embed=embed)

    # ── 8. Role diff ─────────────────────────────────────────────────────────

    @app_commands.command(name="role_diff", description="Show role changes for a member and who made the change")
    async def role_diff(self, interaction: discord.Interaction, member: discord.Member):
        rows = self._role_changes.get(str(member.id), [])[-8:][::-1]
        if not rows:
            await interaction.response.send_message("No role changes have been recorded for this member yet.", ephemeral=True)
            return
        lines = []
        role_names = {r.id: r.name for r in interaction.guild.roles}
        for row in rows:
            added = ", ".join(f"`{role_names.get(x, x)}`" for x in row.get("added", [])) or "none"
            removed = ", ".join(f"`{role_names.get(x, x)}`" for x in row.get("removed", [])) or "none"
            actor = row.get("actor_name") or row.get("actor_id") or "Unknown"
            unix = int(datetime.fromisoformat(row["at"]).timestamp())
            lines.append(f"<t:{unix}:R> · **+** {added} · **−** {removed} · by **{actor}**")
        current_roles = ", ".join(r.mention for r in member.roles if not r.is_default()) or "none"
        embed = make_embed(title=f"🏷️ Role Diff — {member.display_name}", description="**Current roles:** " + current_roles + "\n\n" + "\n".join(lines), color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 9. Permission audit ─────────────────────────────────────────────────

    @app_commands.command(name="permission_audit", description="Scan roles and channels for dangerous permissions")
    async def permission_audit(self, interaction: discord.Interaction):
        guild = interaction.guild
        findings: List[str] = []
        everyone = guild.default_role
        if everyone.permissions.administrator:
            findings.append("@everyone has **Administrator**")
        if everyone.permissions.manage_messages:
            findings.append("@everyone has **Manage Messages**")
        if everyone.permissions.manage_guild:
            findings.append("@everyone has **Manage Server**")
        for role in guild.roles:
            if role.is_default():
                continue
            p = role.permissions
            dangerous = []
            if p.administrator: dangerous.append("Administrator")
            if p.manage_guild: dangerous.append("Manage Server")
            if p.manage_channels: dangerous.append("Manage Channels")
            if p.manage_roles: dangerous.append("Manage Roles")
            if p.ban_members: dangerous.append("Ban Members")
            if p.kick_members: dangerous.append("Kick Members")
            if p.manage_messages: dangerous.append("Manage Messages")
            if dangerous:
                findings.append(f"{role.mention} — {', '.join(dangerous)}")
        for channel in guild.channels:
            ow = channel.overwrites_for(everyone)
            dangerous = []
            if ow.manage_messages is True: dangerous.append("Manage Messages")
            if ow.manage_channels is True: dangerous.append("Manage Channels")
            if ow.manage_roles is True: dangerous.append("Manage Roles")
            if dangerous:
                findings.append(f"#{channel.name} @everyone allow — {', '.join(dangerous)}")
        if not findings:
            findings.append("No dangerous permissions found by this audit.")
        embed = make_embed(title="🔎 Permission Audit", description="\n".join(findings[:30]), color=discord.Color.red())
        embed.set_footer(text=f"Scanned {len(guild.roles)} roles · {len(guild.channels)} channels")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 10. Mass action alert ───────────────────────────────────────────────

    async def _record_actor_action(self, guild: discord.Guild, actor_id: Optional[int], action: str, detail: str):
        if not actor_id or (self.bot.user and actor_id == self.bot.user.id):
            return
        now = datetime.now(timezone.utc).timestamp()
        key = int(actor_id)
        arr = [(ts, kind) for ts, kind in self._mass_actions[key] if now - ts <= 60]
        arr.append((now, action))
        self._mass_actions[key] = arr
        if len(arr) < 3:
            return
        kinds = Counter(kind for _, kind in arr)
        alert = {
            "at": now_iso(),
            "actor_id": actor_id,
            "actions": len(arr),
            "breakdown": dict(kinds),
            "latest": detail,
        }
        self._mass_alerts.append(alert)
        del self._mass_alerts[:-100]
        await self._send_staff_log(
            "🚨 Mass action alert",
            f"**Executor:** <@{actor_id}> (`{actor_id}`)\n"
            f"**Last 60s:** `{len(arr)}` actions\n"
            f"**Breakdown:** `{dict(kinds)}`\n"
            f"**Latest:** {detail}",
            channel_id=MASS_ACTION_LOG_CHANNEL,
            color=discord.Color.red(),
        )
        # Prevent repeated spam while the burst continues.
        self._mass_actions[key] = arr[-1:]

    async def _recent_audit_executor(self, guild: discord.Guild, action: Any, *, target_id: Optional[int] = None) -> Optional[int]:
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                target = getattr(entry, "target", None)
                if target_id is not None and getattr(target, "id", None) not in (None, target_id):
                    continue
                age = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
                if age <= 15:
                    return getattr(entry.user, "id", None)
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        actor = await self._recent_audit_executor(guild, discord.AuditLogAction.ban, target_id=user.id)
        await self._record_actor_action(guild, actor, "ban", f"ban target `{user.id}`")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        actor = await self._recent_audit_executor(member.guild, discord.AuditLogAction.kick, target_id=member.id)
        if actor:
            await self._record_actor_action(member.guild, actor, "kick", f"kick target `{member.id}`")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or not message.author or message.author.bot:
            return
        actor = await self._recent_audit_executor(message.guild, discord.AuditLogAction.message_delete, target_id=message.author.id)
        await self._record_actor_action(message.guild, actor, "message_delete", f"deleted message `{message.id}` in <#{message.channel.id}>")

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: Sequence[discord.Message]):
        if not messages:
            return
        guild = getattr(messages[0], "guild", None)
        if not guild:
            return
        actor = await self._recent_audit_executor(guild, discord.AuditLogAction.message_bulk_delete)
        await self._record_actor_action(guild, actor, "bulk_delete", f"bulk deleted `{len(messages)}` messages in <#{messages[0].channel.id}>")

    @app_commands.command(name="mass_action_alert", description="Show recent automatic mass-action alerts")
    async def mass_action_alert(self, interaction: discord.Interaction):
        rows = self._mass_alerts[-10:][::-1]
        if not rows:
            await interaction.response.send_message("No mass-action alerts recorded yet. Monitoring is active.", ephemeral=True)
            return
        lines = []
        for row in rows:
            unix = int(datetime.fromisoformat(row["at"]).timestamp())
            lines.append(
                f"• <t:{unix}:R> · **<@{row.get('actor_id')}>** · `{row.get('actions', 0)}` actions · `{row.get('breakdown', {})}`\n"
                f"  {clip(row.get('latest', ''), 180)}"
            )
        embed = make_embed(title="🚨 Mass Action Alerts", description="\n".join(lines), color=discord.Color.red())
        embed.set_footer(text=f"Automatic threshold: 3+ actions by the same executor within 60 seconds")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 11. Detailed message stats ──────────────────────────────────────────

    @app_commands.command(name="msg_stats", description="Show detailed tracked message statistics for a member")
    async def msg_stats(self, interaction: discord.Interaction, member: discord.Member):
        stat = self._msg_stats.get(str(member.id), {})
        messages = int(stat.get("messages", 0))
        chars = int(stat.get("characters", 0))
        media = int(stat.get("media", 0))
        channels = stat.get("channels", {}) or {}
        hours = stat.get("hours", {}) or {}
        weekdays = stat.get("weekdays", {}) or {}
        avg = (chars / messages) if messages else 0
        media_pct = (media / messages * 100) if messages else 0
        favorite = sorted(((int(cid), int(n)) for cid, n in channels.items()), key=lambda x: x[1], reverse=True)[:5]
        fav_text = ", ".join(f"<#{cid}> ({n})" for cid, n in favorite) or "none"
        peak_hour = max(hours.items(), key=lambda x: x[1])[0] if hours else "?"
        peak_day = max(weekdays.items(), key=lambda x: x[1])[0] if weekdays else "?"
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = days[int(peak_day)] if str(peak_day).isdigit() and int(peak_day) < 7 else "?"
        description = (
            f"**Messages:** `{messages}`\n"
            f"**Average message length:** `{avg:.1f}` characters\n"
            f"**Media share:** `{media_pct:.1f}%`\n"
            f"**Most active hour:** `{peak_hour}:00` (São Paulo)\n"
            f"**Most active day:** `{day_name}`"
        )
        embed = make_embed(title=f"📈 Message Stats — {member.display_name}", description=description, color=discord.Color.cyan())
        embed.add_field(name="Favorite channels", value=fav_text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 12. Log health ──────────────────────────────────────────────────────

    @app_commands.command(name="log_health", description="Check log channels and required bot permissions")
    async def log_health(self, interaction: discord.Interaction):
        ids = {
            "Member info": self.bot.config.get("LOG_CHANNEL_ID"),
            "Message log": self.bot.config.get("MESSAGE_LOG_CHANNEL_ID"),
            "WebLogs": self.bot.config.get("WEBLOGS_CHANNEL_ID"),
            "Bot room": self.bot.config.get("BOT_ROOM_CHANNEL_ID"),
            "Invite/Mass log": INVITE_LOG_CHANNEL,
            "AutoMod": TARGET_AUTOMOD_CHANNEL,
        }
        lines = []
        me = interaction.guild.me
        for name, cid in ids.items():
            ch = interaction.guild.get_channel(int(cid)) if cid else None
            if ch is None:
                lines.append(f"❌ **{name}** — `{cid}` not accessible")
                continue
            p = ch.permissions_for(me) if me else None
            ok = p and p.view_channel and p.send_messages and p.embed_links
            lines.append(f"{'✅' if ok else '⚠️'} **{name}** — <#{ch.id}> · View={bool(p and p.view_channel)} Send={bool(p and p.send_messages)} Embed={bool(p and p.embed_links)}")
        embed = make_embed(title="🩺 Log Health", description="\n".join(lines), color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 13. Guild snapshot ──────────────────────────────────────────────────

    def _snapshot(self, guild: discord.Guild) -> Dict[str, Any]:
        role_perms = {str(r.id): int(r.permissions.value) for r in guild.roles}
        channel_perms = {}
        for ch in guild.channels:
            overwrites = {}
            try:
                for target, overwrite in ch.overwrites.items():
                    tid = getattr(target, "id", None)
                    if tid is not None:
                        allow, deny = overwrite.pair()
                        overwrites[str(tid)] = {"allow": int(allow.value), "deny": int(deny.value)}
            except Exception:
                pass
            channel_perms[str(ch.id)] = overwrites
        return {
            "at": now_iso(),
            "members": guild.member_count,
            "member_ids": sorted({m.id for m in guild.members}),
            "member_names": {str(m.id): user_name(m) for m in guild.members},
            "roles": sorted({r.id for r in guild.roles}),
            "channels": sorted({c.id for c in guild.channels}),
            "categories": sorted({c.id for c in guild.categories}),
            "role_names": {str(r.id): r.name for r in guild.roles},
            "channel_names": {str(c.id): c.name for c in guild.channels},
            "role_permissions": role_perms,
            "channel_permissions": channel_perms,
        }

    @app_commands.command(name="guild_snapshot", description="Create a server snapshot and compare it with the previous one")
    async def guild_snapshot(self, interaction: discord.Interaction):
        guild = interaction.guild
        previous = kv_get(f"guild_snapshot:{guild.id}", None)
        current = self._snapshot(guild)
        kv_set(f"guild_snapshot:{guild.id}", current)
        if not previous:
            await interaction.response.send_message("📸 Initial guild snapshot saved. Run `/guild_snapshot` again later to compare changes.", ephemeral=True)
            return
        added_roles = sorted(set(current["roles"]) - set(previous.get("roles", [])))
        removed_roles = sorted(set(previous.get("roles", [])) - set(current["roles", []]))
        added_channels = sorted(set(current["channels"]) - set(previous.get("channels", [])))
        removed_channels = sorted(set(previous.get("channels", [])) - set(current["channels", []]))
        old_members = set(previous.get("member_ids", []))
        new_members = set(current.get("member_ids", []))
        added_members = sorted(new_members - old_members)
        removed_members = sorted(old_members - new_members)
        old_role_perms = previous.get("role_permissions", {})
        new_role_perms = current.get("role_permissions", {})
        changed_role_perms = [rid for rid in set(old_role_perms) & set(new_role_perms) if old_role_perms[rid] != new_role_perms[rid]]
        old_channel_perms = previous.get("channel_permissions", {})
        new_channel_perms = current.get("channel_permissions", {})
        changed_channel_perms = [cid for cid in set(old_channel_perms) & set(new_channel_perms) if old_channel_perms[cid] != new_channel_perms[cid]]
        desc = (
            f"**Members:** `{previous.get('members')}` → `{current.get('members')}` · added: `{len(added_members)}` · removed: `{len(removed_members)}`\n"
            f"**Roles added:** `{len(added_roles)}` · removed: `{len(removed_roles)}` · permission changes: `{len(changed_role_perms)}`\n"
            f"**Channels added:** `{len(added_channels)}` · removed: `{len(removed_channels)}` · permission changes: `{len(changed_channel_perms)}`\n"
        )
        if added_roles:
            desc += "\n**New roles:** " + ", ".join(current["role_names"].get(str(x), str(x)) for x in added_roles[:10])
        if removed_roles:
            desc += "\n**Removed roles:** " + ", ".join(previous.get("role_names", {}).get(str(x), str(x)) for x in removed_roles[:10])
        if added_channels:
            desc += "\n**New channels:** " + ", ".join(current["channel_names"].get(str(x), str(x)) for x in added_channels[:10])
        if removed_channels:
            desc += "\n**Removed channels:** " + ", ".join(previous.get("channel_names", {}).get(str(x), str(x)) for x in removed_channels[:10])
        embed = make_embed(title="📸 Guild Snapshot Diff", description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 14. Investigate ─────────────────────────────────────────────────────

    @app_commands.command(name="investigate", description="Open a staff investigation panel for a member")
    async def investigate(self, interaction: discord.Interaction, member: discord.Member):
        name_cog = self.bot.get_cog("NameHistory")
        names = []
        if name_cog:
            entry = getattr(name_cog, "data", {}).get("members", {}).get(str(member.id), {})
            names = entry.get("names", [])[-5:]
        stats_cog = self.bot.get_cog("Stats")
        total_messages = 0
        if stats_cog:
            total_messages = int(getattr(stats_cog, "data", {}).get("messages", {}).get(str(member.id), 0))
        recent_deleted = self._recent_deleted(member.id)
        joined = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown"
        names_text = "\n".join(f"• `{clip(x.get('display_name'), 60)}` — <t:{int(datetime.fromisoformat(x['at']).timestamp())}:R>" for x in names) or "None recorded"
        deleted_text = "\n".join(f"• <#{x['channel_id']}> — `{clip(x['content'], 90)}`" for x in recent_deleted) or "None cached"
        dm_cog = self.bot.get_cog("DMInbox")
        dm_text = "No recent DM record"
        if dm_cog:
            msgs = getattr(dm_cog, "data", {}).get("conversations", {}).get(str(member.id), [])
            if msgs:
                dm_text = f"{len(msgs)} recorded DM messages · last: `{clip(msgs[-1].get('content', ''), 100)}`"
        embed = make_embed(title=f"🕵️ Investigate — {member.display_name}", color=discord.Color.dark_red())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Server time", value=f"Joined: {joined}\nRoles: {self._role_mentions(member)}", inline=False)
        embed.add_field(name="Name history", value=names_text[:1000], inline=False)
        embed.add_field(name="Stats", value=f"Tracked messages: `{total_messages}`\nRecent activities: `{len(self._activity.get(str(member.id), []))}`", inline=True)
        embed.add_field(name="Deleted messages", value=deleted_text[:1000], inline=True)
        embed.add_field(name="DM record", value=dm_text[:1000], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 15. Who deleted ─────────────────────────────────────────────────────

    @app_commands.command(name="who_deleted", description="Best-effort audit-log lookup for who deleted a message")
    async def who_deleted(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message("❌ Message ID must be numeric.", ephemeral=True)
            return
        web = self.bot.get_cog("WebLogs")
        snap = getattr(web, "_msg_cache", {}).get(mid) if web else None
        author_id = snap.get("author_id") if snap else None
        channel_id = snap.get("channel_id") if snap else interaction.channel_id
        found = []
        try:
            async for entry in interaction.guild.audit_logs(limit=25, action=discord.AuditLogAction.message_delete):
                target = getattr(entry, "target", None)
                target_id = getattr(target, "id", None)
                extra = getattr(entry, "extra", None)
                extra_channel = getattr(extra, "channel", None)
                extra_channel_id = getattr(extra_channel, "id", None)
                if (author_id is None or target_id == author_id) and (extra_channel_id is None or extra_channel_id == channel_id):
                    found.append(entry)
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass
        if not found:
            await interaction.response.send_message(
                "⚠️ Discord's audit log does not expose a guaranteed message-ID → executor mapping. No matching recent deletion entry was found.",
                ephemeral=True,
            )
            return
        entry = found[0]
        executor = getattr(entry, "user", None)
        embed = make_embed(
            title="🗑️ Message deletion audit",
            description=(
                f"**Message ID:** `{mid}`\n**Channel:** <#{channel_id}>\n"
                f"**Likely executor:** {executor.mention if executor else 'Unknown'}\n"
                f"**Audit entry:** <t:{int(entry.created_at.timestamp())}:F>"
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── 16. Peak hours ───────────────────────────────────────────────────────

    @app_commands.command(name="peak_hours", description="Show periods with the highest unique-user engagement")
    async def peak_hours(self, interaction: discord.Interaction):
        hour_users: Counter[int] = Counter()
        weekday_users: Counter[int] = Counter()
        for date_key, hours in self._engagement.items():
            try:
                dt = datetime.fromisoformat(date_key).date()
            except ValueError:
                continue
            for hour, users in hours.items():
                count = len(set(users))
                hour_users[int(hour)] += count
                weekday_users[dt.weekday()] += count
        top_hours = hour_users.most_common(5)
        top_days = weekday_users.most_common(7)
        hour_lines = "\n".join(f"• **{h:02d}:00** — `{n}` unique-user engagements" for h, n in top_hours) or "No data yet"
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_lines = "\n".join(f"• **{names[d]}** — `{n}` unique-user engagements" for d, n in top_days) or "No data yet"
        embed = make_embed(
            title="📈 Peak Hours — Real Engagement",
            description="This uses unique active users per hour/day rather than message volume alone.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Top hours (São Paulo)", value=hour_lines, inline=False)
        embed.add_field(name="Top days", value=day_lines, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminTools(bot))
