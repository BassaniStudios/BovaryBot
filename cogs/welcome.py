"""
Optional voice greet (configurable through stored configuration, OFF by default).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json

logger = logging.getLogger("bovary_bot.welcome")
FILE = "welcome.json"


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Dict[str, Any] = load_json(FILE, {
            "voice_greet_enabled": False,
            "voice_log_channel_id": None,
            "voice_join_bot": False,
            # Only trigger for members with this role (🤖 Bovas Bot interaction)
            "voice_required_role_id": 1548171930962763917,
            "voice_message": "🔊 {user} joined **{channel}**",
        })

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return
        if not self.config.get("voice_greet_enabled"):
            return
        # Role gate: only specific role triggers bot voice behaviour
        role_id = self.config.get("voice_required_role_id")
        if role_id:
            if not any(r.id == int(role_id) for r in getattr(member, "roles", [])):
                return
        # Only when joining a channel (not moving mute etc.)
        if after.channel and (before.channel is None or before.channel.id != after.channel.id):
            ch_id = self.config.get("voice_log_channel_id")
            text_ch = safe_get_channel(self.bot, ch_id) if ch_id else None
            msg = self._render(
                self.config.get("voice_message") or "{user} joined {channel}",
                user=member.mention,
                channel=after.channel.name,
            )
            if text_ch and isinstance(text_ch, discord.TextChannel):
                try:
                    embed = discord.Embed(
                        description=msg,
                        color=discord.Color.from_rgb(0, 200, 255),
                        timestamp=datetime.now(timezone.utc),
                    )
                    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                    embed.set_footer(text="Bova's Bot · Voice")
                    await text_ch.send(embed=embed)
                except Exception:
                    logger.exception("Voice log message failed")

            if self.config.get("voice_join_bot"):
                # Optional: bot joins the same VC briefly — can be disruptive; default OFF
                try:
                    vc = after.channel
                    if isinstance(vc, discord.VoiceChannel):
                        if member.guild.voice_client:
                            await member.guild.voice_client.move_to(vc)
                        else:
                            await vc.connect(reconnect=False, timeout=10)
                except Exception:
                    logger.debug("Voice join bot failed", exc_info=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
