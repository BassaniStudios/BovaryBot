"""
The Love Professor — GTA Online arcade-style love tester mini-game.
Persistent sticky panel (delayed), queue matching with lock, challenge system, admin test mode.

Fixes:
- Race condition on waiting_user (asyncio.Lock)
- Sticky panel: delayed re-pin (default 90s) so chat after results is not interrupted
- Cooldown only applied when a test actually starts (match / accept)
- Safer sticky (skip if already last message, proper task cancel, single lock)
- waiting_user stored by id for restart resilience of panel state
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
# Local animated GIF used ONLY on the main sticky panel (results still use LOGO_URL)
PANEL_GIF_PATH = "assets/theloveprofessor.gif"
PANEL_GIF_FILENAME = "theloveprofessor.gif"
ALLOWED_CHANNEL_ID = 1553823431349371042
COOLDOWN_SECONDS = 90
CHALLENGE_TIMEOUT = 600  # 10 minutes — plenty of time to accept
# Delay before sticky panel is moved back to the bottom of the channel.
# Gives people time to comment on results without the panel jumping constantly.
STICKY_DELAY_SECONDS = 90  # between 60–120 as requested
PANEL_STATE_FILE = "loveprofessor_panel.json"

LEVEL_COLORS = [
    discord.Color.from_rgb(80, 140, 255),    # 1  Ice Cold
    discord.Color.from_rgb(90, 150, 240),    # 2  Frozen Solid
    discord.Color.from_rgb(100, 160, 230),   # 3  Cold as Hell
    discord.Color.from_rgb(110, 170, 220),   # 4  Heartless
    discord.Color.from_rgb(120, 180, 210),   # 5  Thaw Out
    discord.Color.from_rgb(140, 190, 200),   # 6  Chilly Business
    discord.Color.from_rgb(160, 200, 180),   # 7  Clammy
    discord.Color.from_rgb(190, 200, 140),   # 8  Slightly Toasty
    discord.Color.from_rgb(220, 200, 100),   # 9  Flushed
    discord.Color.from_rgb(255, 220, 60),    # 10 Burning Touch   (yellow start)
    discord.Color.from_rgb(255, 200, 50),    # 11 Steamy Situation
    discord.Color.from_rgb(255, 180, 40),    # 12 Burning Loins
    discord.Color.from_rgb(255, 160, 30),    # 13 Dangerously Hot
    discord.Color.from_rgb(255, 140, 20),    # 14 Hot n' Heavy
    discord.Color.from_rgb(255, 120, 10),    # 15 Filthy Chemistry (yellow end)
    discord.Color.from_rgb(255, 100, 20),    # 16 Sizzlin'        (orange start)
    discord.Color.from_rgb(255, 80, 30),     # 17 Hellfire Chemistry
    discord.Color.from_rgb(255, 60, 40),     # 18 Point of No Return
    discord.Color.from_rgb(255, 40, 50),     # 19 Certified Freakshow (orange end)
    discord.Color.from_rgb(255, 20, 60),     # 20 The Final Thrust (red)
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
        "quote": "Hotter than an iceberg in winter — morgue freezer temperature. Are you two even alive?",
        "color_idx": 0,
    },
    {
        "name": "Frozen Solid",
        "emoji": "🥶",
        "bar": 2,
        "quote": "Not even global warming can save this romantic disaster.",
        "color_idx": 1,
    },
    {
        "name": "Cold as Hell",
        "emoji": "🥶",
        "bar": 3,
        "quote": "Pure ice. Not even the devil could melt this.",
        "color_idx": 2,
    },
    {
        "name": "Heartless",
        "emoji": "💔",
        "bar": 4,
        "quote": "The heart barely beats, feels nothing, and probably already blocked you.",
        "color_idx": 3,
    },
    {
        "name": "Thaw Out",
        "emoji": "❄️",
        "bar": 5,
        "quote": "The ice is melting… extremely slowly. Like a shy couple on a first date.",
        "color_idx": 4,
    },
    {
        "name": "Chilly Business",
        "emoji": "❄️",
        "bar": 6,
        "quote": "The temperature dropped so fast there wasn't even time to get embarrassed.",
        "color_idx": 5,
    },
    {
        "name": "Clammy",
        "emoji": "😓",
        "bar": 7,
        "quote": "Sweaty-hand first-date chemistry mixed with butterflies of pure anxiety.",
        "color_idx": 6,
    },
    {
        "name": "Slightly Toasty",
        "emoji": "🍞",
        "bar": 8,
        "quote": "There's a spark… but someone left the bread in the toaster too long.",
        "color_idx": 7,
    },
    {
        "name": "Flushed",
        "emoji": "😳",
        "bar": 9,
        "quote": "Red from embarrassment… or is it something else?",
        "color_idx": 8,
    },
    {
        "name": "Burning Touch",
        "emoji": "🔥",
        "bar": 10,
        "quote": "Almost can't pretend they don't want it anymore. There, I said it.",
        "color_idx": 9,
    },
    {
        "name": "Steamy Situation",
        "emoji": "♨️",
        "bar": 11,
        "quote": "Things are heating up, but the intentions are still under investigation.",
        "color_idx": 10,
    },
    {
        "name": "Burning Loins",
        "emoji": "🔥",
        "bar": 12,
        "quote": "Is someone on fire… or did summer arrive early?",
        "color_idx": 11,
    },
    {
        "name": "Dangerously Hot",
        "emoji": "🔥",
        "bar": 13,
        "quote": "The tension is so high even the air conditioner turned on a fan.",
        "color_idx": 12,
    },
    {
        "name": "Hot n' Heavy",
        "emoji": "❤️‍🔥",
        "bar": 14,
        "quote": "Sex? Maybe. Guaranteed trauma. Forbidden and addictive at the same time.",
        "color_idx": 13,
    },
    {
        "name": "Filthy Chemistry",
        "emoji": "😈",
        "bar": 15,
        "quote": "This stopped being flirting a while ago. We all know where this is going… hehehe.",
        "color_idx": 14,
    },
    {
        "name": "Sizzlin'",
        "emoji": "🌶️",
        "bar": 16,
        "quote": "Extremely hot, but everything is under control… (lie — it's burning from the inside).",
        "color_idx": 15,
    },
    {
        "name": "Hellfire Chemistry",
        "emoji": "🔥💋",
        "bar": 17,
        "quote": "An attraction so hot that Hell called asking who stole their fire.",
        "color_idx": 16,
    },
    {
        "name": "Point of No Return",
        "emoji": "🖤🔥",
        "bar": 18,
        "quote": "No going back after this. Everyone already knows. No point pretending anymore.",
        "color_idx": 17,
    },
    {
        "name": "Certified Freakshow",
        "emoji": "😈🔥",
        "bar": 19,
        "quote": "Get the kids out of the room. These two are already sweating.",
        "color_idx": 18,
    },
    {
        "name": "The Final Thrust",
        "emoji": "⚰️🌶️",
        "bar": 20,
        "quote": "**Final phase unlocked.** The filth level has exceeded my terms of service. The bed is on fire, the neighbors called the cops because of the screams — but the screams weren't from the TV. The windows are fogged up. It got so hot that the Devil called the fire department.",
        "color_idx": 19,
    },
]


# ---------------------------------------------------------------------------
# Helpers — arcade visual
# ---------------------------------------------------------------------------
def _meter_blocks(level: int) -> str:
    """20-block love meter.
    Blocks 1-9: cold (blue-ish feel via overall color)
    Blocks 10-15: yellow zone
    Blocks 16-19: orange zone
    Block 20: red
    """
    filled = max(0, min(level, 20))
    empty = 20 - filled
    # Use solid blocks; color is mainly carried by the embed
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
            "╔════════════════════════════════════════╗\n"
            "║        THE LOVE PROFESSOR              ║\n"
            "║     ░░ ANALYZING CHEMISTRY ░░          ║\n"
            "╠════════════════════════════════════════╣\n"
            f"║ {meter} ║\n"
            "╚════════════════════════════════════════╝"
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
            f"`{meter}`  **{result['bar']}/20**"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="◆ ARCADE CABINET · THE LOVE PROFESSOR · 100% SCIENTIFIC ◆")
    return embed


def build_panel_embed(
    waiting_user: Optional[discord.abc.User] = None,
    *,
    anonymous: bool = False,
) -> discord.Embed:
    if waiting_user:
        if anonymous:
            status = "⏳ **WAITING** — Someone is at the machine **anonymously** 🕵️"
            tip = "Click **Play Now** or **Anonymous** to join them and start the test!"
        else:
            status = f"⏳ **WAITING** — {waiting_user.mention} is at the machine"
            tip = "Click **Play Now** or **Anonymous** to join them and start the test!"
        color = ARCADE_GOLD
    else:
        status = "🟢 **READY** — Insert player"
        tip = "Click **Play Now** or **Anonymous** to step up to the machine."
        color = ARCADE_PINK

    embed = discord.Embed(
        title="💘 THE LOVE PROFESSOR",
        description=(
            f"{status}\n\n"
            f"{tip}\n\n"
            f"**🎮 Play Now** — join queue / match with whoever is waiting\n"
            f"**🕵️ Anonymous** — play without revealing your name until the result\n"
            f"**🚪 Cancel Wait** — leave the queue\n"
            f"**💘 Challenge Someone** — pick a specific person"
        ),
        color=color,
    )
    # GIF is attached as a file when the panel message is sent/edited
    embed.set_image(url=f"attachment://{PANEL_GIF_FILENAME}")
    embed.set_footer(
        text=f"◆ ARCADE · THE LOVE PROFESSOR · PANEL RE-PINS AFTER ~{STICKY_DELAY_SECONDS}s QUIET ◆"
    )
    return embed


def _panel_file() -> discord.File:
    """Return a fresh File object for the panel GIF (required on every send/edit)."""
    import os
    # Try several common locations relative to this file / cwd
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), PANEL_GIF_PATH),
        os.path.join(os.path.dirname(__file__), "..", PANEL_GIF_PATH),
        PANEL_GIF_PATH,
        os.path.join("assets", PANEL_GIF_FILENAME),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return discord.File(path, filename=PANEL_GIF_FILENAME)
    raise FileNotFoundError(
        f"Panel GIF not found. Looked in: {candidates}"
    )


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

        # Cooldown only when the test actually starts
        self.cog._set_cooldown(self.challenger.id)
        self.cog._set_cooldown(self.target.id)

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
        # After a test, schedule sticky so panel returns after conversation
        self.cog._schedule_sticky()

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
        self.cog._schedule_sticky()

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
        self.cog._schedule_sticky()


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

        # Cooldown is NOT set here — only when the target accepts (or on Play Now match).
        # Challenger is free to challenge again if declined/expired.

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
        self.cog._schedule_sticky()


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

    async def _handle_join(
        self,
        interaction: discord.Interaction,
        *,
        anonymous: bool,
    ) -> None:
        """Shared logic for Play Now and Anonymous buttons."""
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

        partner = None
        match_msg = None
        was_anonymous = False

        async with self.cog._queue_lock:
            waiting = self.cog.waiting_user

            if waiting is not None and waiting.id == user.id:
                await interaction.response.send_message(
                    "⏳ You are already waiting for a partner. No time limit — someone will join!",
                    ephemeral=True,
                )
                return

            if waiting is not None and waiting.id != user.id:
                # Match found
                partner = waiting
                was_anonymous = self.cog.waiting_anonymous
                self.cog.waiting_user = None
                self.cog._waiting_user_id = None
                self.cog.waiting_anonymous = False
                self.cog._set_cooldown(user.id)
                self.cog._set_cooldown(partner.id)
                self.cog._save_panel_state()

                await interaction.response.defer()

                try:
                    await interaction.message.edit(
                        embed=build_panel_embed(None),
                        attachments=[_panel_file()],
                        view=self,
                    )
                except (discord.NotFound, discord.HTTPException):
                    pass

                # Reveal both names (anonymous is revealed on match)
                if was_anonymous or anonymous:
                    match_msg = await interaction.followup.send(
                        f"💘 **Match found!** {partner.mention} × {user.mention} "
                        f"— starting the test...\n"
                        f"*🕵️ Anonymous player revealed!*",
                        wait=True,
                    )
                else:
                    match_msg = await interaction.followup.send(
                        f"💘 **Match found!** {partner.mention} × {user.mention} — starting the test...",
                        wait=True,
                    )
            else:
                # Nobody waiting → join queue
                self.cog.waiting_user = user
                self.cog._waiting_user_id = user.id
                self.cog.waiting_anonymous = anonymous
                self.cog._save_panel_state()
                await interaction.response.defer()
                try:
                    await interaction.message.edit(
                        embed=build_panel_embed(user, anonymous=anonymous),
                        attachments=[_panel_file()],
                        view=self,
                    )
                except (discord.NotFound, discord.HTTPException):
                    pass

                if anonymous:
                    await interaction.followup.send(
                        f"✅ Someone stepped up to the machine **anonymously** and is waiting for a partner!\n"
                        f"*🕵️ Your identity will only be revealed when the test starts.*\n"
                        f"*No time limit — use **Cancel Wait** to leave.*",
                        ephemeral=False,
                    )
                else:
                    await interaction.followup.send(
                        f"✅ {user.mention} stepped up to the machine and is waiting for a partner!\n"
                        f"*No time limit — stay as long as you want. Use **Cancel Wait** to leave.*",
                        ephemeral=False,
                    )
                self.cog._schedule_sticky()
                return

        # Outside lock: run animation after successful match
        if partner is not None and match_msg is not None:
            await run_love_test(interaction.channel, partner, user, reply_to=match_msg)
            self.cog._schedule_sticky()

    @discord.ui.button(
        label="Play Now",
        style=discord.ButtonStyle.success,
        emoji="🎮",
        custom_id="loveprofessor:play",
        row=0,
    )
    async def play_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_join(interaction, anonymous=False)

    @discord.ui.button(
        label="Anonymous",
        style=discord.ButtonStyle.primary,
        emoji="🕵️",
        custom_id="loveprofessor:anonymous",
        row=0,
    )
    async def anonymous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_join(interaction, anonymous=True)

    @discord.ui.button(
        label="Cancel Wait",
        style=discord.ButtonStyle.secondary,
        emoji="🚪",
        custom_id="loveprofessor:cancel",
        row=0,
    )
    async def cancel_wait(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.cog._queue_lock:
            waiting = self.cog.waiting_user
            if waiting is None or waiting.id != interaction.user.id:
                await interaction.response.send_message(
                    "❌ You are not currently waiting.",
                    ephemeral=True,
                )
                return

            self.cog.waiting_user = None
            self.cog._waiting_user_id = None
            self.cog.waiting_anonymous = False
            self.cog._save_panel_state()

        await interaction.response.defer()
        try:
            await interaction.message.edit(
                embed=build_panel_embed(None),
                attachments=[_panel_file()],
                view=self,
            )
        except (discord.NotFound, discord.HTTPException):
            pass
        await interaction.followup.send(
            f"👋 {interaction.user.mention} left the machine.",
            ephemeral=False,
        )
        self.cog._schedule_sticky()

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
        self._waiting_user_id: Optional[int] = None  # persisted across restarts (best-effort)
        self.waiting_anonymous: bool = False
        self._cooldowns: dict[int, float] = {}
        self._panel_view: Optional[LovePanelView] = None
        self._panel_message_id: Optional[int] = None
        self._queue_lock = asyncio.Lock()
        self._sticky_lock = asyncio.Lock()
        self._sticky_task: Optional[asyncio.Task] = None
        self._load_panel_state()

    def _load_panel_state(self) -> None:
        data = load_json(PANEL_STATE_FILE, {})
        if isinstance(data, dict):
            mid = data.get("message_id")
            self._panel_message_id = int(mid) if mid else None
            wid = data.get("waiting_user_id")
            self._waiting_user_id = int(wid) if wid else None
            self.waiting_anonymous = bool(data.get("waiting_anonymous", False))

    def _save_panel_state(self) -> None:
        wid = None
        if self.waiting_user is not None:
            wid = self.waiting_user.id
        elif self._waiting_user_id is not None:
            wid = self._waiting_user_id
        save_json(
            PANEL_STATE_FILE,
            {
                "message_id": self._panel_message_id,
                "waiting_user_id": wid,
                "waiting_anonymous": self.waiting_anonymous if wid else False,
            },
        )

    def _check_cooldown(self, user_id: int) -> float:
        last = self._cooldowns.get(user_id)
        if last is None:
            return 0.0
        elapsed = datetime.now(timezone.utc).timestamp() - last
        return max(0.0, COOLDOWN_SECONDS - elapsed)

    def _set_cooldown(self, user_id: int) -> None:
        self._cooldowns[user_id] = datetime.now(timezone.utc).timestamp()

    def _schedule_sticky(self) -> None:
        """Cancel any pending sticky and schedule a new one after STICKY_DELAY_SECONDS."""
        if self._sticky_task is not None and not self._sticky_task.done():
            self._sticky_task.cancel()
        self._sticky_task = asyncio.create_task(self._delayed_sticky())

    async def _delayed_sticky(self) -> None:
        try:
            await asyncio.sleep(STICKY_DELAY_SECONDS)
        except asyncio.CancelledError:
            return
        await self._do_sticky_repost()

    async def _do_sticky_repost(self) -> None:
        """Move the panel to the bottom of the channel if needed."""
        if not self._panel_message_id:
            return

        async with self._sticky_lock:
            try:
                channel = self.bot.get_channel(ALLOWED_CHANNEL_ID)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(ALLOWED_CHANNEL_ID)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        return

                if not isinstance(channel, discord.TextChannel):
                    return

                # If panel is already the last message, nothing to do
                try:
                    async for last in channel.history(limit=1):
                        if last.id == self._panel_message_id:
                            return
                        break
                except (discord.Forbidden, discord.HTTPException):
                    pass

                # Delete old panel
                try:
                    old = await channel.fetch_message(self._panel_message_id)
                    await old.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

                # Resolve waiting user for embed (best-effort after restart)
                waiting = self.waiting_user
                if waiting is None and self._waiting_user_id is not None:
                    try:
                        waiting = await self.bot.fetch_user(self._waiting_user_id)
                        self.waiting_user = waiting
                    except (discord.NotFound, discord.HTTPException):
                        self._waiting_user_id = None
                        self.waiting_user = None

                view = LovePanelView(self)
                self._panel_view = view
                self.bot.add_view(view)
                new_msg = await channel.send(
                    embed=build_panel_embed(waiting, anonymous=self.waiting_anonymous),
                    file=_panel_file(),
                    view=view,
                )
                self._panel_message_id = new_msg.id
                self._save_panel_state()
                logger.debug(
                    "LoveProfessor sticky panel reposted (msg %s)",
                    new_msg.id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("LoveProfessor sticky repost failed")

    async def cog_load(self) -> None:
        self._panel_view = LovePanelView(self)
        self.bot.add_view(self._panel_view)
        # Best-effort restore of waiting user after restart
        if self._waiting_user_id is not None and self.waiting_user is None:
            try:
                self.waiting_user = await self.bot.fetch_user(self._waiting_user_id)
            except Exception:
                self._waiting_user_id = None
        logger.info(
            "LoveProfessor persistent panel view registered (sticky delay=%ss)",
            STICKY_DELAY_SECONDS,
        )

    async def cog_unload(self) -> None:
        if self._sticky_task is not None and not self._sticky_task.done():
            self._sticky_task.cancel()
            try:
                await self._sticky_task
            except (asyncio.CancelledError, Exception):
                pass

    # ------------------------------------------------------------------
    # Sticky behaviour — delayed re-pin after channel goes quiet
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != ALLOWED_CHANNEL_ID:
            return
        if message.author.bot:
            return
        if not self._panel_message_id:
            return

        # Any human message resets the quiet timer → panel only moves after
        # STICKY_DELAY_SECONDS of no human activity (lets people discuss results).
        self._schedule_sticky()

    # ------------------------------------------------------------------
    # Admin: post the fixed panel
    # ------------------------------------------------------------------
    @app_commands.command(
        name="loveprofessor_panel",
        description="Post the permanent The Love Professor arcade panel",
    )
    @app_commands.guild_only()
    async def loveprofessor_panel(self, interaction: discord.Interaction):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ This panel can only be posted in the arcade channel.",
                ephemeral=True,
            )
            return

        # Cancel pending sticky while we replace the panel
        if self._sticky_task is not None and not self._sticky_task.done():
            self._sticky_task.cancel()

        # Delete previous panel if any
        if self._panel_message_id:
            try:
                old = await interaction.channel.fetch_message(self._panel_message_id)
                await old.delete()
            except Exception:
                pass

        async with self._queue_lock:
            self.waiting_user = None
            self._waiting_user_id = None
            self.waiting_anonymous = False

        view = LovePanelView(self)
        self._panel_view = view
        self.bot.add_view(view)

        embed = build_panel_embed(None)
        await interaction.response.send_message(
            embed=embed,
            file=_panel_file(),
            view=view,
        )
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
        description="Test the love machine — the bot plays with you",
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
        self._schedule_sticky()

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
