"""
The Love Professor — GTA Online arcade-style love tester mini-game.
Persistent sticky panel, queue matching, challenge system, admin test mode.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.loveprofessor")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOGO_URL = "https://ik.imagekit.io/BassaniStudios/TheLoveProfessor-GTAO-ArcadeGameLogo.webp"
ALLOWED_CHANNEL_ID = 1553823431349371042
COOLDOWN_SECONDS = 90
CHALLENGE_TIMEOUT = 600  # 10 minutes — plenty of time to accept
PANEL_STATE_FILE = "loveprofessor_panel.json"

LEVEL_COLORS = [
    discord.Color.from_rgb(100, 180, 255),   # 1 Ice Cold
    discord.Color.from_rgb(120, 160, 220),   # 2 Cold Shoulder
    discord.Color.from_rgb(140, 180, 200),   # 3 Thaw Out
    discord.Color.from_rgb(180, 200, 160),   # 4 Clammy
    discord.Color.from_rgb(220, 200, 100),   # 5 Warmer
    discord.Color.from_rgb(255, 180, 80),    # 6 Flushed
    discord.Color.from_rgb(255, 120, 60),    # 7 Getting Steamy
    discord.Color.from_rgb(255, 70, 40),     # 8 Burning Loins
    discord.Color.from_rgb(255, 40, 60),     # 9 Hot n' Heavy
    discord.Color.from_rgb(255, 20, 100),    # 10 Sizzlin'
]

# Dark arcade cabinet color
ARCADE_COLOR = discord.Color.from_rgb(20, 12, 40)
ARCADE_PINK = discord.Color.from_rgb(255, 40, 120)
ARCADE_GOLD = discord.Color.from_rgb(255, 200, 50)

RESULTS = [
    {
        "name": "Ice Cold",
        "emoji": "🧊",
        "bar": 1,
        "quote": "You two share the same emotional temperature as a body in the morgue freezer. Congrats — the mutual hatred is professional-grade.",
        "color_idx": 0,
    },
    {
        "name": "Cold Shoulder",
        "emoji": "🥶",
        "bar": 2,
        "quote": "They gave you the cold shoulder so hard you almost caught emotional pneumonia. Recommendation: stop texting 'hey' at 3 a.m.",
        "color_idx": 1,
    },
    {
        "name": "Thaw Out",
        "emoji": "❄️",
        "bar": 3,
        "quote": "The ice is melting… very slowly. Like an ex who still sends memes once in a while. Nobody's impressed.",
        "color_idx": 2,
    },
    {
        "name": "Clammy",
        "emoji": "😓",
        "bar": 4,
        "quote": "Your chemistry is about as good as sweaty hands on a first date. Uncomfortable, sticky, and everyone's pretending it's fine.",
        "color_idx": 3,
    },
    {
        "name": "Warmer",
        "emoji": "🌤️",
        "bar": 5,
        "quote": "It's heating up… like coffee left in the microwave. Still drinkable, but nobody's going to be impressed.",
        "color_idx": 4,
    },
    {
        "name": "Flushed",
        "emoji": "😳",
        "bar": 6,
        "quote": "You two are red. Not from lust. From second-hand embarrassment. Congrats — even the Professor finds this awkward.",
        "color_idx": 5,
    },
    {
        "name": "Getting Steamy",
        "emoji": "♨️",
        "bar": 7,
        "quote": "Steam is rising. Someone opened the bathroom window after a shower and now the mirror is fogged up with unmet expectations.",
        "color_idx": 6,
    },
    {
        "name": "Burning Loins",
        "emoji": "🔥",
        "bar": 8,
        "quote": "The loins are on fire. Literally. Someone call the fire department before this turns into a workplace incident.",
        "color_idx": 7,
    },
    {
        "name": "Hot n' Heavy",
        "emoji": "❤️‍🔥",
        "bar": 9,
        "quote": "Heavy and hot. Like that 2 a.m. 'we need to talk' conversation. Sex? Maybe. Guaranteed trauma? Absolutely.",
        "color_idx": 8,
    },
    {
        "name": "Sizzlin'",
        "emoji": "🌶️",
        "bar": 10,
        "quote": "You're frying. The love is so hot the Professor almost melted the circuit board. Get a room before the cops show up.",
        "color_idx": 9,
    },
]


# ---------------------------------------------------------------------------
# Helpers — arcade visual
# ---------------------------------------------------------------------------
def _meter_blocks(level: int) -> str:
    """Emoji-style meter — more readable than pure ASCII."""
    filled = max(0, min(level, 10))
    empty = 10 - filled
    return "▰" * filled + "▱" * empty


def _arcade_frame(inner: str) -> str:
    return f"```\n{inner}\n```"


def build_result_embed(
    user1: discord.abc.User,
    user2: discord.abc.User,
    result: dict,
    anim_step: Optional[int] = None,
) -> discord.Embed:
    color = LEVEL_COLORS[result["color_idx"]]

    if anim_step is not None:
        meter = _meter_blocks(anim_step)
        machine = (
            "╔══════════════════════════════╗\n"
            "║     THE LOVE PROFESSOR       ║\n"
            "║   ░░ ANALYZING CHEMISTRY ░░  ║\n"
            "╠══════════════════════════════╣\n"
            f"║  {meter}  ║\n"
            "╚══════════════════════════════╝"
        )
        embed = discord.Embed(
            title="💘 THE LOVE PROFESSOR",
            description=(
                f"{_arcade_frame(machine)}\n"
                f"**{user1.display_name}**  ×  **{user2.display_name}**\n\n"
                f"*Please wait while the machine calculates...*"
            ),
            color=ARCADE_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=LOGO_URL)
        embed.set_footer(text="◆ ARCADE CABINET · THE LOVE PROFESSOR ◆")
        return embed

    # Final result — title is the biggest text Discord allows in embeds
    meter = _meter_blocks(result["bar"])
    embed = discord.Embed(
        title=f"{result['emoji']}  {result['name'].upper()}",
        description=(
            f"**{user1.mention}**  ×  **{user2.mention}**\n\n"
            f"> ### ❝ {result['quote']} ❞\n\n"
            f"**LOVE METER**\n"
            f"`{meter}`  **{result['bar']}/10**"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="◆ ARCADE CABINET · THE LOVE PROFESSOR · 100% SCIENTIFIC ◆")
    return embed


def build_panel_embed(waiting_user: Optional[discord.abc.User] = None) -> discord.Embed:
    if waiting_user:
        status = f"⏳ **WAITING** — {waiting_user.mention} is at the machine"
        tip = "Click **Play Now** to join them and start the test!"
        color = ARCADE_GOLD
    else:
        status = "🟢 **READY** — Insert player"
        tip = "Click **Play Now** to step up to the machine."
        color = ARCADE_PINK

    cabinet = (
        "╔════════════════════════════════╗\n"
        "║                                ║\n"
        "║      THE LOVE PROFESSOR        ║\n"
        "║   ─────────────────────────    ║\n"
        "║    BFF or basically platonic?  ║\n"
        "║    Grab the vibrating handle.  ║\n"
        "║                                ║\n"
        "║   Ice Cold  ←——————→  Sizzlin' ║\n"
        "║                                ║\n"
        "╚════════════════════════════════╝"
    )

    embed = discord.Embed(
        title="💘 THE LOVE PROFESSOR",
        description=(
            f"{_arcade_frame(cabinet)}\n"
            f"{status}\n\n"
            f"{tip}\n\n"
            f"**🎮 Play Now** — join queue / match with whoever is waiting\n"
            f"**🚪 Cancel Wait** — leave the queue\n"
            f"**💘 Challenge Someone** — pick a specific person"
        ),
        color=color,
    )
    embed.set_image(url=LOGO_URL)
    embed.set_footer(text="◆ ARCADE · THE LOVE PROFESSOR · NO TIME LIMIT ON QUEUE ◆")
    return embed


# ---------------------------------------------------------------------------
# Animation runner
# ---------------------------------------------------------------------------
async def run_love_test(
    channel: discord.abc.Messageable,
    user1: discord.abc.User,
    user2: discord.abc.User,
    *,
    reply_to: Optional[discord.Message] = None,
) -> discord.Message:
    """Run meter animation + final result. Returns the result message."""
    result = random.choice(RESULTS)

    anim_embed = build_result_embed(user1, user2, result, anim_step=0)
    if reply_to is not None:
        msg = await reply_to.reply(embed=anim_embed, mention_author=False)
    else:
        msg = await channel.send(embed=anim_embed)

    target_bar = result["bar"]
    for step in range(0, target_bar + 1):
        await asyncio.sleep(0.40)
        try:
            await msg.edit(embed=build_result_embed(user1, user2, result, anim_step=step))
        except (discord.NotFound, discord.HTTPException):
            return msg

    await asyncio.sleep(0.55)
    try:
        await msg.edit(embed=build_result_embed(user1, user2, result))
    except (discord.NotFound, discord.HTTPException):
        pass
    return msg


# ---------------------------------------------------------------------------
# Challenge Accept / Decline view  (long timeout — 10 min)
# ---------------------------------------------------------------------------
class ChallengeView(discord.ui.View):
    def __init__(
        self,
        cog: "LoveProfessor",
        challenger: discord.Member,
        target: discord.Member,
        *,
        timeout: float = CHALLENGE_TIMEOUT,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.challenger = challenger
        self.target = target
        self.resolved = False
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "❌ Only the challenged person can respond.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Accept 💘", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            return
        self.resolved = True
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore

        await interaction.response.edit_message(
            content=f"✅ {self.target.mention} accepted the challenge from {self.challenger.mention}!",
            embed=None,
            view=self,
        )
        await run_love_test(
            interaction.channel,
            self.challenger,
            self.target,
            reply_to=interaction.message,
        )

    @discord.ui.button(label="Decline 💔", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            return
        self.resolved = True
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore

        machine = (
            "╔══════════════════════════════╗\n"
            "║     THE LOVE PROFESSOR       ║\n"
            "║        ◆ DECLINED ◆          ║\n"
            "╚══════════════════════════════╝"
        )
        embed = discord.Embed(
            title="",
            description=(
                f"{_arcade_frame(machine)}\n"
                f"{self.target.mention} declined the challenge from {self.challenger.mention}.\n\n"
                f"*Cold. Very cold. Ice Cold energy detected.*"
            ),
            color=discord.Color.from_rgb(100, 140, 200),
        )
        embed.set_thumbnail(url=LOGO_URL)
        embed.set_footer(text="◆ ARCADE CABINET · THE LOVE PROFESSOR ◆")
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    async def on_timeout(self):
        if self.resolved or not self.message:
            return
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            machine = (
                "╔══════════════════════════════╗\n"
                "║     THE LOVE PROFESSOR       ║\n"
                "║        ◆ EXPIRED ◆           ║\n"
                "╚══════════════════════════════╝"
            )
            embed = discord.Embed(
                title="",
                description=(
                    f"{_arcade_frame(machine)}\n"
                    f"Challenge from {self.challenger.mention} to {self.target.mention} expired.\n"
                    f"Nobody grabbed the handle in time. (10 min limit)"
                ),
                color=discord.Color.dark_grey(),
            )
            embed.set_thumbnail(url=LOGO_URL)
            await self.message.edit(content=None, embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


# ---------------------------------------------------------------------------
# User select for Challenge
# ---------------------------------------------------------------------------
class ChallengeUserSelect(discord.ui.UserSelect):
    def __init__(self, cog: "LoveProfessor"):
        super().__init__(
            placeholder="Select someone to challenge...",
            min_values=1,
            max_values=1,
            row=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        challenger = interaction.user

        if target.id == challenger.id:
            await interaction.response.send_message(
                "❌ You can't challenge yourself. That's concerning.",
                ephemeral=True,
            )
            return
        if target.bot:
            await interaction.response.send_message(
                "❌ Bots don't have hearts (literally). Pick a human.",
                ephemeral=True,
            )
            return
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ The Love Professor only works in the arcade channel.",
                ephemeral=True,
            )
            return

        remaining = self.cog._check_cooldown(challenger.id)
        if remaining > 0:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            await interaction.response.send_message(
                f"⏳ Machine is still cooling down. Wait **{time_str}**.",
                ephemeral=True,
            )
            return

        self.cog._set_cooldown(challenger.id)

        machine = (
            "╔══════════════════════════════╗\n"
            "║     THE LOVE PROFESSOR       ║\n"
            "║       ◆ CHALLENGE ◆          ║\n"
            "╚══════════════════════════════╝"
        )
        embed = discord.Embed(
            title="",
            description=(
                f"{_arcade_frame(machine)}\n"
                f"**{challenger.mention}** challenged **{target.mention}**!\n\n"
                f"Grab the vibrating handle and find out your chemistry.\n\n"
                f"👉 {target.mention}, do you accept?\n"
                f"*You have **10 minutes** to respond.*"
            ),
            color=ARCADE_PINK,
        )
        embed.set_thumbnail(url=LOGO_URL)
        embed.set_footer(text="◆ ARCADE · 10 MIN TO ACCEPT ◆")

        view = ChallengeView(self.cog, challenger, target, timeout=CHALLENGE_TIMEOUT)
        await interaction.response.send_message(
            content=f"{target.mention}",
            embed=embed,
            view=view,
        )
        view.message = await interaction.original_response()


class ChallengeSelectView(discord.ui.View):
    def __init__(self, cog: "LoveProfessor"):
        super().__init__(timeout=120.0)
        self.add_item(ChallengeUserSelect(cog))


# ---------------------------------------------------------------------------
# Main persistent panel view
# ---------------------------------------------------------------------------
class LovePanelView(discord.ui.View):
    """Persistent panel — timeout=None so it survives restarts."""

    def __init__(self, cog: "LoveProfessor"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Play Now",
        style=discord.ButtonStyle.success,
        emoji="🎮",
        custom_id="loveprofessor:play",
        row=0,
    )
    async def play_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ The Love Professor only works in the arcade channel.",
                ephemeral=True,
            )
            return

        user = interaction.user
        remaining = self.cog._check_cooldown(user.id)
        if remaining > 0:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            await interaction.response.send_message(
                f"⏳ Machine is still cooling down. Wait **{time_str}**.",
                ephemeral=True,
            )
            return

        waiting = self.cog.waiting_user

        if waiting is not None and waiting.id == user.id:
            await interaction.response.send_message(
                "⏳ You are already waiting for a partner. No time limit — someone will join!",
                ephemeral=True,
            )
            return

        if waiting is not None and waiting.id != user.id:
            partner = waiting
            self.cog.waiting_user = None
            self.cog._set_cooldown(user.id)
            self.cog._set_cooldown(partner.id)

            await interaction.response.defer()

            try:
                await interaction.message.edit(
                    embed=build_panel_embed(None),
                    view=self,
                )
            except (discord.NotFound, discord.HTTPException):
                pass

            match_msg = await interaction.followup.send(
                f"💘 **Match found!** {partner.mention} × {user.mention} — starting the test...",
                wait=True,
            )
            await run_love_test(interaction.channel, partner, user, reply_to=match_msg)
            return

        # Nobody waiting → join queue (NO time limit)
        self.cog.waiting_user = user
        await interaction.response.defer()
        try:
            await interaction.message.edit(
                embed=build_panel_embed(user),
                view=self,
            )
        except (discord.NotFound, discord.HTTPException):
            pass
        await interaction.followup.send(
            f"✅ {user.mention} stepped up to the machine and is waiting for a partner!\n"
            f"*No time limit — stay as long as you want. Use **Cancel Wait** to leave.*",
            ephemeral=False,
        )

    @discord.ui.button(
        label="Cancel Wait",
        style=discord.ButtonStyle.secondary,
        emoji="🚪",
        custom_id="loveprofessor:cancel",
        row=0,
    )
    async def cancel_wait(self, interaction: discord.Interaction, button: discord.ui.Button):
        waiting = self.cog.waiting_user
        if waiting is None or waiting.id != interaction.user.id:
            await interaction.response.send_message(
                "❌ You are not currently waiting.",
                ephemeral=True,
            )
            return

        self.cog.waiting_user = None
        await interaction.response.defer()
        try:
            await interaction.message.edit(
                embed=build_panel_embed(None),
                view=self,
            )
        except (discord.NotFound, discord.HTTPException):
            pass
        await interaction.followup.send(
            f"👋 {interaction.user.mention} left the machine.",
            ephemeral=False,
        )

    @discord.ui.button(
        label="Challenge Someone",
        style=discord.ButtonStyle.primary,
        emoji="💘",
        custom_id="loveprofessor:challenge",
        row=0,
    )
    async def challenge(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ The Love Professor only works in the arcade channel.",
                ephemeral=True,
            )
            return

        remaining = self.cog._check_cooldown(interaction.user.id)
        if remaining > 0:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            await interaction.response.send_message(
                f"⏳ Machine is still cooling down. Wait **{time_str}**.",
                ephemeral=True,
            )
            return

        view = ChallengeSelectView(self.cog)
        await interaction.response.send_message(
            "Select the person you want to challenge:\n*(They will have **10 minutes** to accept)*",
            view=view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class LoveProfessor(commands.Cog):
    """The Love Professor mini-game — sticky arcade panel + queue + challenge."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.waiting_user: Optional[discord.abc.User] = None
        self._cooldowns: dict[int, float] = {}
        self._panel_view: Optional[LovePanelView] = None
        self._panel_message_id: Optional[int] = None
        self._sticky_lock = False
        self._load_panel_state()

    def _load_panel_state(self) -> None:
        data = load_json(PANEL_STATE_FILE, {})
        if isinstance(data, dict):
            mid = data.get("message_id")
            self._panel_message_id = int(mid) if mid else None

    def _save_panel_state(self) -> None:
        save_json(PANEL_STATE_FILE, {"message_id": self._panel_message_id})

    def _check_cooldown(self, user_id: int) -> float:
        last = self._cooldowns.get(user_id)
        if last is None:
            return 0.0
        elapsed = datetime.now(timezone.utc).timestamp() - last
        return max(0.0, COOLDOWN_SECONDS - elapsed)

    def _set_cooldown(self, user_id: int) -> None:
        self._cooldowns[user_id] = datetime.now(timezone.utc).timestamp()

    async def cog_load(self) -> None:
        self._panel_view = LovePanelView(self)
        self.bot.add_view(self._panel_view)
        logger.info("LoveProfessor persistent panel view registered")

    # ------------------------------------------------------------------
    # Sticky behaviour — keep panel at the bottom of the channel
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != ALLOWED_CHANNEL_ID:
            return
        if message.author.bot:
            return
        if not self._panel_message_id:
            return
        if self._sticky_lock:
            return

        self._sticky_lock = True
        try:
            channel = message.channel
            # Delete old panel
            try:
                old = await channel.fetch_message(self._panel_message_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

            # Re-post panel at the bottom
            view = LovePanelView(self)
            self._panel_view = view
            self.bot.add_view(view)
            new_msg = await channel.send(
                embed=build_panel_embed(self.waiting_user),
                view=view,
            )
            self._panel_message_id = new_msg.id
            self._save_panel_state()
        except Exception:
            logger.exception("LoveProfessor sticky repost failed")
        finally:
            self._sticky_lock = False

    # ------------------------------------------------------------------
    # Admin: post the fixed panel
    # ------------------------------------------------------------------
    @app_commands.command(
        name="loveprofessor_panel",
        description="[ADMIN] Post the permanent The Love Professor arcade panel",
    )
    @app_commands.guild_only()
    async def loveprofessor_panel(self, interaction: discord.Interaction):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ This panel can only be posted in the arcade channel.",
                ephemeral=True,
            )
            return

        # Delete previous panel if any
        if self._panel_message_id:
            try:
                old = await interaction.channel.fetch_message(self._panel_message_id)
                await old.delete()
            except Exception:
                pass

        self.waiting_user = None
        view = LovePanelView(self)
        self._panel_view = view
        self.bot.add_view(view)

        embed = build_panel_embed(None)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        self._panel_message_id = msg.id
        self._save_panel_state()
        logger.info(
            "LoveProfessor panel posted by %s in channel %s (msg %s)",
            interaction.user,
            interaction.channel_id,
            msg.id,
        )

    # ------------------------------------------------------------------
    # Admin: test mode (bot plays with you)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="loveprofessor_test",
        description="[ADMIN] Test the love machine — the bot plays with you",
    )
    @app_commands.guild_only()
    async def loveprofessor_test(self, interaction: discord.Interaction):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ Test only works in the arcade channel.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        bot_user = self.bot.user
        human = interaction.user

        match_msg = await interaction.followup.send(
            f"🧪 **Test mode** — {human.mention} × {bot_user.mention}",
            wait=True,
        )
        await run_love_test(interaction.channel, human, bot_user, reply_to=match_msg)

    @loveprofessor_panel.error
    @loveprofessor_test.error
    async def admin_cmd_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Você não possui um dos cargos autorizados para este comando.",
                ephemeral=True,
            )
        else:
            logger.exception("LoveProfessor command error: %s", error)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Something went wrong.",
                    ephemeral=True,
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(LoveProfessor(bot))
