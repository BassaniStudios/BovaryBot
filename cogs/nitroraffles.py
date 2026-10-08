"""
Nitro Raffles — sticky panel (Love Professor style) where members pick a number (1–200).
One winning number is fixed (145). 12-hour cooldown per user.
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

# ── Raffle rules ──────────────────────────────────────────────────────────
WINNING_NUMBER = 145
MIN_NUMBER = 1
MAX_NUMBER = 200
COOLDOWN_SECONDS = 12 * 60 * 60  # 12 hours

# Delay before sticky panel is moved back to the bottom of the channel.
# Gives people time to comment on results without the panel jumping constantly.
STICKY_DELAY_SECONDS = 90

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
            time_str = f"{hours}h {mins}m" if hours else f"{mins}m"
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
        # Per-channel sticky tasks & locks (Love Professor pattern, multi-channel)
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

    def _embed_for_panel(self, panel: Dict) -> discord.Embed:
        """Build the correct embed for the current panel state."""
        if panel.get("active", True):
            return self._build_active_embed()
        winner_id = panel.get("winner_id")
        number = panel.get("winner_number", WINNING_NUMBER)
        if winner_id:
            user = self.bot.get_user(winner_id)
            if user is None:
                # Fallback closed embed without avatar fetch (async not available here)
                embed = discord.Embed(
                    title="NITRO RAFFLES — WINNER!",
                    description=(
                        f"🎉 The lucky number **{number}** was found!\n\n"
                        "This raffle is now closed.\n"
                        "Staff will contact the winner shortly."
                    ),
                    color=NITRO_WIN_COLOR,
                    timestamp=_utc_now(),
                )
                embed.set_image(url=MAIN_IMAGE)
                embed.set_footer(text="Bova's Bot · Nitro Raffles · Closed")
                return embed
            return self._build_closed_embed(user, number)
        return self._build_active_embed()

    # ── Sticky system (Love Professor pattern) ────────────────────────────
    def _schedule_sticky(self, channel_id: int) -> None:
        """Cancel any pending sticky and schedule a new one after STICKY_DELAY_SECONDS."""
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
            logger.exception("NitroRaffles delayed sticky failed for channel %s", channel_id)

    async def _do_sticky_repost(self, channel_id: int) -> None:
        """Move the panel to the bottom of the channel if needed (no native pin)."""
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

                # If panel is already the last message, nothing to do
                try:
                    async for last in channel.history(limit=1):
                        if last.id == panel["message_id"]:
                            return
                        break
                except (discord.Forbidden, discord.HTTPException):
                    pass

                # Delete old panel
                try:
                    old = await channel.fetch_message(panel["message_id"])
                    await old.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

                active = bool(panel.get("active", True))
                view = NitroRaffleView(self, channel_id, active=active)
                self.bot.add_view(view)

                # Prefer full closed embed with winner avatar when possible
                embed = self._build_active_embed()
                if not active and panel.get("winner_id"):
                    try:
                        winner = self.bot.get_user(panel["winner_id"])
                        if winner is None:
                            winner = await self.bot.fetch_user(panel["winner_id"])
                        embed = self._build_closed_embed(
                            winner, panel.get("winner_number", WINNING_NUMBER)
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
        """Any human message in a raffle channel resets the quiet timer."""
        if message.author.bot:
            return
        if not message.guild:
            return
        panel = self._panel(message.channel.id)
        if not panel or not panel.get("message_id"):
            return
        self._schedule_sticky(message.channel.id)

    # ── Core entry logic ──────────────────────────────────────────────────
    async def process_entry(self, interaction: discord.Interaction, channel_id: int, number: int):
        panel = self._panel(channel_id)
        if not panel or not panel.get("active", True):
            await interaction.response.send_message(
                "This raffle is already closed.",
                ephemeral=True,
            )
            return

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

        panel.setdefault("entries", {})[str(interaction.user.id)] = {
            "number": number,
            "at": _utc_now().isoformat(),
        }
        self._save()

        channel = interaction.channel
        user = interaction.user

        if number == WINNING_NUMBER:
            panel["active"] = False
            panel["winner_id"] = user.id
            panel["winner_number"] = number
            panel["won_at"] = _utc_now().isoformat()
            self._save()

            await interaction.response.send_message(
                "🎉 You hit the lucky number! Check the channel…",
                ephemeral=True,
            )

            win_embed = self._build_win_announce_embed(user, number)
            await channel.send(content=f"🎊 {user.mention}", embed=win_embed)

            # Update current panel message in place (button disabled), then schedule sticky
            try:
                msg = await channel.fetch_message(panel["message_id"])
                closed_embed = self._build_closed_embed(user, number)
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
                    f"_You can try again in 12 hours._"
                ),
                color=discord.Color.from_rgb(120, 120, 140),
                timestamp=_utc_now(),
            )
            result_embed.set_thumbnail(url=user.display_avatar.url)
            result_embed.set_footer(text="Bova's Bot · Nitro Raffles")
            await channel.send(embed=result_embed)
            # After result is posted, wait for quiet then bring panel back to bottom
            self._schedule_sticky(channel_id)

    async def _post_panel(self, channel: discord.abc.Messageable, *, reset: bool = False) -> discord.Message:
        channel_id = channel.id
        existing = self._panel(channel_id)

        # Cancel pending sticky while we replace the panel
        old_task = self._sticky_tasks.get(channel_id)
        if old_task is not None and not old_task.done():
            old_task.cancel()

        # Delete old panel message if any
        if existing and existing.get("message_id"):
            try:
                old = await channel.fetch_message(existing["message_id"])
                await old.delete()
            except Exception:
                pass

        active = True
        if existing and not reset and not existing.get("active", True):
            active = False

        if reset:
            active = True

        view = NitroRaffleView(self, channel_id, active=active)
        if active:
            embed = self._build_active_embed()
        else:
            winner_id = existing.get("winner_id") if existing else None
            if winner_id:
                try:
                    winner = self.bot.get_user(winner_id) or await self.bot.fetch_user(winner_id)
                    embed = self._build_closed_embed(
                        winner, existing.get("winner_number", WINNING_NUMBER)
                    )
                except Exception:
                    embed = self._build_active_embed()
                    active = True
                    view = NitroRaffleView(self, channel_id, active=True)
            else:
                embed = self._build_active_embed()
                active = True
                view = NitroRaffleView(self, channel_id, active=True)

        msg = await channel.send(embed=embed, view=view)
        # NO native pin — sticky system keeps it at the bottom

        self.data.setdefault("panels", {})[str(channel_id)] = {
            "message_id": msg.id,
            "guild_id": getattr(getattr(channel, "guild", None), "id", None),
            "active": active,
            "winning_number": WINNING_NUMBER,
            "winner_id": None if active else (existing.get("winner_id") if existing else None),
            "winner_number": None if active else (existing.get("winner_number") if existing else None),
            "entries": {} if (reset or active) else (existing.get("entries") if existing else {}),
            "created_at": _utc_now().isoformat(),
        }
        if reset:
            p = self.data["panels"][str(channel_id)]
            p["entries"] = {}
            p["winner_id"] = None
            p["winner_number"] = None
            p["active"] = True
            p.pop("won_at", None)

        self._save()
        self.bot.add_view(view, message_id=msg.id)
        return msg

    # ── Slash commands (all LOCKED via bot role_check) ────────────────────
    @app_commands.command(
        name="nitroraffles",
        description="[LOCKED] Post the Nitro Raffles sticky panel in this channel",
    )
    async def nitroraffles(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch = interaction.channel
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            await interaction.followup.send(
                "This command only works in text-capable channels.",
                ephemeral=True,
            )
            return
        try:
            msg = await self._post_panel(ch, reset=True)
            await interaction.followup.send(
                f"✅ Nitro Raffles sticky panel posted in {ch.mention}.\n"
                f"Message ID: `{msg.id}`\n"
                f"_Panel auto-returns to the bottom after ~{STICKY_DELAY_SECONDS}s of quiet chat._",
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
            f"**Sticky delay:** `{STICKY_DELAY_SECONDS}s`",
        ]
        if panel.get("winner_id"):
            lines.append(
                f"**Winner:** <@{panel['winner_id']}> (number `{panel.get('winner_number')}`)"
            )
            if panel.get("won_at"):
                lines.append(f"**Won at:** `{panel['won_at']}`")

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
        name="nitroraffles_reset",
        description="[LOCKED] Reset the raffle in this channel (new sticky panel, clear winner & entries)",
    )
    async def nitroraffles_reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch = interaction.channel
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            await interaction.followup.send(
                "This command only works in text-capable channels.",
                ephemeral=True,
            )
            return
        try:
            msg = await self._post_panel(ch, reset=True)
            await interaction.followup.send(
                f"✅ Raffle reset. New sticky panel in {ch.mention}.\nMessage ID: `{msg.id}`",
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
        await interaction.response.defer(ephemeral=True)
        embed = self._build_win_announce_embed(interaction.user, WINNING_NUMBER)
        await interaction.channel.send(
            content=f"🧪 **TEST** — sample win announcement (not a real win)\n{interaction.user.mention}",
            embed=embed,
        )
        # Bring panel back after quiet
        if self._panel(interaction.channel_id):
            self._schedule_sticky(interaction.channel_id)
        await interaction.followup.send(
            "✅ Test win embed posted in channel.",
            ephemeral=True,
        )

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
                logger.exception(
                    "Failed to re-register raffle view for channel %s", ch_id_str
                )
        logger.info(
            "NitroRaffles persistent views registered (sticky delay=%ss)",
            STICKY_DELAY_SECONDS,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NitroRaffles(bot))
