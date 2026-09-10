"""Server activity stats and weekly top media."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.helpers import make_embed, is_media_in_message
from utils.storage import load_json, save_json, default_stats

logger = logging.getLogger("bovary_bot.stats")
STATS_FILE = "stats.json"


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(STATS_FILE, default_stats())
        self._ensure_keys()
        self.save_loop.start()
        self.weekly_loop.start()

    def _ensure_keys(self):
        d = default_stats()
        for k, v in d.items():
            if k not in self.data:
                self.data[k] = v

    def cog_unload(self):
        self.save_loop.cancel()
        self.weekly_loop.cancel()
        save_json(STATS_FILE, self.data)

    def _save(self):
        save_json(STATS_FILE, self.data)

    @tasks.loop(minutes=5)
    async def save_loop(self):
        self._save()

    @save_loop.before_loop
    async def before_save(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def weekly_loop(self):
        """Compute weekly top media every day; reset scores on Monday."""
        now = datetime.now(timezone.utc)
        top = self._top_media()
        if top:
            self.data["weekly_top"] = top
            self._save()
        if now.weekday() == 0 and now.hour < 2:
            self.data["media_scores"] = {}
            self._save()

    @weekly_loop.before_loop
    async def before_weekly(self):
        await self.bot.wait_until_ready()

    def _inc_user(self, key: str, user_id: int, amount: int = 1):
        bucket = self.data.setdefault(key, {})
        sid = str(user_id)
        bucket[sid] = bucket.get(sid, 0) + amount

    def _top_media(self) -> Optional[Dict]:
        scores = self.data.get("media_scores") or {}
        if not scores:
            return None
        best_id, best = max(scores.items(), key=lambda x: x[1].get("score", 0))
        if best.get("score", 0) <= 0:
            return None
        return {"message_id": best_id, **best}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.author or message.author.bot:
            return
        self._inc_user("messages", message.author.id)
        now = datetime.now(timezone.utc)
        self.data["hourly"][str(now.hour)] = self.data.get("hourly", {}).get(str(now.hour), 0) + 1
        self.data["weekday"][str(now.weekday())] = self.data.get("weekday", {}).get(str(now.weekday()), 0) + 1

        if is_media_in_message(message):
            mid = str(message.id)
            self.data.setdefault("media_scores", {})[mid] = {
                "score": 0,
                "channel_id": message.channel.id,
                "author_id": message.author.id,
                "jump_url": message.jump_url,
                "created": now.isoformat(),
            }

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or not payload.user_id:
            return
        if payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return
        self._inc_user("reactions_given", payload.user_id)
        mid = str(payload.message_id)
        media = self.data.get("media_scores", {})
        if mid in media:
            media[mid]["score"] = media[mid].get("score", 0) + 1

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        mid = str(payload.message_id)
        media = self.data.get("media_scores", {})
        if mid in media:
            media[mid]["score"] = max(0, media[mid].get("score", 0) - 1)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self.data["joins"] = self.data.get("joins", 0) + 1

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        self.data["leaves"] = self.data.get("leaves", 0) + 1

    def _topk(self, key: str, n: int = 10) -> List[Tuple[str, int]]:
        bucket = self.data.get(key) or {}
        items = sorted(bucket.items(), key=lambda x: x[1], reverse=True)
        return items[:n]

    @app_commands.command(name="stats", description="Show server activity statistics")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stats_cmd(self, interaction: discord.Interaction):
        embed = make_embed(title="◈ Server Statistics", color=discord.Color.from_rgb(0, 220, 255))
        embed.add_field(
            name="Members",
            value=f"Joins: **{self.data.get('joins', 0)}**\nLeaves: **{self.data.get('leaves', 0)}**",
            inline=True,
        )

        top_msg = self._topk("messages", 5)
        if top_msg:
            lines = [f"<@{uid}> — `{n}` msgs" for uid, n in top_msg]
            embed.add_field(name="Top chatters", value="\n".join(lines), inline=False)

        top_react = self._topk("reactions_given", 5)
        if top_react:
            lines = [f"<@{uid}> — `{n}` reactions" for uid, n in top_react]
            embed.add_field(name="Top reactors", value="\n".join(lines), inline=False)

        hourly = self.data.get("hourly") or {}
        if any(hourly.values()):
            peak_h = max(hourly.items(), key=lambda x: x[1])
            embed.add_field(name="Peak hour (UTC)", value=f"**{peak_h[0]}:00** (`{peak_h[1]}` events)", inline=True)

        weekday = self.data.get("weekday") or {}
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        if any(weekday.values()):
            peak_d = max(weekday.items(), key=lambda x: x[1])
            embed.add_field(
                name="Peak day",
                value=f"**{names[int(peak_d[0])]}** (`{peak_d[1]}` events)",
                inline=True,
            )

        top = self.data.get("weekly_top") or self._top_media()
        if top:
            embed.add_field(
                name="Top media (period)",
                value=f"Score **{top.get('score', 0)}** — [Jump]({top.get('jump_url', '#')})",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="topmedia",
        description="Show or post the most reacted media of the period",
    )
    @app_commands.describe(post="If true, posts a public highlight message")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def topmedia(self, interaction: discord.Interaction, post: bool = False):
        top = self.data.get("weekly_top") or self._top_media()
        if not top:
            await interaction.response.send_message(
                "No media scores recorded yet.", ephemeral=True
            )
            return

        embed = make_embed(
            title="◈ Top Media of the Period",
            description=(
                f"**Score:** {top.get('score', 0)} reactions\n"
                f"**Author:** <@{top.get('author_id')}>\n"
                f"[Jump to message]({top.get('jump_url', '#')})"
            ),
            color=discord.Color.from_rgb(255, 60, 160),
        )
        if post:
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
