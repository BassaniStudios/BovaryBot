"""Scheduled auto-feed messages (Carl-bot style)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

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
                    content = feed.get("message", "")
                    role_id = feed.get("role_id")
                    if role_id:
                        content = f"<@&{role_id}> {content}"
                    await channel.send(content[:2000])
                except Exception:
                    logger.exception("AutoFeed send failed id=%s", feed.get("id"))
            # schedule next
            interval = int(feed.get("interval_minutes", 1440))
            feed["next_unix"] = now.timestamp() + interval * 60
            changed = True
        if changed:
            self._save()

    @loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="autofeed_add", description="Add a scheduled auto-feed message")
    @app_commands.describe(
        message="Message text",
        channel="Target channel",
        interval_minutes="Repeat every N minutes (default 1440 = daily)",
        role="Optional role to mention",
        start_in_minutes="First run in N minutes (default 5)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autofeed_add(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel,
        interval_minutes: app_commands.Range[int, 1, 10080] = 1440,
        role: Optional[discord.Role] = None,
        start_in_minutes: app_commands.Range[int, 1, 10080] = 5,
    ):
        now = datetime.now(timezone.utc)
        feed = {
            "id": int(now.timestamp() * 1000) % 10_000_000,
            "message": message,
            "channel_id": channel.id,
            "role_id": role.id if role else None,
            "interval_minutes": interval_minutes,
            "next_unix": now.timestamp() + start_in_minutes * 60,
            "enabled": True,
        }
        self.feeds.append(feed)
        self._save()
        await interaction.response.send_message(
            f"✅ AutoFeed **#{feed['id']}** created → {channel.mention} every **{interval_minutes}** min.\n"
            f"First post <t:{int(feed['next_unix'])}:R>",
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
            lines.append(
                f"**#{f['id']}** → <#{f['channel_id']}> · "
                f"{'ON' if f.get('enabled') else 'OFF'} · next <t:{nxt}:R>\n"
                f"`{f.get('message', '')[:80]}`"
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
