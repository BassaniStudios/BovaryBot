"""
Nazar Speaks — GTA Online arcade-style fortune-telling mini-game.
Persistent sticky panel, single-player fortunes, admin test mode (any channel).
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.nazarspeaks")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOGO_URL = "https://ik.imagekit.io/BassaniStudios/MadamNazar-GTAO-Livery.webp"
NAZAR_GIF_URL = "https://ik.imagekit.io/BassaniStudios/nazarspeakes-ezgif.com-video-to-gif-converter.gif"
ALLOWED_CHANNEL_ID = 1531417799300350073
COOLDOWN_SECONDS = 90
PANEL_STATE_FILE = "nazarspeaks_panel.json"

# Mystical dark theme
MYSTIC_PURPLE = discord.Color.from_rgb(48, 12, 64)
MYSTIC_RED = discord.Color.from_rgb(180, 20, 40)
MYSTIC_GOLD = discord.Color.from_rgb(200, 160, 60)
GLOW_RED = discord.Color.from_rgb(220, 30, 50)

# Pure Madam Nazar fortunes (no references / explanations)
FORTUNES = [
    "Your every move is watched! Avoid even the smallest misdemeanor!",
    "I see a three-legged man, and a long-legged woman. And they are happy!",
    "I see a lazy river. Flowing beside a scorched town.",
    "I see many people bowing down before a yellow statue of a.. No. No, that cannot be right!",
    "I hear a voice calling again and again, forlorn! A relative... He wants to... do something...",
    "Beware... not all love is kind. Just climb the mountain and ask my poor Jolene!",
    "I see cliffs in a silent desert.",
    "I see a man in a white shirt and a red vest. He is afraid to go to work.",
    "I see a... strange man in a tall hat. He frightens me.",
    "I smell lupins. So many lupins, they fill the valley floor...",
    "I see danger in your future. You must take care crossing the road...",
    "I see grizzled mountains and hungry eyes.",
    "I see a beautiful diamond, the largest in the world! It is cracked.",
    "I see a man with evil intentions. He comes to take what is yours.",
    "I hear birds, beautiful birds singing in a cage!",
    "At the stroke of twelve, when the moon is fat, the beast will awaken within you!",
    "I see great and furious judgment descending from the clouds to strike you down!",
    "Madam Nazar has a beautiful collection. And she is generous. Go, see what trophy she gives you.",
    "Remember, the stars favor those who leave no stone unturned.",
    "I see an emerald covered in filth, lying on a beautiful plain.",
    "I see a vengeful figure from your past, and a reward for your death...",
    "I see a web, still tangled after years of unraveling. Will you be the one, I wonder?",
    "I see bitterness, and ambition, and madness. They shall all come to this city...",
    "I see a face beneath the ice. Yet, not the face of a man, or a woman...",
    "I see many shadowy figures, sent to kill you...",
    "Have you seen... Gavin?",
    "I see numbers... one, two, three.",
    "I see numbers... seven, six, four.",
    "I see numbers. Five, one, one, two.",
    "Kifflom...",
    "I see mists and fog.",
    "I see thunder and lightning!",
    "I see a sky covered by clouds.",
    "I see... snow!",
    "I see the heavens opening, and the rain.",
    "I see a rooftop, and a briefcase, and death. No, no, no, no, no, it is not... not a rooftop...",
    "I see a man. His name is... Johnny. He sits at home, but he longs to be on the spot again.",
    "I see palm trees high in the sky, and shimmering pools of warm water, and people in, oh, oh dear...",
    "I see a man with red hair... And a red mark upon his face. He does not belong here.",
    "I see the ruins of a battle fought long ago.",
    "Take care! Your next drink will go to your head.",
    "I see a ridge in the land... and a falconer... and a black smoke rising to the east.",
    "Safe travels, Kifflom...",
    "I see many cars in a white room. No no no, they are all the same car. And I see great wealth! And great boredom. This is a strange vision.",
    "Nazar, teller of fortunes, finder of lost things...",
    "Good, I have been waiting for you.",
    "You were looking for me, yes?",
    "Ah yes, the mists clear...",
    "Come closer, let me see you.",
    "The future is open to me.",
    "I see Bovary again... You know the ones I mean. Yes, you. Don't pretend you don't.",
    "Bovary... such a strange name. I have seen it written many times, yet I have never seen it in my cards.",
    "I see Bovary gathering once more. You call it a meet... I call it a ritual. Perhaps you should be more careful with your invitations.",
    "I see the people of Bovary driving through Los Santos. They believe they are choosing the road... but someone else is choosing it for them.",
    "I see Bovary written across the screen. Strange... I wonder who is reading this.",
    "I see an old Bovary gathering. Some of you remember the beginning. Others were not there... yet somehow, the story remembers you.",
    "I see Bovary waiting for its next gathering. Do not ask me when it will happen. You already know the answer.",
    "I see the Bovary circle growing again. New faces, old names... and someone behind the screen who thinks I cannot see them.",
    "I see Bovary beneath the stars. Beautiful machines, familiar voices... and a watcher who has been here since the beginning.",
    "I see Bovary leaving Los Santos for a moment. No, do not follow them. This vision was not meant for you.",
    "I see the Bovary name appearing where it should not. On roads, in garages, in photographs... even in places you have not yet visited.",
    "I see Bovary preparing another gathering. You may call it an event... but the cards insist there is more to it.",
    "I see Bovary in my cards again. This is becoming quite repetitive... perhaps you should give me something new to predict.",
    "I see Bovary's story continuing. You thought the old days were finished? How amusing... the cards disagree.",
    "I see you looking for Bovary in the future. Do not worry... Bovary is looking for you too.",
]


# ---------------------------------------------------------------------------
# Helpers — mystical visual
# ---------------------------------------------------------------------------
def _arcade_frame(inner: str) -> str:
    return f"```\n{inner}\n```"


def build_anim_embed(user: discord.abc.User, step: int) -> discord.Embed:
    """Animation frames while Madam Nazar gazes into the future."""
    frames = [
        (
            "╔══════════════════════════════╗\n"
            "║      NAZAR SPEAKS            ║\n"
            "║   ░░ POWERING UP ░░          ║\n"
            "╠══════════════════════════════╣\n"
            "║     ○     ○                  ║\n"
            "║                              ║\n"
            "╚══════════════════════════════╝"
        ),
        (
            "╔══════════════════════════════╗\n"
            "║      NAZAR SPEAKS            ║\n"
            "║   ░░ EYES GLOWING ░░         ║\n"
            "╠══════════════════════════════╣\n"
            "║     ●     ●                  ║\n"
            "║         ⋯                    ║\n"
            "╚══════════════════════════════╝"
        ),
        (
            "╔══════════════════════════════╗\n"
            "║      NAZAR SPEAKS            ║\n"
            "║   ░░ GAZING... ░░            ║\n"
            "╠══════════════════════════════╣\n"
            "║     ◉     ◉                  ║\n"
            "║        ⋯⋯⋯                   ║\n"
            "╚══════════════════════════════╝"
        ),
        (
            "╔══════════════════════════════╗\n"
            "║      NAZAR SPEAKS            ║\n"
            "║   ░░ THE VEIL LIFTS ░░       ║\n"
            "╠══════════════════════════════╣\n"
            "║     ✦     ✦                  ║\n"
            "║       ⋯ ⋯ ⋯                  ║\n"
            "╚══════════════════════════════╝"
        ),
    ]
    machine = frames[min(step, len(frames) - 1)]
    embed = discord.Embed(
        title="🔮 NAZAR SPEAKS",
        description=(
            f"{_arcade_frame(machine)}\n"
            f"**{user.display_name}** approaches the machine...\n\n"
            f"*Madam Nazar is gazing into the future...*"
        ),
        color=MYSTIC_PURPLE,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="◆ ARCADE CABINET · NAZAR SPEAKS ◆")
    return embed


def build_fortune_embed(user: discord.abc.User, fortune: str) -> discord.Embed:
    machine = (
        "╔══════════════════════════════╗\n"
        "║      NAZAR SPEAKS            ║\n"
        "║   ◆ FORTUNE REVEALED ◆       ║\n"
        "╠══════════════════════════════╣\n"
        "║     ✦     ✦                  ║\n"
        "║                              ║\n"
        "╚══════════════════════════════╝"
    )
    embed = discord.Embed(
        title="🔮 MADAM NAZAR SPEAKS",
        description=(
            f"{_arcade_frame(machine)}\n"
            f"**{user.mention}** receives a vision...\n\n"
            f"> ### ❝ {fortune} ❞"
        ),
        color=GLOW_RED,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="◆ ARCADE CABINET · NAZAR SPEAKS · THE FUTURE IS OPEN ◆")
    return embed


def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔮 NAZAR SPEAKS",
        description=(
            "🟢 **READY** — The machine awaits\n\n"
            "Click **Consult Madam Nazar** to receive a fortune.\n\n"
            "**🔮 Consult Madam Nazar** — receive a vision of the future"
        ),
        color=MYSTIC_PURPLE,
    )
    embed.set_image(url=NAZAR_GIF_URL)
    embed.set_footer(text="◆ ARCADE · NAZAR SPEAKS · $1 PER FORTUNE (FREE HERE) ◆")
    return embed


# ---------------------------------------------------------------------------
# Animation + fortune runner
# ---------------------------------------------------------------------------
async def run_fortune(
    channel: discord.abc.Messageable,
    user: discord.abc.User,
    *,
    reply_to: Optional[discord.Message] = None,
) -> discord.Message:
    """Run mystical animation + final fortune. The fortune message never shows the panel GIF."""
    fortune = random.choice(FORTUNES)

    anim_embed = build_anim_embed(user, step=0)
    if reply_to is not None:
        msg = await reply_to.reply(embed=anim_embed, mention_author=False)
    else:
        msg = await channel.send(embed=anim_embed)

    for step in range(1, 4):
        await asyncio.sleep(0.55)
        try:
            await msg.edit(embed=build_anim_embed(user, step=step))
        except (discord.NotFound, discord.HTTPException):
            return msg

    await asyncio.sleep(0.65)
    try:
        await msg.edit(embed=build_fortune_embed(user, fortune))
    except (discord.NotFound, discord.HTTPException):
        pass
    return msg


# ---------------------------------------------------------------------------
# Main persistent panel view
# ---------------------------------------------------------------------------
class NazarPanelView(discord.ui.View):
    """Persistent panel — timeout=None so it survives restarts."""

    def __init__(self, cog: "NazarSpeaks"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Consult Madam Nazar",
        style=discord.ButtonStyle.primary,
        emoji="🔮",
        custom_id="nazarspeaks:consult",
        row=0,
    )
    async def consult(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ Nazar Speaks only works in the arcade channel.",
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
                f"⏳ The spirits need rest. Wait **{time_str}**.",
                ephemeral=True,
            )
            return

        self.cog._set_cooldown(user.id)
        await interaction.response.defer()

        # Move the sticky panel out of the way first. The consultation is then
        # posted immediately before the refreshed panel, keeping the panel last.
        fortune_msg = await self.cog._consult_from_panel(interaction.channel, user)

        # Keep the revealed fortune permanently. The refreshed sticky panel
        # is posted immediately after it, so the fortune remains the
        # penultimate message and the panel stays at the bottom of the channel.


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class NazarSpeaks(commands.Cog):
    """Nazar Speaks mini-game — sticky arcade panel + single-player fortunes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldowns: dict[int, float] = {}
        self._panel_view: Optional[NazarPanelView] = None
        self._panel_message_id: Optional[int] = None
        self._sticky_lock = False
        self._panel_operation_lock = asyncio.Lock()
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
        self._panel_view = NazarPanelView(self)
        self.bot.add_view(self._panel_view)
        logger.info("NazarSpeaks persistent panel view registered")

    async def _delete_current_panel(self, channel: discord.abc.Messageable) -> None:
        """Delete the currently stored sticky panel, if it still exists."""
        if not self._panel_message_id:
            return
        try:
            old = await channel.fetch_message(self._panel_message_id)
            await old.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        finally:
            self._panel_message_id = None
            self._save_panel_state()

    async def _post_panel(self, channel: discord.abc.Messageable) -> discord.Message:
        """Post a fresh persistent panel and store its message ID."""
        view = NazarPanelView(self)
        self._panel_view = view
        self.bot.add_view(view)
        msg = await channel.send(embed=build_panel_embed(), view=view)
        self._panel_message_id = msg.id
        self._save_panel_state()
        return msg

    async def _consult_from_panel(
        self, channel: discord.abc.Messageable, user: discord.abc.User
    ) -> discord.Message:
        """Show a fortune and restore the sticky panel directly underneath it.

        The fortune is intentionally kept in the channel; the panel is always
        reposted as the final message.
        """
        async with self._panel_operation_lock:
            await self._delete_current_panel(channel)
            fortune_msg = await run_fortune(channel, user)
            await self._post_panel(channel)
            return fortune_msg

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
            async with self._panel_operation_lock:
                channel = message.channel
                await self._delete_current_panel(channel)
                await self._post_panel(channel)
        except Exception:
            logger.exception("NazarSpeaks sticky repost failed")
        finally:
            self._sticky_lock = False

    # ------------------------------------------------------------------
    # Admin: post the fixed panel
    # ------------------------------------------------------------------
    @app_commands.command(
        name="nazarspeaks_panel",
        description="[ADMIN] Post the permanent Nazar Speaks arcade panel",
    )
    @app_commands.guild_only()
    async def nazarspeaks_panel(self, interaction: discord.Interaction):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ This panel can only be posted in the arcade channel.",
                ephemeral=True,
            )
            return

        if self._panel_message_id:
            try:
                old = await interaction.channel.fetch_message(self._panel_message_id)
                await old.delete()
            except Exception:
                pass

        view = NazarPanelView(self)
        self._panel_view = view
        self.bot.add_view(view)

        embed = build_panel_embed()
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        self._panel_message_id = msg.id
        self._save_panel_state()
        logger.info(
            "NazarSpeaks panel posted by %s in channel %s (msg %s)",
            interaction.user,
            interaction.channel_id,
            msg.id,
        )

    # ------------------------------------------------------------------
    # Admin: test mode — works in ANY channel (including hidden ones)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="nazarspeaks_test",
        description="[ADMIN] Test Nazar Speaks — works in any channel (including hidden)",
    )
    @app_commands.guild_only()
    async def nazarspeaks_test(self, interaction: discord.Interaction):
        await interaction.response.defer()
        human = interaction.user

        match_msg = await interaction.followup.send(
            f"🧪 **Test mode** — {human.mention} consults Madam Nazar...",
            wait=True,
        )
        await run_fortune(interaction.channel, human, reply_to=match_msg)

    @nazarspeaks_panel.error
    @nazarspeaks_test.error
    async def admin_cmd_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Você não possui um dos cargos autorizados para este comando.",
                ephemeral=True,
            )
        else:
            logger.exception("NazarSpeaks command error: %s", error)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Something went wrong.",
                    ephemeral=True,
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(NazarSpeaks(bot))
