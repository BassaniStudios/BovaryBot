# bot.py
"""
Single-file professional rewrite of your Discord bot.
Features:
- Clean configuration block at top
- Improved logging and error handling
- All previous features preserved (auto-reactions, logs, apagar, timestamp, help panel, invite panel, invite request cooldown)
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
CREW_LEADER_ROLE_ID = 1444179094983020605
REQUIRED_INVITE_CHANNEL = 1444094610157600859

# Server timezone assumption for `/timestamp` parsing (Brazil - São Paulo = UTC-3)
# Adjust if needed; using fixed offset to avoid extra dependencies.
SERVER_TZ = timezone(timedelta(hours=-3))

# Bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Command prefix for legacy on_message processing (slash commands are preferred)
COMMAND_PREFIX = "|"

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
# ====== HELPERS ===========
# -------------------------
def make_embed(title: str = "", description: str = "", color: Optional[discord.Color] = None) -> discord.Embed:
    """Create a well-formed embed with footer and timestamp."""
    if color is None:
        color = discord.Color.blurple()
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=FOOTER_TEXT)
    return embed

def safe_get_channel(bot_instance: commands.Bot, channel_id: Optional[int]) -> Optional[discord.abc.GuildChannel]:
    """Return channel object or None if not found or id is None."""
    if not channel_id:
        return None
    return bot_instance.get_channel(channel_id)

def is_media_in_message(message: discord.Message) -> bool:
    """
    Heuristic to decide if a message counts as 'media' (images/videos).
    Checks:
     - attachments with content_type starting with image/video
     - attachments whose filename ends with common extensions
     - embeds with image/video or thumbnails
    """
    # attachments
    for a in message.attachments:
        # content_type may be None on some hosting; fallback to filename
        if a.content_type and a.content_type.startswith(("image/", "video/")):
            return True
        lower = a.filename.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm", ".mkv", ".gifv")):
            return True

    # embeds
    for e in message.embeds:
        if getattr(e, "type", None) in ("image", "video", "gifv"):
            return True
        if getattr(e, "image", None) and getattr(e.image, "url", None):
            return True
        if getattr(e, "thumbnail", None) and getattr(e.thumbnail, "url", None):
            return True

    return False

def parse_date_time_strings(time_str: str, date_str: Optional[str]) -> datetime:
    """
    Parse user-provided date and time strings.
    - time_str: "HH:MM"
    - date_str: "DD/MM/YYYY" or None (use today's date)
    Returns an aware datetime in UTC.
    Assumes the provided date/time correspond to the server timezone (SERVER_TZ).
    Raises ValueError on invalid formats.
    """
    # time
    h, m = map(int, time_str.split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("Invalid hour/minute values")

    if date_str:
        d, mo, y = map(int, date_str.split("/"))
    else:
        now_local = datetime.now(SERVER_TZ)
        d, mo, y = now_local.day, now_local.month, now_local.year

    local_dt = datetime(year=y, month=mo, day=d, hour=h, minute=m, tzinfo=SERVER_TZ)
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt

# -------------------------
# ====== SLASH COMMANDS ====
# -------------------------

@bot.tree.command(name="timestamp", description="Gera um horário global (formato: HH:MM e opcional DD/MM/YYYY)")
@app_commands.describe(time="HH:MM (24h)", date="DD/MM/YYYY (opcional)")
async def timestamp(interaction: discord.Interaction, time: str, date: Optional[str] = None):
    """Generates a global timestamp for cross-timezone events."""
    try:
        utc_dt = parse_date_time_strings(time, date)
        ts = int(utc_dt.timestamp())
        embed = make_embed(
            title="🕒 Global Timestamp",
            description=(
                f"**Formato completo:** <t:{ts}:F>\n"
                f"**Relativo:** <t:{ts}:R>\n\n"
                f"Use em mensagens: `t:{ts}:F` ou `t:{ts}:R`"
            ),
            color=discord.Color.teal()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as exc:
        logger.debug("Timestamp parsing error: %s", exc)
        await interaction.response.send_message(
            "⚠️ Formato inválido! Use algo como `/timestamp time:19:30 date:14/10/2025` ou apenas `/timestamp time:19:30`.",
            ephemeral=True
        )

@bot.tree.command(name="ping", description="Mostra a latência do bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = make_embed(title="🏓 Pong!", description=f"Latência: `{latency}ms`", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="info", description="Mostra informações sobre o bot, servidor e usuário")
async def info(interaction: discord.Interaction):
    bot_user = interaction.client.user
    server = interaction.guild
    user = interaction.user

    embed = discord.Embed(
        title="ℹ️ Informações",
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )

    if bot_user and bot_user.avatar:
        embed.set_thumbnail(url=bot_user.avatar.url)

    embed.add_field(
        name="🤖 Bot",
        value=(
            f"**Nome:** {bot_user.name if bot_user else BOT_NAME}\n"
            f"**ID:** `{bot_user.id if bot_user else 'N/A'}`\n"
            f"**Latência:** `{round(bot.latency * 1000)}ms`"
        ),
        inline=False
    )

    if server:
        embed.add_field(
            name="🛡️ Servidor",
            value=(f"**Nome:** {server.name}\n**ID:** `{server.id}`\n**Membros:** `{server.member_count}`"),
            inline=False
        )

    embed.add_field(
        name="👤 Usuário",
        value=(f"**Nome:** {user.display_name}\n**ID:** `{user.id}`"),
        inline=False
    )

    embed.set_footer(text=FOOTER_TEXT)
    await interaction.response.send_message(embed=embed)

# apagar (delete message by ID) - requires manage_messages permission
@bot.tree.command(name="apagar", description="Apaga uma mensagem pelo ID (anônimo)")
@app_commands.describe(canal="Canal onde está a mensagem", mensagem_id="ID da mensagem que deseja apagar")
async def apagar(interaction: discord.Interaction, canal: discord.TextChannel, mensagem_id: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("🚫 Você não tem permissão para apagar mensagens.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        mensagem = await canal.fetch_message(int(mensagem_id))
        await mensagem.delete()
        await interaction.followup.send("✅ Mensagem apagada com sucesso!", ephemeral=True)

        msg_log = safe_get_channel(bot, MESSAGE_LOG_CHANNEL_ID)
        if msg_log:
            embed = make_embed(
                title="🧹 Mensagem apagada via comando",
                description=f"Canal: {canal.mention}\nID da mensagem: `{mensagem_id}`",
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Ação executada anonimamente")
            await msg_log.send(embed=embed)

    except discord.NotFound:
        await interaction.followup.send("⚠️ Mensagem não encontrada.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("🚫 Não tenho permissão para apagar mensagens nesse canal.", ephemeral=True)
    except Exception as e:
        logger.exception("Error deleting message")
        await interaction.followup.send(f"❌ Ocorreu um erro: `{e}`", ephemeral=True)

# ===========================
# ====== HELP PANEL VIEW =====
# ===========================
class HelpView(discord.ui.View):
    def __init__(self, *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Moderação 🧹", style=discord.ButtonStyle.red)
    async def mod_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_embed(title="🧹 Moderação", color=discord.Color.red())
        embed.description = "Comandos administrativos disponíveis no bot"
        embed.add_field(
            name="Comandos",
            value=(
                "`/apagar <canal> <id>` — Apaga mensagem anonimamente\n"
                "`/timestamp` — Cria horários globais"
            ),
            inline=False
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Utilidades ⚙️", style=discord.ButtonStyle.green)
    async def util_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_embed(title="⚙️ Utilidades", color=discord.Color.green())
        embed.description = "Comandos gerais e úteis do bot"
        embed.add_field(
            name="Comandos",
            value=(
                "`/ping` — Mostra a latência\n"
                "`/timestamp` — Horário global"
            ),
            inline=False
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Voltar ⬅️", style=discord.ButtonStyle.grey)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_embed(title="📘 Painel de Comandos", color=discord.Color.blue())
        embed.description = "Escolha uma categoria usando os botões abaixo:"
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="help", description="Mostra o painel de comandos do bot")
async def help_command(interaction: discord.Interaction):
    embed = make_embed(title="📘 Painel de Comandos — " + BOT_NAME, description="Escolha uma categoria usando os botões abaixo:", color=discord.Color.blue())
    if interaction.client.user and interaction.client.user.avatar:
        embed.set_thumbnail(url=interaction.client.user.avatar.url)
    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view)

# ===========================
# ====== INVITE SYSTEM ======
# ===========================
class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Invite ✉️", style=discord.ButtonStyle.blurple)
    async def request_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = datetime.now(timezone.utc)

        # cooldown check
        last = last_invite_request.get(user.id)
        if last:
            diff = (now - last).total_seconds()
            remaining = INVITE_COOLDOWN_SECONDS - diff
            if remaining > 0:
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                await interaction.response.send_message(
                    f"⏳ Você deve esperar **{minutes}m {seconds}s** antes de solicitar outro convite.",
                    ephemeral=True
                )
                return

        last_invite_request[user.id] = now
        await interaction.response.send_message("✅ Seu pedido de convite foi enviado para a equipe!", ephemeral=True)

        channel = safe_get_channel(bot, STAFF_LOG_CHANNEL)
        guild = interaction.guild
        crew_leader_role = guild.get_role(CREW_LEADER_ROLE_ID) if guild else None

        if channel:
            embed = make_embed(title="📨 New Invite Request", color=discord.Color.blue())
            embed.description = f"👤 **User:** {user.mention}\n⏰ **Time:** <t:{int(now.timestamp())}:R>"
            await channel.send(content=f"{crew_leader_role.mention if crew_leader_role else ''} **{user.display_name}** has requested an invitation.", embed=embed)

@bot.tree.command(name="invitepanel", description="Sends the official invite panel.")
async def invitepanel(interaction: discord.Interaction):
    if interaction.channel_id != REQUIRED_INVITE_CHANNEL:
        await interaction.response.send_message(f"❌ Use este comando apenas em <#{REQUIRED_INVITE_CHANNEL}>.", ephemeral=True)
        return

    embed = make_embed(title="🚗 Bovary Club – Invitation Request Panel", color=discord.Color.from_rgb(80, 120, 255))
    embed.description = (
        "Clique no botão abaixo para solicitar um convite.\nSeu pedido será encaminhado automaticamente para a equipe.\n\n"
        f"⏳ *Cooldown: {INVITE_COOLDOWN_SECONDS // 60} minutos*"
    )
    embed.set_image(url="https://cdn.discordapp.com/attachments/1427794118440124567/1444131435106664469/Ekipa-w-GTA-Online-1280x720.jpg")
    if interaction.client.user and interaction.client.user.avatar:
        embed.set_thumbnail(url=interaction.client.user.avatar.url)
        embed.set_footer(text=FOOTER_TEXT, icon_url=interaction.client.user.avatar.url)

    await interaction.channel.send(embed=embed, view=InviteView())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)

    temp_msg = await interaction.channel.send(f"📨 {interaction.user.mention} solicitou um convite!")
    # delete the temp message after a delay to avoid clutter (300s = 5min)
    try:
        await temp_msg.delete(delay=300)
    except Exception:
        # ignore if cannot delete
        pass

# -------------------------
# ====== EVENTS ===========
# -------------------------
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("at Bovary Club Society 🏎️"))
    try:
        bot.add_view(InviteView())  # register persistent view
    except Exception:
        logger.warning("Could not add persistent InviteView on startup (maybe already added)")

    try:
        synced = await bot.tree.sync()
        logger.info("✅ %s is online with %d slash commands!", bot.user, len(synced))
    except Exception as e:
        logger.exception("❌ Error syncing commands: %s", e)

@bot.event
async def on_member_join(member: discord.Member):
    channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🟢 **{member}** joined the server! (ID: `{member.id}`)")

@bot.event
async def on_member_remove(member: discord.Member):
    channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🔴 **{member}** left the server. (ID: `{member.id}`)")

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    log_channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🆕 Channel created: **{channel.name}** ({channel.mention if hasattr(channel, 'mention') else channel.name})")

@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    log_channel = safe_get_channel(bot, LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🗑️ Channel deleted: **{channel.name}**")

@bot.event
async def on_message_delete(message: discord.Message):
    # ignore bot messages and ignored channels
    try:
        if message.author and message.author.bot:
            return
        if message.channel and message.channel.id == IGNORE_CHANNEL_ID:
            return

        msg_log = safe_get_channel(bot, MESSAGE_LOG_CHANNEL_ID)
        if msg_log:
            content = message.content or "[no text]"
            embed = make_embed(title="🗑️ Message Deleted", color=discord.Color.red())
            embed.add_field(name="Channel", value=message.channel.mention if message.channel else "Unknown", inline=True)
            embed.add_field(name="Author", value=str(message.author), inline=True)
            embed.add_field(name="Content", value=content, inline=False)
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
            before_content = before.content or "[no text]"
            after_content = after.content or "[no text]"
            embed = make_embed(title="✏️ Message Edited", color=discord.Color.orange())
            embed.add_field(name="Channel", value=before.channel.mention if before.channel else "Unknown", inline=True)
            embed.add_field(name="Author", value=str(before.author), inline=True)
            embed.add_field(name="Before", value=before_content, inline=False)
            embed.add_field(name="After", value=after_content, inline=False)
            if before.author and getattr(before.author, "avatar", None):
                embed.set_thumbnail(url=before.author.avatar.url)
            embed.set_footer(text=f"{FOOTER_TEXT} | Edit log")
            await msg_log.send(embed=embed)
    except Exception:
        logger.exception("Error in on_message_edit")

@bot.event
async def on_message(message: discord.Message):
    # keep default behavior and ensure commands still work
    if message.author and message.author.bot:
        return

    try:
        if message.channel and message.channel.id in CHANNEL_IDS:
            if is_media_in_message(message):
                for emoji in AUTO_REACTIONS:
                    try:
                        await message.add_reaction(emoji)
                    except discord.HTTPException:
                        # skip failed reactions (e.g., invalid emoji, rate limit)
                        continue
    except Exception:
        logger.exception("Error processing on_message (auto reactions)")

    # ensure commands and app commands still process
    await bot.process_commands(message)

# -------------------------
# ====== ERRORS HANDLING ==
# -------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Generic slash command error handler
    logger.exception("Slash command error: %s", error)
    # Provide a compact user-friendly message
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("🚫 Você não tem permissão para executar este comando.", ephemeral=True)
    else:
        # for anything else, show a generic message
        try:
            await interaction.response.send_message("❌ Ocorreu um erro ao executar o comando.", ephemeral=True)
        except Exception:
            # If response already sent, do a followup
            try:
                await interaction.followup.send("❌ Ocorreu um erro ao executar o comando.", ephemeral=True)
            except Exception:
                pass

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    logger.exception("Legacy command error: %s", error)
    # avoid spamming users for known issues
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 Você não tem permissão para executar este comando.")
    else:
        await ctx.send("❌ Ocorreu um erro ao executar o comando.")

# -------------------------
# ====== STARTUP ==========
# -------------------------
if __name__ == "__main__":
    keep_alive()

    if not TOKEN:
        logger.critical("TOKEN not found. Configure it in your environment (.env).")
        print("❌ ERROR: TOKEN not found. Configure it in the environment (.env) as TOKEN=<your token>")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.exception("Failed to start bot: %s", e)
