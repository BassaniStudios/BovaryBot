"""Car meet announcement module with optional 30-min reminder."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.helpers import make_embed, SERVER_TZ
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.meets")
MEETS_FILE = "meets.json"


class Meets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.meets: List[Dict[str, Any]] = load_json(MEETS_FILE, [])
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    def _save(self):
        save_json(MEETS_FILE, self.meets)

    @tasks.loop(minutes=1)
    async def reminder_loop(self):
        now = datetime.now(timezone.utc)
        changed = False
        for meet in self.meets:
            if not meet.get("reminder_enabled") or meet.get("reminder_sent"):
                continue
            start = meet.get("start_unix")
            channel_id = meet.get("reminder_channel_id")
            if not start or not channel_id:
                continue
            # Fire when within 30-31 minutes before start
            delta = start - now.timestamp()
            if 29 * 60 <= delta <= 31 * 60:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        mention = ""
                        role_id = meet.get("mention_role_id")
                        if role_id:
                            mention = f"<@&{role_id}> "
                        await channel.send(
                            f"{mention}⏰ **The meeting starts in 30 minutes.**\n"
                            f"**{meet.get('title', 'Meet')}** — <t:{int(start)}:F>"
                        )
                        meet["reminder_sent"] = True
                        changed = True
                    except Exception:
                        logger.exception("Failed to send meet reminder")
        if changed:
            self._save()

    @reminder_loop.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="meet", description="Post a car meet announcement embed")
    @app_commands.describe(
        title="Meet title",
        description="Meet description",
        date_time="Date/time DD/MM/YYYY HH:MM (São Paulo time)",
        hosts="Host names or mentions",
        server="Server (Legacy / FiveM / other)",
        mention_role="Role to mention",
        image_url="Image URL for the embed",
        reminder_channel="Channel for the 30-min reminder (optional)",
        enable_reminder="Enable 30-minute reminder",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def meet(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        date_time: str,
        hosts: str,
        server: str,
        mention_role: Optional[discord.Role] = None,
        image_url: Optional[str] = None,
        reminder_channel: Optional[discord.TextChannel] = None,
        enable_reminder: bool = False,
    ):
        # Parse date
        dt = None
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(date_time.strip(), fmt).replace(tzinfo=SERVER_TZ)
                break
            except ValueError:
                continue
        if not dt:
            await interaction.response.send_message(
                "❌ Invalid date. Use `DD/MM/YYYY HH:MM` (São Paulo time).",
                ephemeral=True,
            )
            return

        unix = int(dt.timestamp())
        color = discord.Color.from_rgb(180, 80, 255)
        embed = discord.Embed(
            title=f"🚗 {title}",
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="📅 Date & Time",
            value=(
                f"<t:{unix}:F>\n"
                f"<t:{unix}:R>\n"
                f"`São Paulo` {dt.strftime('%d/%m/%Y %H:%M')}"
            ),
            inline=False,
        )
        embed.add_field(name="👤 Hosts", value=hosts, inline=True)
        embed.add_field(name="🖥️ Server", value=server, inline=True)
        if mention_role:
            embed.add_field(name="🔔 Role", value=mention_role.mention, inline=True)
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(text="Bova's Bot · Bovary Club Society")

        content = mention_role.mention if mention_role else None
        await interaction.response.send_message(content=content, embed=embed)
        msg = await interaction.original_response()

        meet_data = {
            "title": title,
            "description": description,
            "start_unix": unix,
            "hosts": hosts,
            "server": server,
            "mention_role_id": mention_role.id if mention_role else None,
            "image_url": image_url,
            "message_id": msg.id,
            "channel_id": interaction.channel_id,
            "reminder_enabled": bool(enable_reminder and reminder_channel),
            "reminder_channel_id": reminder_channel.id if reminder_channel else None,
            "reminder_sent": False,
        }
        self.meets.append(meet_data)
        # Keep last 50
        self.meets = self.meets[-50:]
        self._save()

        if enable_reminder and reminder_channel:
            await interaction.followup.send(
                f"✅ Reminder scheduled in {reminder_channel.mention} (30 min before).",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Meets(bot))
