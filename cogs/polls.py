"""
Poll system inspired by Sesh.fyi — slash + web panel.
Live-updating embed with buttons, single/multi vote, optional end time.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.helpers import make_embed, SERVER_TZ
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.polls")
FILE = "polls.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PollView(discord.ui.View):
    def __init__(self, cog: "Polls", poll_id: str, options: List[str], *, single: bool):
        super().__init__(timeout=None)
        self.cog = cog
        self.poll_id = poll_id
        self.single = single
        for i, opt in enumerate(options[:10]):
            label = opt[:80]
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"poll:{poll_id}:{i}",
                row=i // 5,
            )
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, index: int):
        async def callback(interaction: discord.Interaction):
            await self.cog.handle_vote(interaction, self.poll_id, index, self.single)
        return callback


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(FILE, {"polls": {}})
        self.expire_loop.start()

    def cog_unload(self):
        self.expire_loop.cancel()
        self._save()

    def _save(self):
        save_json(FILE, self.data)

    def _poll(self, poll_id: str) -> Optional[Dict]:
        return self.data.get("polls", {}).get(poll_id)

    def _build_embed(self, poll: Dict) -> discord.Embed:
        total = sum(len(v) for v in poll.get("votes", {}).values())
        lines = []
        for i, opt in enumerate(poll["options"]):
            voters = poll.get("votes", {}).get(str(i), [])
            count = len(voters)
            pct = (count / total * 100) if total else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            lines.append(f"**{i + 1}.** {opt}\n`{bar}` {count} ({pct:.0f}%)")
        desc = poll.get("description") or ""
        if desc:
            desc += "\n\n"
        desc += "\n".join(lines) if lines else "_No votes yet_"
        color = discord.Color.from_str(poll.get("color", "#B450FF")) if poll.get("color") else discord.Color.from_rgb(180, 80, 255)
        embed = discord.Embed(
            title=f"📊 {poll['title']}",
            description=desc,
            color=color,
            timestamp=_now(),
        )
        footer = f"Total votes: {total}"
        if poll.get("single"):
            footer += " · 1 vote per user"
        if poll.get("ends_at"):
            footer += f" · Ends <t:{int(datetime.fromisoformat(poll['ends_at']).timestamp())}:R>"
        if poll.get("closed"):
            footer += " · CLOSED"
        embed.set_footer(text=footer)
        return embed

    async def handle_vote(self, interaction: discord.Interaction, poll_id: str, index: int, single: bool):
        poll = self._poll(poll_id)
        if not poll or poll.get("closed"):
            await interaction.response.send_message("This poll is closed.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        votes: Dict[str, List[str]] = poll.setdefault("votes", {})
        # Remove previous if single
        if single:
            for k, lst in list(votes.items()):
                if uid in lst:
                    lst.remove(uid)
        key = str(index)
        lst = votes.setdefault(key, [])
        if uid in lst:
            lst.remove(uid)
            msg = "Vote removed."
        else:
            lst.append(uid)
            msg = "Vote registered."
        self._save()
        # Update message
        try:
            ch = self.bot.get_channel(poll["channel_id"])
            if ch:
                msg_obj = await ch.fetch_message(poll["message_id"])
                await msg_obj.edit(embed=self._build_embed(poll))
        except Exception:
            logger.exception("Failed to update poll message")
        await interaction.response.send_message(msg, ephemeral=True)

    @tasks.loop(minutes=1)
    async def expire_loop(self):
        now = _now()
        changed = False
        for pid, poll in list(self.data.get("polls", {}).items()):
            if poll.get("closed") or not poll.get("ends_at"):
                continue
            try:
                ends = datetime.fromisoformat(poll["ends_at"])
                if ends.tzinfo is None:
                    ends = ends.replace(tzinfo=timezone.utc)
                if now >= ends:
                    poll["closed"] = True
                    changed = True
                    try:
                        ch = self.bot.get_channel(poll["channel_id"])
                        if ch and poll.get("message_id"):
                            m = await ch.fetch_message(poll["message_id"])
                            await m.edit(embed=self._build_embed(poll), view=None)
                    except Exception:
                        pass
            except Exception:
                continue
        if changed:
            self._save()

    @expire_loop.before_loop
    async def before_expire(self):
        await self.bot.wait_until_ready()

    async def create_poll(
        self,
        *,
        channel: discord.TextChannel,
        title: str,
        options: List[str],
        description: str = "",
        single: bool = False,
        hours: Optional[float] = None,
        color: str = "#B450FF",
        author_id: Optional[int] = None,
    ) -> Dict:
        options = [o.strip() for o in options if o and o.strip()][:10]
        if len(options) < 2:
            raise ValueError("Need at least 2 options")
        poll_id = f"{int(_now().timestamp())}"
        ends_at = None
        if hours and hours > 0:
            ends_at = (_now() + timedelta(hours=hours)).isoformat()
        poll = {
            "id": poll_id,
            "title": title[:256],
            "description": description[:1000],
            "options": options,
            "votes": {str(i): [] for i in range(len(options))},
            "single": single,
            "channel_id": channel.id,
            "message_id": None,
            "ends_at": ends_at,
            "closed": False,
            "color": color,
            "author_id": author_id,
            "created_at": _now().isoformat(),
        }
        view = PollView(self, poll_id, options, single=single)
        embed = self._build_embed(poll)
        msg = await channel.send(embed=embed, view=view)
        poll["message_id"] = msg.id
        self.data.setdefault("polls", {})[poll_id] = poll
        self._save()
        # Persist view for restarts
        self.bot.add_view(view, message_id=msg.id)
        return poll

    @app_commands.command(name="poll", description="Create a poll (Sesh-style live results)")
    @app_commands.describe(
        title="Poll question / title",
        option1="Option 1",
        option2="Option 2",
        option3="Option 3 (optional)",
        option4="Option 4 (optional)",
        option5="Option 5 (optional)",
        single_vote="Limit to one vote per user",
        hours="Auto-close after N hours (0 = no limit)",
        channel="Channel to post (default: current)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.cooldown(1, 5.0)
    async def poll_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        option1: str,
        option2: str,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        option5: Optional[str] = None,
        single_vote: bool = False,
        hours: Optional[float] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("Invalid channel.", ephemeral=True)
            return
        opts = [option1, option2]
        for o in (option3, option4, option5):
            if o:
                opts.append(o)
        try:
            poll = await self.create_poll(
                channel=ch,
                title=title,
                options=opts,
                single=single_vote,
                hours=hours,
                author_id=interaction.user.id,
            )
            await interaction.followup.send(f"✅ Poll created in {ch.mention} (id `{poll['id']}`)", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)

    @app_commands.command(name="poll_end", description="Force-end a poll by ID")
    @app_commands.describe(poll_id="Poll ID shown when created")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def poll_end(self, interaction: discord.Interaction, poll_id: str):
        poll = self._poll(poll_id.strip())
        if not poll:
            await interaction.response.send_message("Poll not found.", ephemeral=True)
            return
        poll["closed"] = True
        self._save()
        try:
            ch = self.bot.get_channel(poll["channel_id"])
            if ch and poll.get("message_id"):
                m = await ch.fetch_message(poll["message_id"])
                await m.edit(embed=self._build_embed(poll), view=None)
        except Exception:
            pass
        await interaction.response.send_message("✅ Poll closed.", ephemeral=True)

    @app_commands.command(name="poll_list", description="List active polls")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def poll_list(self, interaction: discord.Interaction):
        active = [p for p in self.data.get("polls", {}).values() if not p.get("closed")]
        if not active:
            await interaction.response.send_message("No active polls.", ephemeral=True)
            return
        lines = [f"`{p['id']}` — **{p['title']}** · <#{p['channel_id']}>" for p in active[:20]]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def cog_load(self):
        # Re-register persistent views
        for pid, poll in self.data.get("polls", {}).items():
            if poll.get("closed") or not poll.get("message_id"):
                continue
            view = PollView(self, pid, poll["options"], single=bool(poll.get("single")))
            self.bot.add_view(view, message_id=poll["message_id"])


async def setup(bot: commands.Bot):
    await bot.add_cog(Polls(bot))
