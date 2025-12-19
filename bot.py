# bot.py
"""
Single-file professional rewrite of your Discord bot.
Features:
- Clean configuration block at top
- Improved logging and error handling
- All previous features preserved (auto-reactions, logs, delete, timestamp, help panel, invite panel, invite request cooldown)
- Slightly more robust media detection
- Type hints and clear helper functions
- Ready to copy/paste (requires: python-dotenv, discord.py installed)
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

# Keep-alive import (if you use Replit or similar). If not needed, you can remove.
try:
    from keep_alive import keep_alive  # type: ignore
except Exception:
    # keep_alive is optional — swallow if not present
    def keep_alive():
        return None

# -------------------------
# ========== CONFIG ========
# -------------------------
load_dotenv()

# Token
TOKEN: Optional[str] = os.getenv("TOKEN")

# Bot identity & presentation
BOT_NAME = "Bovary Bot"
FOOTER_TEXT = "Bovary Club Society"

# Auto-reactions
AUTO_REACTIONS: List[str] = ["❤️", "🔥", "💯", "💥", "🎀"]

# Channels where bot auto-reacts to media messages
CHANNEL_IDS: List[int] = [
    1384173879295213689,
    1384174586345816134,
    1424515140660760647,
    1424515636524220516,
    1384173136853078038,
    1425870476290428978,
    1424434022058033242,
    1384173137071177753,
    1424509207172087849,
    1424586421599076473,
    1425669117750284318
]

# Log channels
LOG_CHANNEL_ID: Optional[int] = 1441663299065217114         # join/leave/channel logs
MESSAGE_LOG_CHANNEL_ID: Optional[int] = 1432715549116207248 # message delete/edit logs
IGNORE_CHANNEL_ID: Optional[int] = 1384173137985540233      # ignored for message logs

# Invite system constants
INVITE_COOLDOWN_SECONDS = 5 * 60   # 5 minutes
STAFF_LOG_CHANNEL = 1444186478157500508
CREW_LEADER_ROLE_ID = 1384173136177791048
REQUIRED_INVITE_CHANNEL = 1444094610157600859

# Server timezone assumption for `/timestamp` parsing (Brazil - São Paulo = UTC-3)
SERVER_TZ = timezone(timedelta(hours=-3))

# Bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Command prefix for legacy on_message processing (slash commands are preferred)
COMMAND_PREFIX = "|"

# -------------------------
# ====== MESSAGES (EN) ====
# -------------------------
class MESSAGES:
    # Generic
    NO_PERMISSION = "🚫 You do not have permission to execute this command."
    GENERIC_ERROR = "❌ An error occurred while executing the command."
    INVALID_CHANNEL = "This command can only be used in the designated channel."
    COOLDOWN = "Please wait before performing this action again."

    # Actions
    ACTION_SUCCESS = "✅ Action completed successfully."
    MESSAGE_REMOVED = "✅ Message successfully removed."

    # Invite system
    INVITE_REQUEST_SENT = "📨 Invite request sent to staff."
    INVITE_COOLDOWN = "Please wait before requesting another invite."

    # Access
    ACCESS_RESTRICTED = "🚫 Access restricted."

# -------------------------
# ====== LOGGING SETUP =====
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("bovary_bot")

# -------------------------
# ====== BOT INSTANCE ======
# -------------------------
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
bot.remove_command("help")  # we'll use a slash help

# Keep cooldown map for invite requests
last_invite_request: Dict[int, datetime] = {}

# -------------------------
# ====== STATUS ROTATION ===
# -------------------------
STATUS_INTERVAL_SECONDS = 2 * 60 * 60  # 2 hours

STATUS_ROTATION = [
    discord.Game("at Bovary Club Society"),
    discord.Game("Private Crew Access"),

    discord.Game("Curated automotive art"),
    discord.Game("Design. Form. Identity."),
    discord.Game("Where cars become art"),
    discord.Game("Aesthetic over noise"),

    discord.Game("Capturing motion"),
    discord.Game("Frames of luxury"),
    discord.Game("Night shots & neon lines"),
    discord.Game("Composition in motion"),

    discord.Game("Neon tones & deep shadows"),
    discord.Game("Muted colors, loud presence"),
    discord.Game("Light, shadow, contrast"),
    discord.Game("Color tells the story"),
]

# -------------------------
# ====== HELPERS ===========
# -------------------------
def make_embed(title: str = "", description: str = "", color: Optional[discord.Color] = None) -> discord.Embed:
    """Create a well-formed embed with footer and timestamp."""
    if color is None:
        color = discord.Color.blurple()
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=FOOTER_TEXT)
    return embed

def safe_get_channel(
    bot_instance: commands.Bot,
    channel_id: Optional[int]
) -> Optional[discord.abc.Channel]:
    """Return channel object or None if not found or id is None."""
    if not channel_id:
        return None
    return bot_instance.get_channel(channel_id)

def is_media_in_message(message: discord.Message) -> bool:
    """Detect if a message contains image or video media."""
    for a in message.attachments:
        if a.content_type and a.content_type.startswith(("image/", "video/")):
            return True
        if a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm", ".mkv", ".gifv")):
            return True

    for e in message.embeds:
        if getattr(e, "type", None) in ("image", "video", "gifv"):
            return True
        if getattr(e, "image", None) and getattr(e.image, "url", None):
            return True
        if getattr(e, "thumbnail", None) and getattr(e.thumbnail, "url", None):
            return True

    return False
import itertools
from discord.ext import tasks

status_cycle = itertools.cycle(STATUS_ROTATION)

@tasks.loop(seconds=STATUS_INTERVAL_SECONDS)
async def rotate_status():
    await bot.change_presence(activity=next(status_cycle))

# -------------------------
# ====== SLASH COMMANDS ====
# -------------------------

@bot.tree.command(name="ping", description="Display bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = make_embed(
        title="🏓 Pong",
        description=f"Latency: `{latency}ms`",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="info", description="Display information about the bot, server, and user")
async def info(interaction: discord.Interaction):
    bot_user = interaction.client.user
    server = interaction.guild
    user = interaction.user

    embed = discord.Embed(
        title="ℹ️ Information",
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )

    if bot_user and bot_user.avatar:
        embed.set_thumbnail(url=bot_user.avatar.url)

    embed.add_field(
        name="🤖 Bot",
        value=(
            f"**Name:** {bot_user.name if bot_user else BOT_NAME}\n"
            f"**ID:** `{bot_user.id if bot_user else 'N/A'}`\n"
            f"**Latency:** `{round(bot.latency * 1000)}ms`"
        ),
        inline=False
    )

    if server:
        embed.add_field(
            name="🛡️ Server",
            value=(
                f"**Name:** {server.name}\n"
                f"**ID:** `{server.id}`\n"
                f"**Members:** `{server.member_count}`"
            ),
            inline=False
        )

    embed.add_field(
        name="👤 User",
        value=(
            f"**Name:** {user.display_name}\n"
            f"**ID:** `{user.id}`"
        ),
        inline=False
    )

    embed.set_footer(text=FOOTER_TEXT)
    await interaction.response.send_message(embed=embed)

# delete message by ID (anonymous)
@bot.tree.command(name="apagar", description="Delete a message by ID (anonymous)")
@app_commands.describe(canal="Channel where the message is located", mensagem_id="ID of the message to delete")
async def apagar(interaction: discord.Interaction, canal: discord.TextChannel, mensagem_id: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            MESSAGES.NO_PERMISSION,
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        mensagem = await canal.fetch_message(int(mensagem_id))
        await mensagem.delete()
        await interaction.followup.send(
            MESSAGES.MESSAGE_REMOVED,
            ephemeral=True
        )

        msg_log = safe_get_channel(bot, MESSAGE_LOG_CHANNEL_ID)
        if msg_log:
            embed = make_embed(
                title="🧹 Message deleted via command",
                description=(
                    f"Channel: {canal.mention}\n"
                    f"Message ID: `{mensagem_id}`"
                ),
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Action executed anonymously")
            await msg_log.send(embed=embed)

    except discord.NotFound:
        await interaction.followup.send(
            "⚠️ Message not found.",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "🚫 I do not have permission to delete messages in this channel.",
            ephemeral=True
        )
    except Exception as e:
        logger.exception("Error deleting message")
        await interaction.followup.send(
            f"❌ An error occurred: `{e}`",
            ephemeral=True
        )

@bot.tree.command(name="help", description="Internal control panel")
async def help_command(interaction: discord.Interaction):
    embed = make_embed(
        title="📘 Control Panel — " + BOT_NAME,
        description=(
            "Internal interface of the **Bovary Club Society**.\n"
            "A curated space for control, access, and identity.\n\n"
            "Select a category to continue."
        ),
        color=discord.Color.blue()
    )

    if interaction.client.user and interaction.client.user.avatar:
        embed.set_thumbnail(url=interaction.client.user.avatar.url)

    embed.set_footer(text="Bovary Club Society • Internal System")

    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view)

# ===========================
# ====== HELP PANEL VIEW =====
# ===========================
class HelpView(discord.ui.View):
    def __init__(self, *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Moderation 🧹", style=discord.ButtonStyle.red)
    async def mod_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_embed(
            title="🧹 Moderation",
            color=discord.Color.red()
        )
        embed.description = (
            "Restricted tools for environment control.\n"
            "Silent actions. Precise execution. Logged results."
        )

        embed.add_field(
            name="🧹 Actions",
            value="`/apagar <channel> <id>` — Anonymous message removal",
            inline=False
        )
  
        embed.set_footer(text="Bovary Club Society • Moderation Layer")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Utilities ⚙️", style=discord.ButtonStyle.green)
    async def util_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_embed(
            title="⚙️ Utilities",
            color=discord.Color.green()
        )
        embed.description = (
            "Essential internal utilities.\n"
            "Time, system status, and contextual information."
        )
        
        embed.add_field(
            name="🧠 System",
            value="`/ping` — System response verification",
            inline=False
        )

        embed.set_footer(text="Bovary Club Society • Utility Layer")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Back ⬅️", style=discord.ButtonStyle.grey)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_embed(
            title="📘 Control Panel — " + BOT_NAME,
            color=discord.Color.blue()
        )
        embed.description = (
            "Internal interface of the **Bovary Club Society**.\n"
            "A curated space for control, access, and identity.\n\n"
            "Select a category to continue."
        )
        embed.set_footer(text="Bovary Club Society • Internal System")
        await interaction.response.edit_message(embed=embed, view=self)

# ===========================
# ====== INVITE SYSTEM ======
# ===========================
class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Request Invite ✉️",
        style=discord.ButtonStyle.blurple,
        custom_id="invite_request_button"
    )
    async def request_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = datetime.now(timezone.utc)

        last = last_invite_request.get(user.id)
        if last:
            diff = (now - last).total_seconds()
            remaining = INVITE_COOLDOWN_SECONDS - diff
            if remaining > 0:
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                await interaction.response.send_message(
                    f"⏳ Please wait **{minutes}m {seconds}s** before requesting another invite.",
                    ephemeral=True
                )
                return

        last_invite_request[user.id] = now
        await interaction.response.send_message(
            MESSAGES.INVITE_REQUEST_SENT,
            ephemeral=True
        )

        channel = safe_get_channel(bot, STAFF_LOG_CHANNEL)
        guild = interaction.guild
        crew_leader_role = guild.get_role(CREW_LEADER_ROLE_ID) if guild else None

        if channel:
            embed = make_embed(
                title="📨 New Invite Request",
                color=discord.Color.blue()
            )
            embed.description = (
                f"👤 **User:** {user.mention}\n"
                f"⏰ **Time:** <t:{int(now.timestamp())}:R>"
            )
            await channel.send(
                content=f"{crew_leader_role.mention if crew_leader_role else ''} "
                        f"**{user.display_name}** has requested an invitation.",
                embed=embed
            )

@bot.tree.command(name="invitepanel", description="Send the official invite panel")
async def invitepanel(interaction: discord.Interaction):
    if interaction.channel_id != REQUIRED_INVITE_CHANNEL:
        await interaction.response.send_message(
            f"❌ Use this command only in <#{REQUIRED_INVITE_CHANNEL}>.",
            ephemeral=True
        )
        return

    embed = make_embed(
        title="🚗 Bovary Club – Invitation Request Panel",
        color=discord.Color.from_rgb(80, 120, 255)
    )
    embed.description = (
        "Click the button below to request an invitation.\n"
        "Your request will be automatically forwarded to the staff.\n\n"
        f"⏳ *Cooldown: {INVITE_COOLDOWN_SECONDS // 60} minutes*"
    )
    embed.set_image(
        url="https://cdn.discordapp.com/attachments/1427794118440124567/1444131435106664469/Ekipa-w-GTA-Online-1280x720.jpg"
    )

    if interaction.client.user and interaction.client.user.avatar:
        embed.set_thumbnail(url=interaction.client.user.avatar.url)
        embed.set_footer(text=FOOTER_TEXT, icon_url=interaction.client.user.avatar.url)

    await interaction.channel.send(embed=embed, view=InviteView())
    await interaction.response.send_message("✅ Panel sent.", ephemeral=True)

    temp_msg = await interaction.channel.send(
        f"📨 {interaction.user.mention} requested an invite!"
    )
    try:
        await temp_msg.delete(delay=300)
    except Exception:
        pass

# -------------------------
# ====== EVENTS ===========
# -------------------------
@bot.event
async def on_ready():
    if not rotate_status.is_running():
        rotate_status.start()

    try:
        bot.add_view(InviteView())
    except Exception:
        logger.warning("Could not add persistent InviteView on startup")

    try:
        synced = await bot.tree.sync()
        logger.info("✅ %s is online with %d slash commands!", bot.user, len(synced))
    except Exception as e:
        logger.exception("❌ Error syncing commands: %s", e)

@bot.event
async def on_member_join(member: discord.Member):
    channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if channel:
        await channel.send(
            f"🟢 **{member}** joined the server! (ID: `{member.id}`)"
        )

@bot.event
async def on_member_remove(member: discord.Member):
    channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if channel:
        await channel.send(
            f"🔴 **{member}** left the server. (ID: `{member.id}`)"
        )

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    log_channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(
            f"🆕 Channel created: **{channel.name}** "
            f"({channel.mention if hasattr(channel, 'mention') else channel.name})"
        )

@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    log_channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(
            f"🗑️ Channel deleted: **{channel.name}**"
        )

@bot.event
async def on_message_delete(message: discord.Message):
    try:
        if message.author and message.author.bot:
            return
        if message.channel and message.channel.id == IGNORE_CHANNEL_ID:
            return

        msg_log = safe_get_channel(bot, MESSAGE_LOG_CHANNEL_ID)
        if msg_log:
            content = message.content or "[no text]"
            embed = make_embed(
                title="🗑️ Message Deleted",
                color=discord.Color.red()
            )

            embed.add_field(
                name="Channel",
                value=message.channel.mention if message.channel else "Unknown",
                inline=True
            )

            author = message.author if message.author else "Unknown"
            embed.add_field(
                name="Author",
                value=str(author),
                inline=True
            )

            embed.add_field(
                name="Content",
                value=content,
                inline=False
            )

            if message.author and getattr(message.author, "avatar", None):
                embed.set_thumbnail(url=message.author.avatar.url)

            embed.set_footer(text=f"{FOOTER_TEXT} | Delete log")
            await msg_log.send(embed=embed)

    except Exception:
        logger.exception("Error in on_message_delete")

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    try:
        if before.author and before.author.bot:
            return
        if before.content == after.content:
            return
        if before.channel and before.channel.id == IGNORE_CHANNEL_ID:
            return

        msg_log = safe_get_channel(bot, MESSAGE_LOG_CHANNEL_ID)
        if msg_log:
            embed = make_embed(
                title="✏️ Message Edited",
                color=discord.Color.orange()
            )

            embed.add_field(
                name="Channel",
                value=before.channel.mention if before.channel else "Unknown",
                inline=True
            )
            embed.add_field(
                name="Author",
                value=str(before.author),
                inline=True
            )
            embed.add_field(
                name="Before",
                value=before.content or "[no text]",
                inline=False
            )
            embed.add_field(
                name="After",
                value=after.content or "[no text]",
                inline=False
            )

            if before.author and getattr(before.author, "avatar", None):
                embed.set_thumbnail(url=before.author.avatar.url)

            embed.set_footer(text=f"{FOOTER_TEXT} | Edit log")
            await msg_log.send(embed=embed)

    except Exception:
        logger.exception("Error in on_message_edit")

@bot.event
async def on_message(message: discord.Message):
    if message.author and message.author.bot:
        return

    try:
        if message.channel and message.channel.id in CHANNEL_IDS:
            if is_media_in_message(message):
                for emoji in AUTO_REACTIONS:
                    try:
                        await message.add_reaction(emoji)
                    except discord.HTTPException:
                        continue
    except Exception:
        logger.exception("Error processing on_message (auto reactions)")

    await bot.process_commands(message)

# -------------------------
# ====== ERRORS HANDLING ==
# -------------------------
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    logger.exception("Slash command error: %s", error)

    if isinstance(error, app_commands.MissingPermissions):
        message = MESSAGES.NO_PERMISSION
    else:
        message = MESSAGES.GENERIC_ERROR

    try:
        await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        try:
            await interaction.followup.send(message, ephemeral=True)
        except Exception:
            pass

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    logger.exception("Legacy command error: %s", error)

    if isinstance(error, commands.MissingPermissions):
        message = MESSAGES.NO_PERMISSION
    else:
        message = MESSAGES.GENERIC_ERROR

    try:
        await ctx.send(message)
    except Exception:
        pass

# -------------------------
# ====== STARTUP ==========
# -------------------------
if __name__ == "__main__":
    keep_alive()

    if not TOKEN:
        logger.critical("TOKEN not found. Configure it in your environment (.env).")
        print("❌ ERROR: TOKEN not found. Configure it in the environment (.env)")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.exception("Failed to start bot: %s", e)
