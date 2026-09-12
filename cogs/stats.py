"""Server activity stats and weekly top media (numbers only, no charts)."""
from __future__ import annotations

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


    @app_commands.command(
        name="week_summary",
        description="Activity snapshot for the tracked period (not full chat reading)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def week_summary(self, interaction: discord.Interaction):
        """
        Discord does not give a full 'read all chats' API without scanning every channel.
        This command summarizes what the bot already tracks: messages, media, joins/leaves.
        Narrative AI summary was removed on purpose.
        """
        await interaction.response.defer(ephemeral=True)
        top_msg = self._top("messages", 8)
        top_react = self._top("reactions_given", 5)
        media_top = self._top_media()
        joins = self.data.get("joins", 0)
        leaves = self.data.get("leaves", 0)
        hourly = self.data.get("hourly") or {}
        peak_h = max(hourly.items(), key=lambda x: x[1])[0] if hourly else "?"
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekday = self.data.get("weekday") or {}
        peak_d = max(weekday.items(), key=lambda x: x[1])[0] if weekday else "?"
        try:
            peak_d_name = days[int(peak_d)]
        except Exception:
            peak_d_name = str(peak_d)

        def fmt_users(pairs):
            if not pairs:
                return "_none_"
            return "\n".join(f"• <@{uid}> — **{n}**" for uid, n in pairs)

        embed = make_embed(
            title="📋 Activity summary (tracked data)",
            description=(
                "Based on **bot counters** (not a full transcript of every message).\n"
                "For narrative summaries you would need an AI provider — currently disabled."
            ),
            color=discord.Color.from_rgb(180, 80, 255),
        )
        embed.add_field(name="Joins / Leaves (since counters started)", value=f"**{joins}** in · **{leaves}** out", inline=False)
        embed.add_field(name="Peak hour (São Paulo)", value=f"**{peak_h}h**", inline=True)
        embed.add_field(name="Peak weekday", value=f"**{peak_d_name}**", inline=True)
        embed.add_field(name="Top chatters", value=fmt_users(top_msg), inline=False)
        embed.add_field(name="Top reactors", value=fmt_users(top_react), inline=False)
        if media_top:
            embed.add_field(
                name="Top media",
                value=(
                    f"Score **{media_top.get('score', 0)}** · "
                    f"author <@{media_top.get('author_id')}>\n"
                    f"[Jump]({media_top.get('jump_url', '#')})"
                ),
                inline=False,
            )
        embed.set_footer(text="Bova's Bot · week_summary")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
