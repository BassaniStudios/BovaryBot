"""
Server boost thank-you notifications.

Professional public announcement when a member boosts the server.
Config is stored via utils.storage (SQLite-backed).
All public-facing text is in English.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.boost")
CONFIG_FILE = "boost.json"

# Default channel: Boosts room on Bovary Club Society
DEFAULT_CHANNEL_ID = 1384173136638906407

# Soft neon pink used across Bovary branding
EMBED_COLOR = 0xF47FFF

# Public-facing thank-you copy. Clean, no config or internal logs.
THANK_YOU_TEMPLATE = (
    "🚀 **Server Boost Received!**\n\n"
    "Thank you {user} for boosting **{guild}**!\n\n"
    "Your support fuels neon nights, clean meets, and the whole community vibe. 💜✨\n"
    "Welcome to the boosters crew — we appreciate you. 🌟"
)


class Boost(commands.Cog):
    """Announce server boosts with a polished public embed."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_json(
            CONFIG_FILE,
            {
                "enabled": True,
                "channel_id": DEFAULT_CHANNEL_ID,
                "embed_color": EMBED_COLOR,
            },
        )

    # ── persistence ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        save_json(CONFIG_FILE, self.config)

    def _channel_id(self) -> Optional[int]:
        raw = self.config.get("channel_id")
        if raw is None:
            return DEFAULT_CHANNEL_ID
        try:
            return int(raw)
        except (TypeError, ValueError):
            return DEFAULT_CHANNEL_ID

    def _is_enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    # ── embed builder ────────────────────────────────────────────────────────

    def _build_embed(self, member: discord.Member) -> discord.Embed:
        """Create a clean public boost announcement embed.

        Avatar is placed on the right via thumbnail (Discord standard layout).
        No configuration text, no internal logs — presentation-ready.
        """
        guild_name = member.guild.name if member.guild else "the server"
        description = THANK_YOU_TEMPLATE.format(
            user=member.mention,
            guild=guild_name,
        )

        color = self.config.get("embed_color", EMBED_COLOR)
        try:
            color = int(color)
        except (TypeError, ValueError):
            color = EMBED_COLOR

        embed = discord.Embed(
            title="💜 Server Boost!",
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        # Right-side avatar
        avatar_url = member.display_avatar.url if member.display_avatar else None
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.set_author(
            name=str(member.display_name),
            icon_url=avatar_url,
        )

        footer_icon = None
        if self.bot.user and self.bot.user.display_avatar:
            footer_icon = self.bot.user.display_avatar.url

        embed.set_footer(
            text="Bova's Bot · Server Boost",
            icon_url=footer_icon,
        )
        return embed

    async def _send_thanks(self, member: discord.Member) -> bool:
        """Send the public boost announcement. Returns True on success."""
        if not self._is_enabled():
            logger.debug("Boost announcements disabled — skipping for %s", member.id)
            return False

        channel_id = self._channel_id()
        if not channel_id:
            logger.warning("No boost channel configured")
            return False

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning("Boost channel %s not found or inaccessible", channel_id)
                return False

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.warning("Boost channel %s is not a text channel", channel_id)
            return False

        embed = self._build_embed(member)
        try:
            # Mention outside the embed so the user is properly pinged
            await channel.send(content=member.mention, embed=embed)
            logger.info("Boost thank-you sent for %s in #%s", member, channel.name)
            return True
        except discord.Forbidden:
            logger.error("Missing permission to send in boost channel %s", channel_id)
        except Exception:
            logger.exception("Failed to send boost thank-you")
        return False

    # ── event listener ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Detect boost: premium_since goes from None → datetime
        if before.premium_since is None and after.premium_since is not None:
            await self._send_thanks(after)

    # ── slash commands (Manage Server required) ──────────────────────────────

    @app_commands.command(
        name="boost_channel",
        description="Set the channel where boost announcements are posted",
    )
    @app_commands.describe(channel="Text channel for boost notifications")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def boost_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        self.config["channel_id"] = channel.id
        self._save()
        await interaction.response.send_message(
            f"✅ Boost announcements will now post in {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="boost_enable",
        description="Enable automatic boost announcements",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def boost_enable(self, interaction: discord.Interaction):
        self.config["enabled"] = True
        self._save()
        await interaction.response.send_message(
            "✅ Boost announcements are now **enabled**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="boost_disable",
        description="Disable automatic boost announcements",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def boost_disable(self, interaction: discord.Interaction):
        self.config["enabled"] = False
        self._save()
        await interaction.response.send_message(
            "🛑 Boost announcements are now **disabled**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="boost_test",
        description="Send a test boost announcement (does not require a real boost)",
    )
    @app_commands.describe(
        member="Member to feature in the test (defaults to you)",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def boost_test(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ):
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Force-send for testing; restore previous enabled state afterward
        was_enabled = self._is_enabled()
        self.config["enabled"] = True
        ok = await self._send_thanks(target)
        self.config["enabled"] = was_enabled  # do not persist the temporary force

        if ok:
            ch_id = self._channel_id()
            await interaction.followup.send(
                f"✅ Test announcement sent for {target.mention} "
                f"(channel ID `{ch_id}`).",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "❌ Could not send the test announcement. "
                "Check that the boost channel exists and the bot can post there.",
                ephemeral=True,
            )

    @app_commands.command(
        name="boost_status",
        description="Show current boost announcement settings",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def boost_status(self, interaction: discord.Interaction):
        enabled = self._is_enabled()
        ch_id = self._channel_id()
        channel = self.bot.get_channel(ch_id) if ch_id else None
        ch_display = channel.mention if channel else f"`{ch_id}` (not found)"

        embed = discord.Embed(
            title="Boost Announcement Settings",
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Status",
            value="🟢 Enabled" if enabled else "🔴 Disabled",
            inline=True,
        )
        embed.add_field(name="Channel", value=ch_display, inline=True)
        embed.set_footer(text="Bova's Bot · Config")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Boost(bot))
