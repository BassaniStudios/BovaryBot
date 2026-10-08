"""
Nitro Raffles — persistent pinned panel where members pick a number (1–200).
One winning number is fixed (145). 12-hour cooldown per user.
When someone hits the winning number the panel button is disabled and the
embed stays pinned waiting for staff.
"""
from __future__ import annotations

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

# ── Raffle rules ──────────────────────────────────────────────────────────
WINNING_NUMBER = 145
MIN_NUMBER = 1
MAX_NUMBER = 200
COOLDOWN_SECONDS = 12 * 60 * 60  # 12 hours

# ── Assets ────────────────────────────────────────────────────────────────
MAIN_IMAGE = "https://ik.imagekit.io/BassaniStudios/321213211232112.jpg"
THUMB_IMAGE = "https://ik.imagekit.io/BassaniStudios/Emblema%20Neon%20Retr%C3%B4%20BOVARY%20Club.png"

# Nitro-inspired purple / pink
NITRO_COLOR = discord.Color.from_rgb(245, 73, 148)  # pink-magenta
NITRO_WIN_COLOR = discord.Color.from_rgb(88, 101, 242)  # blurple


def _now_ts() -> float:
    return time.time()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Modal ─────────────────────────────────────────────────────────────────
class NumberModal(discord.ui.Modal, title="Try your luck"):
    number_input = discord.ui.TextInput(
        label="Pick a number (1 – 200)",
        placeholder="Enter a number between 1 and 200",
        min_length=1,
        max_length=3,
        required=True,
        style=discord.TextStyle.short,
    )

    def __init__(self, cog: "NitroRaffles", channel_id: int):
        super().__init__()
        self.cog = cog
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        raw = (self.number_input.value or "").strip()
        try:
            number = int(raw)
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid whole number between 1 and 200.",
                ephemeral=True,
            )
            return

        if number < MIN_NUMBER or number > MAX_NUMBER:
            await interaction.response.send_message(
                f"Number must be between **{MIN_NUMBER}** and **{MAX_NUMBER}**.",
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
        # Disable button when raffle already has a winner
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

        remaining = self.cog._check_cooldown(interaction.user.id)
        if remaining > 0:
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            if hours > 0:
                time_str = f"{hours}h {mins}m"
            else:
                time_str = f"{mins}m"
            await interaction.response.send_message(
                f"⏳ You can try again in **{time_str}**.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(NumberModal(self.cog, self.channel_id))


# ── Cog ───────────────────────────────────────────────────────────────────
class NitroRaffles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(FILE, {"panels": {}, "cooldowns": {}})

    def cog_unload(self):
        self._save()

    def _save(self):
        save_json(FILE, self.data)

    def _panel(self, channel_id: int) -> Optional[Dict]:
        return self.data.get("panels", {}).get(str(channel_id))

    def _check_cooldown(self, user_id: int) -> float:
        last = self.data.get("cooldowns", {}).get(str(user_id))
        if last is None:
            return 0.0
        elapsed = _now_ts() - float(last)
        remaining = COOLDOWN_SECONDS - elapsed
        return max(0.0, remaining)

    def _set_cooldown(self, user_id: int):
        self.data.setdefault("cooldowns", {})[str(user_id)] = _now_ts()
        self._save()

    # ── Embed builders ────────────────────────────────────────────────────
    def _build_active_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="NITRO RAFFLES",
            description=(
                "Pick a number between **1** and **200**.\n"
                "If you choose the lucky number, you win a **Discord Nitro**!\n\n"
                "One attempt every **12 hours**.\n"
                "Good luck — may the odds be in your favour. ✨"
            ),
            color=NITRO_COLOR,
            timestamp=_utc_now(),
        )
        embed.set_thumbnail(url=THUMB_IMAGE)
        embed.set_image(url=MAIN_IMAGE)
        embed.set_footer(text="Bova's Bot · Nitro Raffles")
        return embed

    def _build_closed_embed(self, winner: discord.Member | discord.User, number: int) -> discord.Embed:
        embed = discord.Embed(
            title="NITRO RAFFLES — WINNER!",
            description=(
                f"🎉 **{winner.display_name}** picked the lucky number **{number}**!\n\n"
                "This raffle is now closed.\n"
                "Staff will contact the winner shortly."
            ),
            color=NITRO_WIN_COLOR,
            timestamp=_utc_now(),
        )
        embed.set_thumbnail(url=winner.display_avatar.url)
        embed.set_image(url=MAIN_IMAGE)
        embed.set_footer(text="Bova's Bot · Nitro Raffles · Closed")
        return embed

    def _build_win_announce_embed(self, winner: discord.Member | discord.User, number: int) -> discord.Embed:
        embed = discord.Embed(
            title="🎊 NITRO WINNER! 🎊",
            description=(
                f"✨💎 **CONGRATULATIONS {winner.mention}!** 💎✨\n\n"
                f"You picked the lucky number **`{number}`**!\n\n"
                "🎁 You just won a **Discord Nitro**!\n"
                "Staff will reach out to deliver your prize.\n\n"
                "🎉🔥🚀💎✨🎊"
            ),
            color=NITRO_WIN_COLOR,
            timestamp=_utc_now(),
        )
        embed.set_thumbnail(url=winner.display_avatar.url)
        embed.set_image(url=MAIN_IMAGE)
        embed.set_footer(text="Bova's Bot · Nitro Raffles · Winner")
        return embed

    # ── Core logic ────────────────────────────────────────────────────────
    async def process_entry(self, interaction: discord.Interaction, channel_id: int, number: int):
        panel = self._panel(channel_id)
        if not panel or not panel.get("active", True):
            await interaction.response.send_message(
                "This raffle is already closed.",
                ephemeral=True,
            )
            return

        # Re-check cooldown (race safety)
        remaining = self._check_cooldown(interaction.user.id)
        if remaining > 0:
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            time_str = f"{hours}h {mins}m" if hours else f"{mins}m"
            await interaction.response.send_message(
                f"⏳ You can try again in **{time_str}**.",
                ephemeral=True,
            )
            return

        self._set_cooldown(interaction.user.id)

        # Record entry
        panel.setdefault("entries", {})[str(interaction.user.id)] = {
            "number": number,
            "at": _utc_now().isoformat(),
        }
        self._save()

        channel = interaction.channel
        user = interaction.user

        if number == WINNING_NUMBER:
            # ── WIN ──────────────────────────────────────────────────────
            panel["active"] = False
            panel["winner_id"] = user.id
            panel["winner_number"] = number
            panel["won_at"] = _utc_now().isoformat()
            self._save()

            await interaction.response.send_message(
                "🎉 You hit the lucky number! Check the channel…",
                ephemeral=True,
            )

            # Public win announcement
            win_embed = self._build_win_announce_embed(user, number)
            await channel.send(content=f"🎊 {user.mention}", embed=win_embed)

            # Update + disable the pinned panel
            try:
                msg = await channel.fetch_message(panel["message_id"])
                closed_embed = self._build_closed_embed(user, number)
                closed_view = NitroRaffleView(self, channel_id, active=False)
                await msg.edit(embed=closed_embed, view=closed_view)
            except Exception:
                logger.exception("Failed to update raffle panel after win")
        else:
            # ── MISS ─────────────────────────────────────────────────────
            await interaction.response.send_message(
                f"You picked **{number}**. Check the channel for the result.",
                ephemeral=True,
            )
            result_embed = discord.Embed(
                title="Not this time…",
                description=(
                    f"{user.mention} picked **`{number}`**.\n"
                    "Better luck next time! ✨\n"
                    f"_You can try again in 12 hours._"
                ),
                color=discord.Color.from_rgb(120, 120, 140),
                timestamp=_utc_now(),
            )
            result_embed.set_thumbnail(url=user.display_avatar.url)
            result_embed.set_footer(text="Bova's Bot · Nitro Raffles")
            await channel.send(embed=result_embed)

    async def _post_panel(self, channel: discord.abc.Messageable, *, reset: bool = False) -> discord.Message:
        channel_id = channel.id
        existing = self._panel(channel_id)

        # Remove old message if any
        if existing and existing.get("message_id"):
            try:
                old = await channel.fetch_message(existing["message_id"])
                await old.delete()
            except Exception:
                pass

        active = True
        if existing and not reset and not existing.get("active", True):
            # Keep closed state if not resetting
            active = False

        view = NitroRaffleView(self, channel_id, active=active)
        if active:
            embed = self._build_active_embed()
        else:
            winner_id = existing.get("winner_id") if existing else None
            winner = None
            if winner_id:
                winner = self.bot.get_user(winner_id) or await self.bot.fetch_user(winner_id)
            if winner:
                embed = self._build_closed_embed(winner, existing.get("winner_number", WINNING_NUMBER))
            else:
                embed = self._build_active_embed()
                active = True
                view = NitroRaffleView(self, channel_id, active=True)

        msg = await channel.send(embed=embed, view=view)

        # Pin
        try:
            await msg.pin(reason="Nitro Raffles panel")
        except Exception:
            logger.warning("Could not pin raffle panel in %s", channel_id)

        # Persist
        self.data.setdefault("panels", {})[str(channel_id)] = {
            "message_id": msg.id,
            "guild_id": getattr(channel, "guild", None) and channel.guild.id,
            "active": active,
            "winning_number": WINNING_NUMBER,
            "winner_id": None if active else (existing.get("winner_id") if existing else None),
            "winner_number": None if active else (existing.get("winner_number") if existing else None),
            "entries": {} if reset or active else (existing.get("entries") if existing else {}),
            "created_at": _utc_now().isoformat(),
        }
        if reset:
            self.data["panels"][str(channel_id)]["entries"] = {}
            self.data["panels"][str(channel_id)]["winner_id"] = None
            self.data["panels"][str(channel_id)]["winner_number"] = None
            self.data["panels"][str(channel_id)]["active"] = True

        self._save()
        self.bot.add_view(view, message_id=msg.id)
        return msg

    # ── Slash commands (all LOCKED via bot role_check) ────────────────────
    @app_commands.command(
        name="nitroraffles",
        description="[LOCKED] Post the Nitro Raffles panel in this channel (pinned)",
    )
    async def nitroraffles(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch = interaction.channel
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            await interaction.followup.send("This command only works in text-capable channels.", ephemeral=True)
            return
        try:
            msg = await self._post_panel(ch, reset=True)
            await interaction.followup.send(
                f"✅ Nitro Raffles panel posted and pinned in {ch.mention}.\nMessage ID: `{msg.id}`",
                ephemeral=True,
            )
        except Exception as e:
            logger.exception("nitroraffles panel failed")
            await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

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
        lines = [
            f"**Status:** {'🟢 Active' if panel.get('active', True) else '🔒 Closed'}",
            f"**Winning number:** `{panel.get('winning_number', WINNING_NUMBER)}`",
            f"**Total attempts:** **{len(entries)}**",
            f"**Panel message:** `{panel.get('message_id')}`",
        ]
        if panel.get("winner_id"):
            lines.append(f"**Winner:** <@{panel['winner_id']}> (number `{panel.get('winner_number')}`)")
            if panel.get("won_at"):
                lines.append(f"**Won at:** `{panel['won_at']}`")

        # Recent entries (last 10)
        if entries:
            recent = sorted(entries.items(), key=lambda x: x[1].get("at", ""), reverse=True)[:10]
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
        name="nitroraffles_reset",
        description="[LOCKED] Reset the raffle in this channel (new panel, clear winner & entries)",
    )
    async def nitroraffles_reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch = interaction.channel
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            await interaction.followup.send("This command only works in text-capable channels.", ephemeral=True)
            return
        try:
            msg = await self._post_panel(ch, reset=True)
            await interaction.followup.send(
                f"✅ Raffle reset. New panel pinned in {ch.mention}.\nMessage ID: `{msg.id}`",
                ephemeral=True,
            )
        except Exception as e:
            logger.exception("nitroraffles_reset failed")
            await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(
        name="nitroraffles_test",
        description="[LOCKED] Test the win announcement embed (does not affect real raffle)",
    )
    async def nitroraffles_test(self, interaction: discord.Interaction):
        """Posts a sample win embed as if the invoker won — for visual testing only."""
        await interaction.response.defer(ephemeral=True)
        embed = self._build_win_announce_embed(interaction.user, WINNING_NUMBER)
        await interaction.channel.send(
            content=f"🧪 **TEST** — sample win announcement (not a real win)\n{interaction.user.mention}",
            embed=embed,
        )
        await interaction.followup.send("✅ Test win embed posted in channel.", ephemeral=True)

    async def cog_load(self):
        """Re-register persistent views after restart."""
        for ch_id_str, panel in self.data.get("panels", {}).items():
            if not panel.get("message_id"):
                continue
            try:
                ch_id = int(ch_id_str)
                active = bool(panel.get("active", True))
                view = NitroRaffleView(self, ch_id, active=active)
                self.bot.add_view(view, message_id=panel["message_id"])
            except Exception:
                logger.exception("Failed to re-register raffle view for channel %s", ch_id_str)
        logger.info("NitroRaffles persistent views registered")


async def setup(bot: commands.Bot):
    await bot.add_cog(NitroRaffles(bot))
