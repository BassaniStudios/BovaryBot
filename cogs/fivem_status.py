"""FiveM server status — Fenrir Yakuza (glm78x).

Professional rich embeds with online/offline status, player count,
optional player list, server icon/banner and connect link.

Accessible by Lider + special staff roles (not in the locked blacklist).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("bovary_bot.fivem_status")

# ── Fixed Fenrir target ──────────────────────────────────────────────────────
FIVEM_CODE = "glm78x"
FIVEM_JOIN_URL = f"https://cfx.re/join/{FIVEM_CODE}"
FIVEM_API_URL = f"https://servers-frontend.fivem.net/api/servers/single/{FIVEM_CODE}"
FALLBACK_NAME = "Fenrir Yakuza"

# ── Cyber palette (matches utilities.py) ─────────────────────────────────────
CYBER_PURPLE = discord.Color.from_rgb(180, 80, 255)
CYBER_CYAN = discord.Color.from_rgb(0, 220, 255)
CYBER_GREEN = discord.Color.from_rgb(0, 255, 170)
CYBER_RED = discord.Color.from_rgb(255, 40, 80)
CYBER_ORANGE = discord.Color.from_rgb(255, 140, 40)

VISIBILITY_CHOICES = [
    app_commands.Choice(name="Only you", value="private"),
    app_commands.Choice(name="Post in channel", value="channel"),
]


def is_public(visibility: str) -> bool:
    return visibility == "channel"


def strip_fivem_colors(text: str) -> str:
    """Remove ^0-^9 and ~r~ style color codes from FiveM hostnames."""
    if not text:
        return ""
    cleaned = re.sub(r"\^[0-9]", "", text)
    cleaned = re.sub(r"~[a-zA-Z]~", "", cleaned)
    return cleaned.strip() or text.strip()


def progress_bar(current: int, maximum: int, length: int = 12) -> str:
    """Simple unicode progress bar for player slots."""
    if maximum <= 0:
        return "░" * length
    filled = min(length, max(0, round((current / maximum) * length)))
    return "█" * filled + "░" * (length - filled)


def cyber_embed(
    title: str,
    description: str = "",
    color: discord.Color = CYBER_PURPLE,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="BOVA CORE · Fenrir Status · SYSTEM ONLINE")
    return embed


class FiveMStatus(commands.Cog):
    """Live status of the Fenrir Yakuza FiveM server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=12),
            headers={
                "User-Agent": "BovaBot/2.11 (FiveM Status; +https://cfx.re)",
                "Accept": "application/json",
            },
        )

    async def cog_unload(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_server(self) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Returns (online, data_dict_or_None, error_message_or_None).
        online=True only when the CFX frontend returns a valid Data payload.
        """
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=12),
                headers={
                    "User-Agent": "BovaBot/2.11 (FiveM Status; +https://cfx.re)",
                    "Accept": "application/json",
                },
            )

        try:
            async with self._session.get(FIVEM_API_URL) as resp:
                if resp.status == 404:
                    return False, None, None  # clean offline / not listed
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("FiveM API HTTP %s: %s", resp.status, text[:200])
                    return False, None, f"API returned HTTP {resp.status}"

                payload = await resp.json(content_type=None)
                data = payload.get("Data") if isinstance(payload, dict) else None
                if not data or not isinstance(data, dict):
                    return False, None, "API response missing Data field"
                return True, data, None

        except aiohttp.ClientError as e:
            logger.warning("FiveM API network error: %s", e)
            return False, None, f"Network error: {type(e).__name__}"
        except Exception as e:
            logger.exception("Unexpected error fetching FiveM status")
            return False, None, f"Internal error: {type(e).__name__}"

    def _build_online_embed(
        self,
        data: Dict[str, Any],
        *,
        show_players: bool,
    ) -> discord.Embed:
        raw_name = data.get("hostname") or data.get("vars", {}).get("sv_projectName") or FALLBACK_NAME
        name = strip_fivem_colors(str(raw_name))

        clients = int(data.get("clients") or 0)
        max_clients = int(data.get("sv_maxclients") or 0) or 1
        players: List[Dict[str, Any]] = data.get("players") or []
        if not isinstance(players, list):
            players = []

        if players:
            clients = len(players)

        pct = min(100, round((clients / max_clients) * 100)) if max_clients else 0
        bar = progress_bar(clients, max_clients)

        vars_ = data.get("vars") or {}
        if not isinstance(vars_, dict):
            vars_ = {}

        project_desc = strip_fivem_colors(str(vars_.get("sv_projectDesc") or vars_.get("tags") or ""))
        gametype = strip_fivem_colors(str(data.get("gametype") or vars_.get("gametype") or "Roleplay"))
        mapname = strip_fivem_colors(str(data.get("mapname") or vars_.get("mapname") or ""))

        embed = cyber_embed(
            title=f"◈ {name}",
            description=(
                f"```ansi\n"
                f"\u001b[0;32m● ONLINE\u001b[0m  ·  {clients}/{max_clients} players  ·  {pct}%\n"
                f"{bar}\n"
                f"```"
            ),
            color=CYBER_GREEN,
        )

        icon_version = data.get("iconVersion") or data.get("iconVersion", 0)
        if icon_version:
            icon_url = f"https://servers-frontend.fivem.net/api/servers/icon/{FIVEM_CODE}/{icon_version}"
            embed.set_thumbnail(url=icon_url)

        banner = (
            vars_.get("banner_detail")
            or vars_.get("banner_connecting")
            or data.get("banner_detail")
            or data.get("banner_connecting")
        )
        if banner and isinstance(banner, str) and banner.startswith("http"):
            embed.set_image(url=banner)

        embed.add_field(name="▸ Status", value="🟢 **Online**", inline=True)
        embed.add_field(name="▸ Players", value=f"**{clients}** / **{max_clients}**", inline=True)
        embed.add_field(name="▸ Occupancy", value=f"**{pct}%**", inline=True)

        if gametype:
            embed.add_field(name="▸ Game Type", value=f"`{gametype}`", inline=True)
        if mapname:
            embed.add_field(name="▸ Map", value=f"`{mapname}`", inline=True)

        embed.add_field(
            name="▸ Connect",
            value=f"[`cfx.re/join/{FIVEM_CODE}`]({FIVEM_JOIN_URL})",
            inline=False,
        )

        if project_desc and len(project_desc) > 3:
            desc_short = project_desc[:280] + ("…" if len(project_desc) > 280 else "")
            embed.add_field(name="▸ Description", value=desc_short, inline=False)

        if show_players and players:
            names = []
            for p in sorted(players, key=lambda x: str(x.get("name", "")).lower()):
                pname = strip_fivem_colors(str(p.get("name") or "Unknown"))
                ping = p.get("ping")
                if ping is not None:
                    names.append(f"`{pname}` ({ping}ms)")
                else:
                    names.append(f"`{pname}`")

            max_shown = 40
            shown = names[:max_shown]
            remaining = len(names) - len(shown)

            chunks: List[str] = []
            current = ""
            for entry in shown:
                candidate = (current + "\n" + entry).strip() if current else entry
                if len(candidate) > 1000:
                    if current:
                        chunks.append(current)
                    current = entry
                else:
                    current = candidate
            if current:
                chunks.append(current)

            for i, chunk in enumerate(chunks[:3]):
                title = "▸ Online Players" if i == 0 else "▸ Online Players (cont.)"
                if i == 0 and remaining > 0:
                    title = f"▸ Online Players (+{remaining} hidden)"
                embed.add_field(name=title, value=chunk or "—", inline=False)

            if not chunks:
                embed.add_field(name="▸ Online Players", value="*No player names available*", inline=False)
        elif show_players and clients == 0:
            embed.add_field(name="▸ Online Players", value="*Server is empty*", inline=False)

        return embed

    def _build_offline_embed(self, error: Optional[str] = None) -> discord.Embed:
        embed = cyber_embed(
            title=f"◈ {FALLBACK_NAME}",
            description=(
                "```ansi\n"
                "\u001b[0;31m● OFFLINE / NOT LISTED\u001b[0m\n"
                "```\n"
                "The server is not responding on the public CFX list right now.\n"
                "It may be offline, under maintenance, or using a private listing."
            ),
            color=CYBER_RED,
        )
        embed.add_field(name="▸ Status", value="🔴 **Offline / Private**", inline=True)
        embed.add_field(name="▸ Players", value="**—** / **—**", inline=True)
        embed.add_field(
            name="▸ Connect",
            value=f"[`cfx.re/join/{FIVEM_CODE}`]({FIVEM_JOIN_URL})\n*(try anyway — direct join sometimes still works)*",
            inline=False,
        )
        if error:
            embed.add_field(name="▸ Diagnostics", value=f"`{error}`", inline=False)
        return embed

    # ── Slash command ────────────────────────────────────────────────────────

    @app_commands.command(
        name="fenrir",
        description="Live status of the Fenrir Yakuza FiveM server (players, online/offline, banner)",
    )
    @app_commands.describe(
        show_players="Show the list of online player names? (default: no)",
        visibility="How to display the result",
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    @app_commands.checks.cooldown(1, 15.0)
    async def fenrir(
        self,
        interaction: discord.Interaction,
        show_players: bool = False,
        visibility: str = "private",
    ):
        """Fetch Fenrir server status and post a rich embed."""
        await interaction.response.defer(ephemeral=not is_public(visibility), thinking=True)

        online, data, err = await self._fetch_server()

        if online and data:
            embed = self._build_online_embed(data, show_players=show_players)
        else:
            embed = self._build_offline_embed(error=err)

        await interaction.followup.send(embed=embed, ephemeral=not is_public(visibility))

    @fenrir.error
    async def fenrir_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Please wait **{error.retry_after:.0f}s** before checking again."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            logger.exception("Error in /fenrir command: %s", error)
            msg = "❌ Failed to fetch Fenrir status. Please try again in a moment."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(FiveMStatus(bot))
