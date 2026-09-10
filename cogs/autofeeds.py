"""Scheduled auto-feed messages — interval or fixed daily time, optional embed."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.helpers import SERVER_TZ
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.autofeeds")
FILE = "autofeeds.json"


class AutoFeeds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.feeds: List[Dict[str, Any]] = load_json(FILE, [])
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()
        save_json(FILE, self.feeds)

    def _save(self):
        save_json(FILE, self.feeds)

    def _next_fixed(self, hour: int, minute: int) -> float:
        """Next occurrence of HH:MM in São Paulo timezone."""
        now = datetime.now(SERVER_TZ)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.astimezone(timezone.utc).timestamp()

    @tasks.loop(minutes=1)
    async def loop(self):
        now = datetime.now(timezone.utc)
        changed = False
        for feed in self.feeds:
            if not feed.get("enabled", True):
                continue
            next_unix = feed.get("next_unix")
            if not next_unix or now.timestamp() < next_unix:
                continue
            channel = self.bot.get_channel(feed.get("channel_id"))
            if channel:
                try:
                    await self._post(channel, feed)
                except Exception:
                    logger.exception("AutoFeed send failed id=%s", feed.get("id"))

            # Schedule next
            if feed.get("mode") == "fixed" and feed.get("fixed_hour") is not None:
                feed["next_unix"] = self._next_fixed(
                    int(feed["fixed_hour"]),
                    int(feed.get("fixed_minute", 0)),
                )
            else:
                interval = int(feed.get("interval_minutes", 1440))
                feed["next_unix"] = now.timestamp() + interval * 60
            changed = True
        if changed:
            self._save()

    async def _post(self, channel, feed: dict):
        content = feed.get("message", "")
        role_id = feed.get("role_id")
        if role_id:
            content = f"<@&{role_id}> {content}".strip()

        if feed.get("use_embed"):
            color = feed.get("embed_color", 0xB450FF)
            embed = discord.Embed(
                title=feed.get("embed_title") or None,
                description=feed.get("message", ""),
                color=color,
                timestamp=datetime.now(timezone.utc),
            )
            if feed.get("embed_image"):
                embed.set_image(url=feed["embed_image"])
            embed.set_footer(text="Bova's Bot · AutoFeed")
            mention = f"<@&{role_id}>" if role_id else None
            await channel.send(content=mention, embed=embed)
        else:
            await channel.send(content[:2000] if content else "…")

    @loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="autofeed_add", description="Add a scheduled auto-feed message")
    @app_commands.describe(
        message="Message text (or embed description)",
        channel="Target channel",
        interval_minutes="Repeat every N minutes (ignored if fixed time is set)",
        role="Optional role to mention",
        start_in_minutes="First run in N minutes (default 5, ignored if fixed time)",
        fixed_hour="Fixed daily hour 0-23 (São Paulo) — enables fixed mode",
        fixed_minute="Fixed daily minute 0-59",
        use_embed="Send as embed instead of plain text",
        embed_title="Embed title (if use_embed)",
        embed_image="Optional image URL for embed",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 5.0)
    async def autofeed_add(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel,
        interval_minutes: app_commands.Range[int, 1, 10080] = 1440,
        role: Optional[discord.Role] = None,
        start_in_minutes: app_commands.Range[int, 1, 10080] = 5,
        fixed_hour: Optional[app_commands.Range[int, 0, 23]] = None,
        fixed_minute: app_commands.Range[int, 0, 59] = 0,
        use_embed: bool = False,
        embed_title: Optional[str] = None,
        embed_image: Optional[str] = None,
    ):
        now = datetime.now(timezone.utc)
        mode = "fixed" if fixed_hour is not None else "interval"

        if mode == "fixed":
            next_unix = self._next_fixed(int(fixed_hour), int(fixed_minute))
        else:
            next_unix = now.timestamp() + start_in_minutes * 60

        feed = {
            "id": int(now.timestamp() * 1000) % 10_000_000,
            "message": message,
            "channel_id": channel.id,
            "role_id": role.id if role else None,
            "interval_minutes": interval_minutes,
            "mode": mode,
            "fixed_hour": fixed_hour,
            "fixed_minute": fixed_minute if fixed_hour is not None else None,
            "next_unix": next_unix,
            "enabled": True,
            "use_embed": use_embed,
            "embed_title": embed_title,
            "embed_image": embed_image,
            "embed_color": 0xB450FF,
        }
        self.feeds.append(feed)
        self._save()

        schedule = (
            f"daily at **{fixed_hour:02d}:{fixed_minute:02d}** (SP)"
            if mode == "fixed"
            else f"every **{interval_minutes}** min"
        )
        await interaction.response.send_message(
            f"✅ AutoFeed **#{feed['id']}** → {channel.mention} · {schedule}\n"
            f"First post <t:{int(next_unix)}:R>"
            + (" · **embed**" if use_embed else ""),
            ephemeral=True,
        )

    @app_commands.command(name="autofeed_list", description="List auto-feeds")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autofeed_list(self, interaction: discord.Interaction):
        if not self.feeds:
            await interaction.response.send_message("No auto-feeds configured.", ephemeral=True)
            return
        lines = []
        for f in self.feeds:
            nxt = int(f.get("next_unix", 0))
            mode = f.get("mode", "interval")
            if mode == "fixed":
                sched = f"daily {f.get('fixed_hour', 0):02d}:{f.get('fixed_minute', 0):02d} SP"
            else:
                sched = f"every {f.get('interval_minutes', 1440)} min"
            emb = " · embed" if f.get("use_embed") else ""
            lines.append(
                f"**#{f['id']}** → <#{f['channel_id']}> · "
                f"{'ON' if f.get('enabled') else 'OFF'} · {sched}{emb}\n"
                f"next <t:{nxt}:R> · `{f.get('message', '')[:80]}`"
            )
        await interaction.response.send_message("\n\n".join(lines)[:2000], ephemeral=True)

    @app_commands.command(name="autofeed_remove", description="Remove an auto-feed by ID")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autofeed_remove(self, interaction: discord.Interaction, feed_id: int):
        before = len(self.feeds)
        self.feeds = [f for f in self.feeds if f.get("id") != feed_id]
        self._save()
        await interaction.response.send_message(
            f"Removed {before - len(self.feeds)} feed(s).", ephemeral=True
        )

    @app_commands.command(name="autofeed_toggle", description="Enable/disable an auto-feed")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autofeed_toggle(self, interaction: discord.Interaction, feed_id: int):
        for f in self.feeds:
            if f.get("id") == feed_id:
                f["enabled"] = not f.get("enabled", True)
                self._save()
                await interaction.response.send_message(
                    f"Feed **#{feed_id}** is now **{'ON' if f['enabled'] else 'OFF'}**.",
                    ephemeral=True,
                )
                return
        await interaction.response.send_message("Feed not found.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoFeeds(bot))
