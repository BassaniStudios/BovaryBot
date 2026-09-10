"""Server activity stats, weekly top media, and chart images."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.helpers import make_embed, is_media_in_message, SERVER_TZ
from utils.storage import load_json, save_json, default_stats

logger = logging.getLogger("bovary_bot.stats")
STATS_FILE = "stats.json"


def _make_bar_chart(title: str, labels: List[str], values: List[float], color: str = "#B450FF") -> Optional[io.BytesIO]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed — skip charts")
        return None

    fig, ax = plt.subplots(figsize=(8, 4), facecolor="#0a0a12")
    ax.set_facecolor("#12121e")
    bars = ax.bar(labels, values, color=color, edgecolor="#2a2a45")
    ax.set_title(title, color="#e8e8f0", fontsize=12, pad=10)
    ax.tick_params(colors="#8888a8", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#2a2a45")
    ax.yaxis.label.set_color("#8888a8")
    ax.xaxis.label.set_color("#8888a8")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


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

    @tasks.loop(hours=1)
    async def weekly_loop(self):
        now_sp = datetime.now(SERVER_TZ)
        top = self._top_media()
        if top:
            self.data["weekly_top"] = top
            self._save()
        today_key = now_sp.strftime("%Y-%m-%d")
        last = self.data.get("last_weekly_reset")
        if now_sp.weekday() == 0 and last != today_key:
            self.data["media_scores"] = {}
            self.data["last_weekly_reset"] = today_key
            self._save()
            logger.info("Weekly media scores reset (Monday SP)")

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

    def _media_channels(self) -> list:
        return self.bot.config.get("MEDIA_SCORE_CHANNEL_IDS") or self.bot.config.get("CHANNEL_IDS", [])

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.author or message.author.bot:
            return
        ignore = self.bot.config.get("IGNORE_CHANNEL_ID")
        if ignore and message.channel.id == ignore:
            return

        self._inc_user("messages", message.author.id)
        now_sp = datetime.now(SERVER_TZ)
        self.data["hourly"][str(now_sp.hour)] = self.data.get("hourly", {}).get(str(now_sp.hour), 0) + 1
        self.data["weekday"][str(now_sp.weekday())] = self.data.get("weekday", {}).get(str(now_sp.weekday()), 0) + 1

        media_channels = self._media_channels()
        if media_channels and message.channel.id not in media_channels:
            return

        if is_media_in_message(message):
            mid = str(message.id)
            self.data.setdefault("media_scores", {})[mid] = {
                "score": 0,
                "channel_id": message.channel.id,
                "author_id": message.author.id,
                "jump_url": message.jump_url,
                "created": datetime.now(timezone.utc).isoformat(),
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

    @app_commands.command(name="stats", description="Show server activity statistics (numbers + charts)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stats_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
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
            embed.add_field(
                name="Peak hour (São Paulo)",
                value=f"**{peak_h[0]}:00** (`{peak_h[1]}` events)",
                inline=True,
            )

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

        files = []
        if hourly and any(hourly.values()):
            labels = [f"{h}" for h in range(24)]
            values = [float(hourly.get(str(h), 0)) for h in range(24)]
            buf = _make_bar_chart("Activity by hour (São Paulo)", labels, values, "#00E5FF")
            if buf:
                files.append(discord.File(buf, filename="hourly.png"))
                embed.set_image(url="attachment://hourly.png")

        if weekday and any(weekday.values()):
            labels = names
            values = [float(weekday.get(str(i), 0)) for i in range(7)]
            buf = _make_bar_chart("Activity by weekday", labels, values, "#B450FF")
            if buf:
                files.append(discord.File(buf, filename="weekday.png"))

        if files:
            await interaction.followup.send(embed=embed, files=files)
        else:
            await interaction.followup.send(embed=embed)

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
