"""Member join snapshots + nickname / username change history."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.namehistory")
FILE = "namehistory.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NameHistory(commands.Cog):
    """
    On join: store id, username, display name, avatar URL.
    On nick/username change: append history and log to bot-room.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(FILE, {"members": {}})

    def _save(self):
        save_json(FILE, self.data)

    def _bot_room(self) -> Optional[discord.abc.GuildChannel]:
        return safe_get_channel(self.bot, self.bot.config.get("BOT_ROOM_CHANNEL_ID"))

    def _ensure_member(self, member: discord.Member) -> Dict[str, Any]:
        key = str(member.id)
        members = self.data.setdefault("members", {})
        if key not in members:
            members[key] = {
                "user_id": member.id,
                "first_seen": _now_iso(),
                "username": str(member),
                "display_name": member.display_name,
                "avatar_url": str(member.display_avatar.url) if member.display_avatar else None,
                "names": [
                    {
                        "username": str(member),
                        "display_name": member.display_name,
                        "at": _now_iso(),
                        "reason": "first_seen",
                    }
                ],
            }
            self._save()
        return members[key]

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        entry = self._ensure_member(member)
        # Refresh snapshot
        entry["username"] = str(member)
        entry["display_name"] = member.display_name
        entry["avatar_url"] = str(member.display_avatar.url) if member.display_avatar else None
        entry["last_join"] = _now_iso()
        self._save()

        channel = self._bot_room()
        if channel:
            embed = make_embed(
                title="📥 Member registered",
                description=(
                    f"**User:** {member.mention}\n"
                    f"**ID:** `{member.id}`\n"
                    f"**Username:** `{member}`\n"
                    f"**Display name:** `{member.display_name}`"
                ),
                color=discord.Color.green(),
            )
            if member.display_avatar:
                embed.set_thumbnail(url=member.display_avatar.url)
            try:
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to log member register")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Track nick + global name changes relevant to server display
        before_name = before.display_name
        after_name = after.display_name
        before_user = str(before)
        after_user = str(after)

        if before_name == after_name and before_user == after_user:
            return

        entry = self._ensure_member(after)
        change = {
            "username": after_user,
            "display_name": after_name,
            "previous_username": before_user,
            "previous_display_name": before_name,
            "at": _now_iso(),
            "reason": "rename",
        }
        entry.setdefault("names", []).append(change)
        # Keep last 50 name entries per user
        entry["names"] = entry["names"][-50:]
        entry["username"] = after_user
        entry["display_name"] = after_name
        entry["avatar_url"] = str(after.display_avatar.url) if after.display_avatar else None
        self._save()

        channel = self._bot_room()
        if channel:
            lines = []
            if before_user != after_user:
                lines.append(f"**Username:** `{before_user}` → `{after_user}`")
            if before_name != after_name:
                lines.append(f"**Display name:** `{before_name}` → `{after_name}`")
            embed = make_embed(
                title="✏️ Name change",
                description=(
                    f"**User:** {after.mention} (`{after.id}`)\n"
                    + "\n".join(lines)
                ),
                color=discord.Color.gold(),
            )
            if after.display_avatar:
                embed.set_thumbnail(url=after.display_avatar.url)
            try:
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to log name change")

    @app_commands.command(name="namehistory", description="Show name history for a member")
    @app_commands.describe(member="Member to look up")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def namehistory_cmd(self, interaction: discord.Interaction, member: discord.Member):
        entry = self.data.get("members", {}).get(str(member.id))
        if not entry:
            await interaction.response.send_message(
                "No history stored for this member yet.", ephemeral=True
            )
            return
        names: List[dict] = entry.get("names") or []
        lines = []
        for n in names[-15:]:
            at = n.get("at", "")[:19].replace("T", " ")
            lines.append(
                f"`{at}` · `{n.get('previous_display_name', '—')}` → **{n.get('display_name')}**"
                if n.get("reason") == "rename"
                else f"`{at}` · first: **{n.get('display_name')}**"
            )
        embed = make_embed(
            title=f"Name history — {member.display_name}",
            description="\n".join(lines) or "Empty",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Entries", value=str(len(names)), inline=True)
        if entry.get("avatar_url"):
            embed.set_thumbnail(url=entry["avatar_url"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="namehistory_export", description="Export name history JSON (staff)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def namehistory_export(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        path = __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "namehistory.json"
        if not path.exists():
            await interaction.followup.send("No data file yet.", ephemeral=True)
            return
        await interaction.followup.send(
            file=discord.File(path, filename="namehistory.json"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NameHistory(bot))
