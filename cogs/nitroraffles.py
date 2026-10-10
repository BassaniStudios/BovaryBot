"""
Nitro Raffles — sticky panel (Love Professor style) where members pick a number.
Staff configures max numbers (up to 999), winning number, cooldown, prize name,
and optional custom image when posting.
When someone hits the winning number the panel button is disabled; the embed
stays as a sticky "sticker" at the bottom of the chat waiting for staff.

Sticky behaviour (same pattern as Love Professor):
- No native Discord pin
- After human activity (or result messages), wait STICKY_DELAY_SECONDS of quiet
- Then delete the old panel message and re-send it at the bottom of the channel
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.nitroraffles")
FILE = "nitroraffles.json"

# ── Defaults / limits ─────────────────────────────────────────────────────
DEFAULT_MAX_NUMBER = 200
DEFAULT_WINNING_NUMBER = 145
DEFAULT_COOLDOWN_HOURS = 12.0
DEFAULT_PRIZE_NAME = "Discord Nitro"
MIN_NUMBER = 1
HARD_MAX_NUMBERS = 999  # absolute ceiling for the number list size

# Delay before sticky panel is moved back to the bottom of the channel.
STICKY_DELAY_SECONDS = 90

# ── Assets ────────────────────────────────────────────────────────────────
MAIN_IMAGE = "https://ik.imagekit.io/BassaniStudios/321213211232112.jpg"
THUMB_IMAGE = "https://ik.imagekit.io/BassaniStudios/Emblema%20Neon%20Retr%C3%B4%20BOVARY%20Club.png"

NITRO_COLOR = discord.Color.from_rgb(245, 73, 148)
NITRO_WIN_COLOR = discord.Color.from_rgb(88, 101, 242)


def _resolve_image_url(panel: Optional[Dict] = None) -> str:
    """Return custom image URL from panel if valid, otherwise the default MAIN_IMAGE."""
    if panel:
        raw = (panel.get("image_url") or "").strip()
        if raw.startswith(("http://", "https://")):
            return raw
    return MAIN_IMAGE


def _prize_name(panel: Optional[Dict] = None) -> str:
    """Prize display name stored on the panel (falls back to Discord Nitro)."""
    if panel:
        name = (panel.get("prize_name") or "").strip()
        if name:
            return name
    return DEFAULT_PRIZE_NAME



def _now_ts() -> float:
    return time.time()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_cooldown(seconds: float) -> str:
    """Human-readable cooldown duration."""
    if seconds >= 3600:
        h = seconds / 3600
        if h == int(h):
            return f"{int(h)} hour{'s' if int(h) != 1 else ''}"
        return f"{h:.1f} hours"
    if seconds >= 60:
        m = int(seconds // 60)
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{int(seconds)} second{'s' if int(seconds) != 1 else ''}"


# ── Setup modal (staff configures raffle before posting) ──────────────────
class RaffleSetupModal(discord.ui.Modal, title="Nitro Raffles — Setup"):
    max_numbers = discord.ui.TextInput(
        label="How many numbers? (1 – 999)",
        placeholder="e.g. 200",
        default=str(DEFAULT_MAX_NUMBER),
        min_length=1,
        max_length=3,
        required=True,
        style=discord.TextStyle.short,
    )
    winning_number = discord.ui.TextInput(
        label="Winning number",
        placeholder="e.g. 145  (must be within 1 … max)",
        default=str(DEFAULT_WINNING_NUMBER),
        min_length=1,
        max_length=3,
        required=True,
        style=discord.TextStyle.short,
    )
    cooldown_hours = discord.ui.TextInput(
        label="Cooldown in hours (per person)",
        placeholder="e.g. 12   or  0.5 for 30 minutes",
        default=str(int(DEFAULT_COOLDOWN_HOURS)),
        min_length=1,
        max_length=6,
        required=True,
        style=discord.TextStyle.short,
    )
    prize_name = discord.ui.TextInput(
        label="Prize name (what is awarded)",
        placeholder="e.g. Discord Nitro · Nitro Classic 1m · Steam Gift",
        default=DEFAULT_PRIZE_NAME,
        min_length=1,
        max_length=80,
        required=True,
        style=discord.TextStyle.short,
    )
    image_url = discord.ui.TextInput(
        label="Image URL (leave empty = default)",
        placeholder="https://…  or leave blank for the default Nitro art",
        default="",
        min_length=0,
        max_length=300,
        required=False,
        style=discord.TextStyle.short,
    )

    def __init__(self, cog: "NitroRaffles", channel: discord.abc.Messageable, *, reset: bool):
        super().__init__()
        self.cog = cog
        self.channel = channel
        self.reset = reset

    async def on_submit(self, interaction: discord.Interaction):
        # ── Validate max numbers ──────────────────────────────────────────
        try:
            max_n = int((self.max_numbers.value or "").strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ **How many numbers** must be a whole number.",
                ephemeral=True,
            )
            return
        if max_n < 1 or max_n > HARD_MAX_NUMBERS:
            await interaction.response.send_message(
                f"❌ Number list size must be between **1** and **{HARD_MAX_NUMBERS}**.",
                ephemeral=True,
            )
            return

        # ── Validate winning number ───────────────────────────────────────
        try:
            win_n = int((self.winning_number.value or "").strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ **Winning number** must be a whole number.",
                ephemeral=True,
            )
            return
        if win_n < MIN_NUMBER or win_n > max_n:
            await interaction.response.send_message(
                f"❌ Winning number must be between **{MIN_NUMBER}** and **{max_n}**.",
                ephemeral=True,
            )
            return

        # ── Validate cooldown (hours) ─────────────────────────────────────
        try:
            hours = float((self.cooldown_hours.value or "").strip().replace(",", "."))
        except ValueError:
            await interaction.response.send_message(
                "❌ **Cooldown** must be a number (hours). Example: `12` or `0.5`.",
                ephemeral=True,
            )
            return
        if hours <= 0 or hours > 720:  # up to 30 days
            await interaction.response.send_message(
                "❌ Cooldown must be greater than **0** and at most **720** hours.",
                ephemeral=True,
            )
            return
        cooldown_seconds = hours * 3600

        # ── Prize name ────────────────────────────────────────────────────
        prize = (self.prize_name.value or "").strip() or DEFAULT_PRIZE_NAME
        if len(prize) > 80:
            await interaction.response.send_message(
                "❌ Prize name must be at most **80** characters.",
                ephemeral=True,
            )
            return

        # ── Optional custom image URL ─────────────────────────────────────
        img_raw = (self.image_url.value or "").strip()
        if img_raw and not img_raw.startswith(("http://", "https://")):
            await interaction.response.send_message(
                "❌ Image URL must start with `http://` or `https://` (or leave empty for default).",
                ephemeral=True,
            )
            return
        image_url = img_raw or None  # None → use MAIN_IMAGE default

        await interaction.response.defer(ephemeral=True)
        try:
            msg = await self.cog._post_panel(
                self.channel,
                reset=self.reset,
                max_number=max_n,
                winning_number=win_n,
                cooldown_seconds=cooldown_seconds,
                prize_name=prize,
                image_url=image_url,
            )
            img_note = "custom" if image_url else "default"
            await interaction.followup.send(
                f"✅ Raffles sticky panel posted in {self.channel.mention}.\n"
                f"• Prize: **{prize}**\n"
                f"• Numbers: **1 – {max_n}**\n"
                f"• Winning number: set (hidden from public)\n"
                f"• Cooldown: **{_fmt_cooldown(cooldown_seconds)}**\n"
                f"• Image: **{img_note}**\n"
                f"• Message ID: `{msg.id}`\n"
                f"_Panel auto-returns to the bottom after ~{STICKY_DELAY_SECONDS}s of quiet chat._",
                ephemeral=True,
            )
        except Exception as e:
            logger.exception("nitroraffles setup panel failed")
            await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)



# ── Player number modal ───────────────────────────────────────────────────
class NumberModal(discord.ui.Modal, title="Try your luck"):
    def __init__(self, cog: "NitroRaffles", channel_id: int, max_number: int):
        super().__init__()
        self.cog = cog
        self.channel_id = channel_id
        self.max_number = max_number
        self.number_input = discord.ui.TextInput(
            label=f"Pick a number (1 – {max_number})",
            placeholder=f"Enter a number between 1 and {max_number}",
            min_length=1,
            max_length=len(str(max_number)),
            required=True,
            style=discord.TextStyle.short,
        )
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = (self.number_input.value or "").strip()
        try:
            number = int(raw)
        except ValueError:
            await interaction.response.send_message(
                f"Please enter a valid whole number between 1 and {self.max_number}.",
                ephemeral=True,
            )
            return

        if number < MIN_NUMBER or number > self.max_number:
            await interaction.response.send_message(
                f"Number must be between **{MIN_NUMBER}** and **{self.max_number}**.",
                ephemeral=True,
            )
            return

        await self.cog.process_entry(interaction, self.channel_id, number)


# ── Persistent view ───────────────────────────────────────────────────────
class NitroRaffleView(discord.ui.View):
    """Persistent view — timeout=None so it survives restarts."""

    def __init__(self, cog: "NitroRaffles", channel_id: int, *, active: bool = True):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == "nitroraffle:try":
                item.disabled = not active

    @discord.ui.button(
        label="Try your luck",
        style=discord.ButtonStyle.primary,
        emoji="💎",
        custom_id="nitroraffle:try",
        row=0,
    )
    async def try_luck(self, interaction: discord.Interaction, button: discord.ui.Button):
        panel = self.cog._panel(self.channel_id)
        if not panel or not panel.get("active", True):
            await interaction.response.send_message(
                "This raffle is closed — someone already won!",
                ephemeral=True,
            )
            return

        remaining = self.cog._check_cooldown(interaction.user.id, panel)
        if remaining > 0:
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            time_str = f"{hours}h {mins}m" if hours else f"{mins}m"
            await interaction.response.send_message(
                f"⏳ You can try again in **{time_str}**.",
                ephemeral=True,
            )
            return

        max_n = int(panel.get("max_number", DEFAULT_MAX_NUMBER))
        await interaction.response.send_modal(
            NumberModal(self.cog, self.channel_id, max_n)
        )


# ── Cog ───────────────────────────────────────────────────────────────────
class NitroRaffles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(FILE, {"panels": {}, "cooldowns": {}})
        self._sticky_tasks: Dict[int, asyncio.Task] = {}
        self._sticky_locks: Dict[int, asyncio.Lock] = {}

    def cog_unload(self):
        for task in list(self._sticky_tasks.values()):
            if task is not None and not task.done():
                task.cancel()
        self._save()

    def _save(self):
        save_json(FILE, self.data)

    def _panel(self, channel_id: int) -> Optional[Dict]:
        return self.data.get("panels", {}).get(str(channel_id))

    def _get_lock(self, channel_id: int) -> asyncio.Lock:
        if channel_id not in self._sticky_locks:
            self._sticky_locks[channel_id] = asyncio.Lock()
        return self._sticky_locks[channel_id]

    def _check_cooldown(self, user_id: int, panel: Optional[Dict] = None) -> float:
        last = self.data.get("cooldowns", {}).get(str(user_id))
        if last is None:
            return 0.0
        cooldown_sec = float(
            (panel or {}).get("cooldown_seconds", DEFAULT_COOLDOWN_HOURS * 3600)
        )
        elapsed = _now_ts() - float(last)
        remaining = cooldown_sec - elapsed
        return max(0.0, remaining)

    def _set_cooldown(self, user_id: int):
        self.data.setdefault("cooldowns", {})[str(user_id)] = _now_ts()
        self._save()

    # ── Embed builders ────────────────────────────────────────────────────
    def _build_active_embed(self, panel: Optional[Dict] = None) -> discord.Embed:
        max_n = int((panel or {}).get("max_number", DEFAULT_MAX_NUMBER))
        cd_sec = float((panel or {}).get("cooldown_seconds", DEFAULT_COOLDOWN_HOURS * 3600))
        cd_text = _fmt_cooldown(cd_sec)
        prize = _prize_name(panel)
        embed = discord.Embed(
            title="NITRO RAFFLES",
            description=(
                f"Pick a number between **1** and **{max_n}**.\n"
                f"If you choose the lucky number, you win a **{prize}**!\n\n"
                f"One attempt every **{cd_text}**.\n"
                "Good luck — may the odds be in your favour. ✨"
            ),
            color=NITRO_COLOR,
            timestamp=_utc_now(),
        )
        embed.set_thumbnail(url=THUMB_IMAGE)
        embed.set_image(url=_resolve_image_url(panel))
        embed.set_footer(text="Bova's Bot · Nitro Raffles")
        return embed

    def _build_closed_embed(
        self,
        winner: discord.Member | discord.User,
        number: int,
        panel: Optional[Dict] = None,
    ) -> discord.Embed:
        prize = _prize_name(panel)
        embed = discord.Embed(
            title="NITRO RAFFLES — WINNER!",
            description=(
                f"🎉 **{winner.display_name}** picked the lucky number **{number}**!\n\n"
                f"Prize: **{prize}**\n"
                "This raffle is now closed.\n"
                "Staff will contact the winner shortly."
            ),
            color=NITRO_WIN_COLOR,
            timestamp=_utc_now(),
        )
        embed.set_thumbnail(url=winner.display_avatar.url)
        embed.set_image(url=_resolve_image_url(panel))
        embed.set_footer(text="Bova's Bot · Nitro Raffles · Closed")
        return embed

    def _build_win_announce_embed(
        self,
        winner: discord.Member | discord.User,
        number: int,
        panel: Optional[Dict] = None,
    ) -> discord.Embed:
        prize = _prize_name(panel)
        embed = discord.Embed(
            title="🎊 WINNER! 🎊",
            description=(
                f"✨💎 **CONGRATULATIONS {winner.mention}!** 💎✨\n\n"
                f"You picked the lucky number **`{number}`**!\n\n"
                f"🎁 You just won a **{prize}**!\n"
                "Staff will reach out to deliver your prize.\n\n"
                "🎉🔥🚀💎✨🎊"
            ),
            color=NITRO_WIN_COLOR,
            timestamp=_utc_now(),
        )
        embed.set_thumbnail(url=winner.display_avatar.url)
        embed.set_image(url=_resolve_image_url(panel))
        embed.set_footer(text="Bova's Bot · Nitro Raffles · Winner")
        return embed

    def _embed_for_panel(self, panel: Dict) -> discord.Embed:
        if panel.get("active", True):
            return self._build_active_embed(panel)
        winner_id = panel.get("winner_id")
        number = panel.get("winning_number", DEFAULT_WINNING_NUMBER)
        if winner_id:
            user = self.bot.get_user(winner_id)
            if user is None:
                prize = _prize_name(panel)
                embed = discord.Embed(
                    title="NITRO RAFFLES — WINNER!",
                    description=(
                        f"🎉 The lucky number **{number}** was found!\n\n"
                        f"Prize: **{prize}**\n"
                        "This raffle is now closed.\n"
                        "Staff will contact the winner shortly."
                    ),
                    color=NITRO_WIN_COLOR,
                    timestamp=_utc_now(),
                )
                embed.set_image(url=_resolve_image_url(panel))
                embed.set_footer(text="Bova's Bot · Nitro Raffles · Closed")
                return embed
            return self._build_closed_embed(user, number, panel)
        return self._build_active_embed(panel)


    # ── Sticky system ─────────────────────────────────────────────────────
    def _schedule_sticky(self, channel_id: int) -> None:
        old = self._sticky_tasks.get(channel_id)
        if old is not None and not old.done():
            old.cancel()
        self._sticky_tasks[channel_id] = asyncio.create_task(
            self._delayed_sticky(channel_id)
        )

    async def _delayed_sticky(self, channel_id: int) -> None:
        try:
            await asyncio.sleep(STICKY_DELAY_SECONDS)
            await self._do_sticky_repost(channel_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "NitroRaffles delayed sticky failed for channel %s", channel_id
            )

    async def _do_sticky_repost(self, channel_id: int) -> None:
        panel = self._panel(channel_id)
        if not panel or not panel.get("message_id"):
            return

        async with self._get_lock(channel_id):
            try:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        return

                if not isinstance(
                    channel,
                    (discord.TextChannel, discord.VoiceChannel, discord.Thread),
                ):
                    return

                try:
                    async for last in channel.history(limit=1):
                        if last.id == panel["message_id"]:
                            return
                        break
                except (discord.Forbidden, discord.HTTPException):
                    pass

                try:
                    old = await channel.fetch_message(panel["message_id"])
                    await old.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

                active = bool(panel.get("active", True))
                view = NitroRaffleView(self, channel_id, active=active)
                self.bot.add_view(view)

                embed = self._build_active_embed(panel)
                if not active and panel.get("winner_id"):
                    try:
                        winner = self.bot.get_user(panel["winner_id"])
                        if winner is None:
                            winner = await self.bot.fetch_user(panel["winner_id"])
                        embed = self._build_closed_embed(
                            winner, panel.get("winning_number", DEFAULT_WINNING_NUMBER)
                        )
                    except Exception:
                        embed = self._embed_for_panel(panel)
                else:
                    embed = self._embed_for_panel(panel)

                new_msg = await channel.send(embed=embed, view=view)
                panel["message_id"] = new_msg.id
                self._save()
                logger.debug(
                    "NitroRaffles sticky panel reposted in %s (msg %s)",
                    channel_id,
                    new_msg.id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("NitroRaffles sticky repost failed in %s", channel_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        panel = self._panel(message.channel.id)
        if not panel or not panel.get("message_id"):
            return
        self._schedule_sticky(message.channel.id)

    # ── Core entry logic ──────────────────────────────────────────────────
    async def process_entry(
        self, interaction: discord.Interaction, channel_id: int, number: int
    ):
        panel = self._panel(channel_id)
        if not panel or not panel.get("active", True):
            await interaction.response.send_message(
                "This raffle is already closed.",
                ephemeral=True,
            )
            return

        remaining = self._check_cooldown(interaction.user.id, panel)
        if remaining > 0:
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            time_str = f"{hours}h {mins}m" if hours else f"{mins}m"
            await interaction.response.send_message(
                f"⏳ You can try again in **{time_str}**.",
                ephemeral=True,
            )
            return

        max_n = int(panel.get("max_number", DEFAULT_MAX_NUMBER))
        if number < MIN_NUMBER or number > max_n:
            await interaction.response.send_message(
                f"Number must be between **{MIN_NUMBER}** and **{max_n}**.",
                ephemeral=True,
            )
            return

        self._set_cooldown(interaction.user.id)

        panel.setdefault("entries", {})[str(interaction.user.id)] = {
            "number": number,
            "at": _utc_now().isoformat(),
        }
        self._save()

        channel = interaction.channel
        user = interaction.user
        winning = int(panel.get("winning_number", DEFAULT_WINNING_NUMBER))
        cd_sec = float(panel.get("cooldown_seconds", DEFAULT_COOLDOWN_HOURS * 3600))
        cd_text = _fmt_cooldown(cd_sec)

        if number == winning:
            panel["active"] = False
            panel["winner_id"] = user.id
            panel["winner_number"] = number
            panel["won_at"] = _utc_now().isoformat()
            self._save()

            await interaction.response.send_message(
                "🎉 You hit the lucky number! Check the channel…",
                ephemeral=True,
            )

            win_embed = self._build_win_announce_embed(user, number, panel)
            await channel.send(content=f"🎊 {user.mention}", embed=win_embed)

            try:
                msg = await channel.fetch_message(panel["message_id"])
                closed_embed = self._build_closed_embed(user, number, panel)
                closed_view = NitroRaffleView(self, channel_id, active=False)
                await msg.edit(embed=closed_embed, view=closed_view)
            except Exception:
                logger.exception("Failed to update raffle panel after win")

            self._schedule_sticky(channel_id)

        else:
            await interaction.response.send_message(
                f"You picked **{number}**. Check the channel for the result.",
                ephemeral=True,
            )
            result_embed = discord.Embed(
                title="Not this time…",
                description=(
                    f"{user.mention} picked **`{number}`**.\n"
                    "Better luck next time! ✨\n"
                    f"_You can try again in {cd_text}._"
                ),
                color=discord.Color.from_rgb(120, 120, 140),
                timestamp=_utc_now(),
            )
            result_embed.set_thumbnail(url=user.display_avatar.url)
            result_embed.set_footer(text="Bova's Bot · Nitro Raffles")
            await channel.send(embed=result_embed)
            self._schedule_sticky(channel_id)

    async def _post_panel(
        self,
        channel: discord.abc.Messageable,
        *,
        reset: bool = False,
        max_number: int = DEFAULT_MAX_NUMBER,
        winning_number: int = DEFAULT_WINNING_NUMBER,
        cooldown_seconds: float = DEFAULT_COOLDOWN_HOURS * 3600,
        prize_name: str = DEFAULT_PRIZE_NAME,
        image_url: Optional[str] = None,
    ) -> discord.Message:
        channel_id = channel.id
        existing = self._panel(channel_id)

        old_task = self._sticky_tasks.get(channel_id)
        if old_task is not None and not old_task.done():
            old_task.cancel()

        if existing and existing.get("message_id"):
            try:
                old = await channel.fetch_message(existing["message_id"])
                await old.delete()
            except Exception:
                pass

        view = NitroRaffleView(self, channel_id, active=True)
        panel_cfg = {
            "max_number": max_number,
            "winning_number": winning_number,
            "cooldown_seconds": cooldown_seconds,
            "prize_name": prize_name or DEFAULT_PRIZE_NAME,
            "image_url": image_url or "",
        }
        embed = self._build_active_embed(panel_cfg)

        msg = await channel.send(embed=embed, view=view)

        self.data.setdefault("panels", {})[str(channel_id)] = {
            "message_id": msg.id,
            "guild_id": getattr(getattr(channel, "guild", None), "id", None),
            "active": True,
            "max_number": max_number,
            "winning_number": winning_number,
            "cooldown_seconds": cooldown_seconds,
            "prize_name": prize_name or DEFAULT_PRIZE_NAME,
            "image_url": image_url or "",
            "winner_id": None,
            "winner_number": None,
            "entries": {},
            "created_at": _utc_now().isoformat(),
        }
        self._save()
        self.bot.add_view(view, message_id=msg.id)
        return msg


    # ── Slash commands (all LOCKED via bot role_check) ────────────────────
    @app_commands.command(
        name="nitroraffles",
        description="[LOCKED] Configure & post the Nitro Raffles sticky panel in this channel",
    )
    async def nitroraffles(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            await interaction.response.send_message(
                "This command only works in text-capable channels.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            RaffleSetupModal(self, ch, reset=True)
        )

    @app_commands.command(
        name="nitroraffles_reset",
        description="[LOCKED] Reset the raffle (new setup modal — clears winner & entries)",
    )
    async def nitroraffles_reset(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            await interaction.response.send_message(
                "This command only works in text-capable channels.",
                ephemeral=True,
            )
            return
        # Pre-fill modal with existing config if any
        panel = self._panel(ch.id)
        modal = RaffleSetupModal(self, ch, reset=True)
        if panel:
            modal.max_numbers.default = str(
                panel.get("max_number", DEFAULT_MAX_NUMBER)
            )
            modal.winning_number.default = str(
                panel.get("winning_number", DEFAULT_WINNING_NUMBER)
            )
            cd_h = float(panel.get("cooldown_seconds", DEFAULT_COOLDOWN_HOURS * 3600)) / 3600
            modal.cooldown_hours.default = (
                str(int(cd_h)) if cd_h == int(cd_h) else f"{cd_h:.2f}".rstrip("0").rstrip(".")
            )
            modal.prize_name.default = str(
                panel.get("prize_name") or DEFAULT_PRIZE_NAME
            )
            modal.image_url.default = str(panel.get("image_url") or "")
        await interaction.response.send_modal(modal)


    @app_commands.command(
        name="nitroraffles_reset_cooldown",
        description="[LOCKED] Reset all player cooldowns so everyone can try again",
    )
    async def nitroraffles_reset_cooldown(self, interaction: discord.Interaction):
        count = len(self.data.get("cooldowns") or {})
        self.data["cooldowns"] = {}
        self._save()

        await interaction.response.send_message(
            f"✅ Cooldown reset for **{count}** player(s). Everyone can try again now.",
            ephemeral=True,
        )

        # Public notice in the channel
        embed = discord.Embed(
            title="⏰ Cooldown Reset",
            description=(
                "The **Nitro Raffles** cooldown has been reset by staff.\n"
                "Everyone can **Try your luck** again! 💎"
            ),
            color=NITRO_COLOR,
            timestamp=_utc_now(),
        )
        embed.set_footer(text="Bova's Bot · Nitro Raffles")
        try:
            await interaction.channel.send(embed=embed)
            if self._panel(interaction.channel_id):
                self._schedule_sticky(interaction.channel_id)
        except Exception:
            logger.exception("Failed to post cooldown reset notice")

    @app_commands.command(
        name="nitroraffles_result",
        description="[LOCKED] Show current raffle status for this channel",
    )
    async def nitroraffles_result(self, interaction: discord.Interaction):
        panel = self._panel(interaction.channel_id)
        if not panel:
            await interaction.response.send_message(
                "No Nitro Raffles panel found in this channel.",
                ephemeral=True,
            )
            return

        entries = panel.get("entries") or {}
        max_n = panel.get("max_number", DEFAULT_MAX_NUMBER)
        cd_sec = float(panel.get("cooldown_seconds", DEFAULT_COOLDOWN_HOURS * 3600))
        prize = _prize_name(panel)
        img = (panel.get("image_url") or "").strip() or "(default)"
        lines = [
            f"**Status:** {'🟢 Active' if panel.get('active', True) else '🔒 Closed'}",
            f"**Prize:** **{prize}**",
            f"**Number range:** `1 – {max_n}`",
            f"**Winning number:** `{panel.get('winning_number', DEFAULT_WINNING_NUMBER)}`",
            f"**Cooldown:** **{_fmt_cooldown(cd_sec)}**",
            f"**Image:** `{img}`",
            f"**Total attempts:** **{len(entries)}**",
            f"**Panel message:** `{panel.get('message_id')}`",
            f"**Sticky delay:** `{STICKY_DELAY_SECONDS}s`",
        ]

        if panel.get("winner_id"):
            lines.append(
                f"**Winner:** <@{panel['winner_id']}> (number `{panel.get('winner_number')}`)"
            )
            if panel.get("won_at"):
                lines.append(f"**Won at:** `{panel['won_at']}`")

        active_cds = len(self.data.get("cooldowns") or {})
        lines.append(f"**Players on cooldown:** **{active_cds}**")

        if entries:
            recent = sorted(
                entries.items(), key=lambda x: x[1].get("at", ""), reverse=True
            )[:10]
            entry_lines = [
                f"• <@{uid}> → `{info.get('number')}` ({info.get('at', '?')[:16]})"
                for uid, info in recent
            ]
            lines.append("\n**Recent attempts:**\n" + "\n".join(entry_lines))

        embed = discord.Embed(
            title="Nitro Raffles — Staff Result",
            description="\n".join(lines),
            color=NITRO_COLOR,
            timestamp=_utc_now(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="nitroraffles_test",
        description="[LOCKED] Test the win announcement embed (does not affect real raffle)",
    )
    async def nitroraffles_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        panel = self._panel(interaction.channel_id)
        win_n = int(
            (panel or {}).get("winning_number", DEFAULT_WINNING_NUMBER)
        )
        embed = self._build_win_announce_embed(interaction.user, win_n, panel)

        await interaction.channel.send(
            content=(
                f"🧪 **TEST** — sample win announcement (not a real win)\n"
                f"{interaction.user.mention}"
            ),
            embed=embed,
        )
        if panel:
            self._schedule_sticky(interaction.channel_id)
        await interaction.followup.send(
            "✅ Test win embed posted in channel.",
            ephemeral=True,
        )

    async def cog_load(self):
        for ch_id_str, panel in self.data.get("panels", {}).items():
            if not panel.get("message_id"):
                continue
            try:
                ch_id = int(ch_id_str)
                active = bool(panel.get("active", True))
                view = NitroRaffleView(self, ch_id, active=active)
                self.bot.add_view(view, message_id=panel["message_id"])
            except Exception:
                logger.exception(
                    "Failed to re-register raffle view for channel %s", ch_id_str
                )
        logger.info(
            "NitroRaffles persistent views registered (sticky delay=%ss)",
            STICKY_DELAY_SECONDS,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NitroRaffles(bot))
