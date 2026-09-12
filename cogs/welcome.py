"""
Welcome DM on join + optional voice greet (configurable, OFF by default).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.welcome")
FILE = "welcome.json"


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Dict[str, Any] = load_json(FILE, {
            "dm_enabled": True,
            "dm_title": "Welcome to Bovary Club Society",
            "dm_body": (
                "Hello {user},\n"
                "Welcome to **Bovary Club Society** 🚗✨\n"
                "More than a crew – a community where we bring together other friendly crews\n"
                "We're glad you're here.\n\n"
                "🌐 **Community website:** https://bovaryclub.github.io/Crew/\n"
                "Visit the website to explore crew, meetings and the **Bovary Now APP** "
                "(all app information is on the website).\n\n"
                "• Check meeting announcement channels on our server\n"
                "• Check of the APP to find out in real time if there is an active session\n"
                "• Check of the space to post your photos and videos\n\n"
                "— Bova Bot"
            ),
            "dm_image": "",
            "voice_greet_enabled": False,
            "voice_log_channel_id": None,
            "voice_join_bot": False,
            # Only trigger for members with this role (🤖 Bovas Bot interaction)
            "voice_required_role_id": 1548171930962763917,
            "voice_message": "🔊 {user} joined **{channel}**",
        })

    def _save(self):
        save_json(FILE, self.config)

    def _render(self, template: str, **kwargs) -> str:
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not self.config.get("dm_enabled"):
            return
        title = self.config.get("dm_title") or "Welcome"
        body = self._render(
            self.config.get("dm_body") or "Welcome {user}!",
            user=member.display_name,
            mention=member.mention,
            server=member.guild.name if member.guild else "the server",
        )
        embed = discord.Embed(
            title=f"✨ {title}",
            description=body,
            color=discord.Color.from_rgb(180, 80, 255),
            timestamp=datetime.now(timezone.utc),
        )
        if member.guild and member.guild.icon:
            embed.set_thumbnail(url=member.guild.icon.url)
        img = (self.config.get("dm_image") or "").strip()
        if img:
            embed.set_image(url=img)
        embed.set_footer(text="Bova's Bot · Bovary Club Society")
        try:
            await member.send(embed=embed)
        except discord.Forbidden:
            logger.info("Could not DM welcome to %s (DMs closed)", member.id)
        except Exception:
            logger.exception("Welcome DM failed")

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

    @app_commands.command(name="welcome_config", description="Configure welcome DM and voice greet")
    @app_commands.describe(
        dm_enabled="Send personalized DM when someone joins",
        dm_title="DM embed title",
        dm_body="DM body — use {user} {mention} {server}",
        dm_image="Optional image URL for the DM embed",
        voice_greet_enabled="Log when someone joins a voice channel",
        voice_log_channel="Text channel for voice join messages",
        voice_join_bot="Bot also joins the voice channel (can be noisy — default off)",
        voice_required_role="Only trigger for this role (default: Bovas Bot interaction)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_config(
        self,
        interaction: discord.Interaction,
        dm_enabled: Optional[bool] = None,
        dm_title: Optional[str] = None,
        dm_body: Optional[str] = None,
        dm_image: Optional[str] = None,
        voice_greet_enabled: Optional[bool] = None,
        voice_log_channel: Optional[discord.TextChannel] = None,
        voice_join_bot: Optional[bool] = None,
        voice_required_role: Optional[discord.Role] = None,
    ):
        if dm_enabled is not None:
            self.config["dm_enabled"] = dm_enabled
        if dm_title is not None:
            self.config["dm_title"] = dm_title[:200]
        if dm_body is not None:
            self.config["dm_body"] = dm_body[:1800]
        if dm_image is not None:
            self.config["dm_image"] = dm_image.strip()
        if voice_greet_enabled is not None:
            self.config["voice_greet_enabled"] = voice_greet_enabled
        if voice_log_channel is not None:
            self.config["voice_log_channel_id"] = voice_log_channel.id
        if voice_join_bot is not None:
            self.config["voice_join_bot"] = voice_join_bot
        if voice_required_role is not None:
            self.config["voice_required_role_id"] = voice_required_role.id
        self._save()
        rid = self.config.get("voice_required_role_id")
        await interaction.response.send_message(
            f"✅ Welcome config saved.\n"
            f"DM: `{self.config.get('dm_enabled')}` · "
            f"Voice log: `{self.config.get('voice_greet_enabled')}` · "
            f"Bot joins VC: `{self.config.get('voice_join_bot')}` · "
            f"Voice role: `{rid}`",
            ephemeral=True,
        )

    @app_commands.command(name="welcome_test", description="Send yourself a test welcome DM")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send("Guild only.", ephemeral=True)
            return
        try:
            await self.on_member_join(member)
            await interaction.followup.send("✅ Test DM sent (if your DMs are open).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
