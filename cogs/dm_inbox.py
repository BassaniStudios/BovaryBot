"""Private DM inbox and staff replies.

Incoming user DMs are persisted in SQLite through the existing storage layer and
forwarded to a configured staff channel. Staff can inspect history and reply
through slash commands. Automatic replies are configurable and OFF by default.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.dm_inbox")
FILE = "dm_inbox.json"
MAX_PER_USER = 200


def _default() -> Dict[str, Any]:
    return {"conversations": {}, "auto_response_enabled": False, "auto_response_text": ""}


class DMInbox(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = load_json(FILE, _default())
        self.data.setdefault("conversations", {})
        self.data.setdefault("auto_response_enabled", bot.config.get("DM_AUTO_RESPONSE_ENABLED", False))
        self.data.setdefault("auto_response_text", bot.config.get("DM_AUTO_RESPONSE_TEXT", ""))
        save_json(FILE, self.data)

    def _is_staff(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages:
            return True
        role_id = self.bot.config.get("STAFF_API_ROLE_ID") or self.bot.config.get("PANEL_ACCESS_ROLE_ID")
        return bool(role_id and any(r.id == role_id for r in interaction.user.roles))

    def _inbox_channel(self):
        cid = self.bot.config.get("DM_INBOX_CHANNEL_ID") or self.bot.config.get("STAFF_LOG_CHANNEL")
        return self.bot.get_channel(cid) if cid else None

    def _conversation(self, user: discord.User) -> List[Dict[str, Any]]:
        return self.data.setdefault("conversations", {}).setdefault(str(user.id), [])

    async def _log_dm(self, message: discord.Message):
        channel = self._inbox_channel()
        if not channel:
            logger.warning("DM inbox channel is not configured or not cached")
            return
        embed = discord.Embed(
            title="📩 New DM received",
            description=message.content[:4000] if message.content else "_(no text)_",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="User", value=f"{message.author.mention} · `{message.author.id}`", inline=False)
        if message.attachments:
            urls = "\n".join(a.url for a in message.attachments[:5])
            embed.add_field(name="Attachments", value=urls[:1024], inline=False)
        embed.set_footer(text="Use /dm_history or /dm_reply to manage this conversation")
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("Failed to forward DM to staff inbox")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is not None:
            return

        convo = self._conversation(message.author)
        convo.append({
            "direction": "in",
            "content": message.content[:4000],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_id": message.id,
            "attachments": [a.url for a in message.attachments[:5]],
        })
        del convo[:-MAX_PER_USER]
        save_json(FILE, self.data)
        await self._log_dm(message)

        if self.data.get("auto_response_enabled"):
            text = (self.data.get("auto_response_text") or "").strip()
            if text:
                try:
                    await message.author.send(text[:2000])
                    convo.append({
                        "direction": "out",
                        "content": text[:2000],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "automatic": True,
                    })
                    del convo[:-MAX_PER_USER]
                    save_json(FILE, self.data)
                except discord.Forbidden:
                    logger.info("Could not auto-reply to DM user %s", message.author.id)
                except Exception:
                    logger.exception("Automatic DM reply failed")

    @app_commands.command(name="dm_inbox", description="[STAFF] Show recent users who contacted the bot by DM")
    async def dm_inbox(self, interaction: discord.Interaction):
        if not self._is_staff(interaction):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        conversations = self.data.get("conversations", {})
        if not conversations:
            await interaction.response.send_message("📭 No DM conversations recorded yet.", ephemeral=True)
            return
        rows = []
        for uid, msgs in list(conversations.items())[-20:][::-1]:
            if not msgs:
                continue
            last = msgs[-1]
            rows.append(f"• <@{uid}> · `{uid}` — {last.get('timestamp', '?')[:16].replace('T', ' ')}")
        embed = discord.Embed(title="📥 DM Inbox", description="\n".join(rows)[:4000] or "No conversations.", color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dm_history", description="[STAFF] View recent DM history with a user")
    @app_commands.describe(user="Discord user", limit="Number of messages to show (1-30)")
    async def dm_history(self, interaction: discord.Interaction, user: discord.User, limit: app_commands.Range[int, 1, 30] = 15):
        if not self._is_staff(interaction):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        msgs = self.data.get("conversations", {}).get(str(user.id), [])
        if not msgs:
            await interaction.response.send_message("📭 No DM history recorded for this user.", ephemeral=True)
            return
        lines = []
        for item in msgs[-limit:]:
            who = "USER" if item.get("direction") == "in" else "BOT"
            stamp = item.get("timestamp", "")[:16].replace("T", " ")
            content = item.get("content") or "_(attachment/no text)_"
            lines.append(f"**{who}** · `{stamp}`\n{content[:800]}")
        embed = discord.Embed(title=f"💬 DM history — {user}", description="\n\n".join(lines)[:6000], color=discord.Color.blurple())
        embed.set_footer(text=f"User ID: {user.id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dm_reply", description="[STAFF] Reply to a user by DM through the bot")
    @app_commands.describe(user="Discord user", message="Reply text")
    async def dm_reply(self, interaction: discord.Interaction, user: discord.User, message: str):
        if not self._is_staff(interaction):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        text = message.strip()[:2000]
        if not text:
            await interaction.response.send_message("❌ The reply cannot be empty.", ephemeral=True)
            return
        try:
            await user.send(text)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Discord rejected the DM. The user may have DMs disabled or blocked the bot.", ephemeral=True)
            return
        except Exception:
            logger.exception("Manual DM reply failed")
            await interaction.response.send_message("❌ Could not send the DM.", ephemeral=True)
            return
        convo = self._conversation(user)
        convo.append({"direction": "out", "content": text, "timestamp": datetime.now(timezone.utc).isoformat(), "automatic": False, "staff_id": interaction.user.id})
        del convo[:-MAX_PER_USER]
        save_json(FILE, self.data)
        await interaction.response.send_message(f"✅ Reply sent to **{user}**.", ephemeral=True)

    @app_commands.command(name="dm_auto_response", description="[STAFF] Configure automatic DM acknowledgement")
    @app_commands.describe(enabled="Enable or disable automatic replies", text="Automatic reply text")
    async def dm_auto_response(self, interaction: discord.Interaction, enabled: bool, text: str | None = None):
        if not self._is_staff(interaction):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        self.data["auto_response_enabled"] = enabled
        if text is not None:
            self.data["auto_response_text"] = text.strip()[:2000]
        save_json(FILE, self.data)
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"✅ Automatic DM response **{state}**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DMInbox(bot))
