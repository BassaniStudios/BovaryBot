
# =====================================
# BOVARY BOT — UNIFIED & BACKWARD-COMPATIBLE VERSION
# All original features preserved
# All missing features re-added
# Backward compatibility maintained
# =====================================

from __future__ import annotations

import os
import json
import copy
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

# -------------------------------------
# OPTIONAL KEEP ALIVE
# -------------------------------------
try:
    from keep_alive import keep_alive  # type: ignore
except Exception:
    def keep_alive():
        return None

# -------------------------------------
# ENV
# -------------------------------------
load_dotenv()
TOKEN: Optional[str] = os.getenv("TOKEN")

BOT_NAME = "Bovary Bot"
FOOTER_TEXT = "Bovary Club Society"
SERVER_TZ = timezone(timedelta(hours=-3))

# -------------------------------------
# CONSTANTS
# -------------------------------------
AUTO_REACTIONS = ["❤️", "🔥", "💯", "💥", "🎀"]
INVITE_COOLDOWN_SECONDS = 300

# -------------------------------------
# INTENTS
# -------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# -------------------------------------
# LOGGING
# -------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("bovary_bot")

# -------------------------------------
# BOT INIT
# -------------------------------------
bot = commands.Bot(command_prefix="|", intents=intents)
bot.remove_command("help")
bot.start_time = time.time()

last_invite_request: Dict[int, datetime] = {}

# =====================================
# CONFIG SYSTEM (PER GUILD)
# =====================================
CONFIG_FILE = Path("config.json")

DEFAULT_GUILD_CONFIG = {
    "log_channel": None,
    "message_log_channel": None,
    "staff_log_channel": None,
    "ignore_log_channel": None,
    "auto_reaction": True,
    "auto_reaction_channels": [],
    "modlog_enabled": True,
    "required_invite_channel": None,
    "crew_leader_role_id": None
}

def load_config() -> Dict[str, dict]:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({}, indent=4))
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError:
        CONFIG_FILE.write_text(json.dumps({}, indent=4))
        return {}

def save_config():
    CONFIG_FILE.write_text(json.dumps(config_data, indent=4))

config_data: Dict[str, dict] = load_config()

def get_guild_config(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in config_data:
        config_data[gid] = copy.deepcopy(DEFAULT_GUILD_CONFIG)
        save_config()
    return config_data[gid]

# =====================================
# HELPERS
# =====================================
def now() -> datetime:
    return datetime.now(tz=SERVER_TZ)

def make_embed(title: str = "", description: str = "", color: Optional[discord.Color] = None) -> discord.Embed:
    if color is None:
        color = discord.Color.blurple()
    embed = discord.Embed(title=title, description=description, color=color, timestamp=now())
    embed.set_footer(text=FOOTER_TEXT)
    return embed

def safe_channel(guild: discord.Guild, channel_id: Optional[int]):
    return guild.get_channel(channel_id) if channel_id else None

def is_media(message: discord.Message) -> bool:
    for a in message.attachments:
        if a.content_type and a.content_type.startswith(("image/", "video/")):
            return True
        if a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm", ".mkv")):
            return True
    for e in message.embeds:
        if getattr(e, "image", None) or getattr(e, "thumbnail", None):
            return True
    return False

# =====================================
# SLASH COMMANDS
# =====================================
@bot.tree.command(name="ping", description="Mostra a latência do bot")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=make_embed("🏓 Pong!", f"Latência: `{round(bot.latency*1000)}ms`")
    )

@bot.tree.command(name="info", description="Mostra informações sobre o bot")
async def info(interaction: discord.Interaction):
    guild = interaction.guild
    user = interaction.user
    embed = make_embed("ℹ️ Informações")
    embed.add_field(
        name="🤖 Bot",
        value=f"{BOT_NAME}\nLatency: {round(bot.latency*1000)}ms",
        inline=False
    )
    if guild:
        embed.add_field(
            name="🛡️ Servidor",
            value=f"{guild.name}\nMembros: {guild.member_count}",
            inline=False
        )
    embed.add_field(
        name="👤 Usuário",
        value=f"{user.display_name} ({user.id})",
        inline=False
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="timestamp", description="Gera um horário global")
@app_commands.describe(time="HH:MM", date="DD/MM/YYYY (opcional)")
async def timestamp(interaction: discord.Interaction, time: str, date: Optional[str] = None):
    try:
        h, m = map(int, time.split(":"))
        if date:
            d, mo, y = map(int, date.split("/"))
        else:
            n = now()
            d, mo, y = n.day, n.month, n.year
        local = datetime(y, mo, d, h, m, tzinfo=SERVER_TZ)
        ts = int(local.astimezone(timezone.utc).timestamp())
        await interaction.response.send_message(
            embed=make_embed("🕒 Timestamp", f"<t:{ts}:F>\n<t:{ts}:R>")
        )
    except Exception:
        await interaction.response.send_message("❌ Formato inválido.", ephemeral=True)

@bot.tree.command(name="apagar", description="Apaga mensagem por ID")
@app_commands.describe(canal="Canal", mensagem_id="ID da mensagem")
async def apagar(interaction: discord.Interaction, canal: discord.TextChannel, mensagem_id: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("🚫 Sem permissão.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        msg = await canal.fetch_message(int(mensagem_id))
        await msg.delete()
        await interaction.followup.send("✅ Mensagem apagada.", ephemeral=True)

        cfg = get_guild_config(interaction.guild.id)
        ch = safe_channel(interaction.guild, cfg["message_log_channel"])
        if ch:
            await ch.send(embed=make_embed(
                "🧹 Apagar via comando",
                f"Canal: {canal.mention}\nID: {mensagem_id}",
                discord.Color.orange()
            ))
    except Exception as e:
        await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)

# =====================================
# HELP PANEL
# =====================================
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Moderação", style=discord.ButtonStyle.red)
    async def mod(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=make_embed("🧹 Moderação", "`/apagar`\n`/invitepanel`"),
            view=self
        )

    @discord.ui.button(label="Utilidades", style=discord.ButtonStyle.green)
    async def util(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=make_embed("⚙️ Utilidades", "`/ping`\n`/timestamp`\n`/info`"),
            view=self
        )

@bot.tree.command(name="help", description="Painel de comandos")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=make_embed("📘 Painel de Comandos", "Use os botões abaixo"),
        view=HelpView()
    )

# =====================================
# INVITE PANEL (NEW + BACKWARD COMPAT)
# =====================================
class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📨 Request Invite", style=discord.ButtonStyle.primary)
    async def invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        now_t = now()

        last = last_invite_request.get(interaction.user.id)
        if last and (now_t - last).total_seconds() < INVITE_COOLDOWN_SECONDS:
            await interaction.response.send_message("⏳ Aguarde o cooldown.", ephemeral=True)
            return

        last_invite_request[interaction.user.id] = now_t
        await interaction.response.send_message("✅ Pedido enviado.", ephemeral=True)

        staff = safe_channel(interaction.guild, cfg["staff_log_channel"])
        role = interaction.guild.get_role(cfg["crew_leader_role_id"]) if cfg["crew_leader_role_id"] else None

        if staff:
            mention = role.mention if role else ""
            await staff.send(
                content=f"{mention} {interaction.user.mention} solicitou convite.",
                embed=make_embed("📨 Novo pedido de convite")
            )

# NEW COMMAND
@bot.tree.command(name="invite_panel", description="Enviar painel de convite")
@app_commands.checks.has_permissions(administrator=True)
async def invite_panel(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild.id)
    if cfg["required_invite_channel"] and interaction.channel.id != cfg["required_invite_channel"]:
        await interaction.response.send_message("❌ Canal incorreto para este comando.", ephemeral=True)
        return

    await interaction.channel.send(
        embed=make_embed("🎟️ Convites", "Clique abaixo para solicitar"),
        view=InviteView()
    )
    await interaction.response.send_message("✅ Painel enviado.", ephemeral=True)

# BACKWARD COMPATIBILITY COMMAND
@bot.tree.command(name="invitepanel", description="(Compatibilidade) Enviar painel de convite")
@app_commands.checks.has_permissions(administrator=True)
async def invitepanel(interaction: discord.Interaction):
    await invite_panel(interaction)

# =====================================
# EVENTS & LOGS
# =====================================
@bot.event
async def on_ready():
    bot.add_view(InviteView())
    await bot.change_presence(activity=discord.Game("at Bovary Club Society 🏎️"))
    await bot.tree.sync()
    logger.info("%s online como %s", BOT_NAME, bot.user)

@bot.event
async def on_member_join(member):
    cfg = get_guild_config(member.guild.id)
    ch = safe_channel(member.guild, cfg["log_channel"])
    if ch:
        await ch.send(embed=make_embed("🟢 Entrou", str(member)))

@bot.event
async def on_member_remove(member):
    cfg = get_guild_config(member.guild.id)
    ch = safe_channel(member.guild, cfg["log_channel"])
    if ch:
        await ch.send(embed=make_embed("🔴 Saiu", str(member)))

@bot.event
async def on_guild_channel_create(channel):
    cfg = get_guild_config(channel.guild.id)
    ch = safe_channel(channel.guild, cfg["log_channel"])
    if ch:
        await ch.send(embed=make_embed("🆕 Canal criado", channel.name))

@bot.event
async def on_guild_channel_delete(channel):
    cfg = get_guild_config(channel.guild.id)
    ch = safe_channel(channel.guild, cfg["log_channel"])
    if ch:
        await ch.send(embed=make_embed("🗑️ Canal removido", channel.name))

@bot.event
async def on_message_delete(message):
    if not message.guild or message.author.bot:
        return
    cfg = get_guild_config(message.guild.id)
    if message.channel.id == cfg["ignore_log_channel"]:
        return
    ch = safe_channel(message.guild, cfg["message_log_channel"])
    if ch:
        await ch.send(embed=make_embed(
            "🗑️ Mensagem apagada",
            f"{message.author}\n{message.content}",
            discord.Color.red()
        ))

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    cfg = get_guild_config(before.guild.id)
    if before.channel.id == cfg["ignore_log_channel"]:
        return
    ch = safe_channel(before.guild, cfg["message_log_channel"])
    if ch:
        await ch.send(embed=make_embed(
            "✏️ Mensagem editada",
            f"Antes: {before.content}\nDepois: {after.content}",
            discord.Color.orange()
        ))

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    cfg = get_guild_config(message.guild.id)
    if cfg["auto_reaction"] and message.channel.id in cfg["auto_reaction_channels"]:
        if is_media(message):
            for r in AUTO_REACTIONS:
                try:
                    await message.add_reaction(r)
                    await asyncio.sleep(0.2)
                except Exception:
                    break
    await bot.process_commands(message)

# =====================================
# SLASH ERROR HANDLER (RESTORED)
# =====================================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.exception("Slash command error: %s", error)
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("🚫 Sem permissão.", ephemeral=True)
    else:
        try:
            await interaction.response.send_message("❌ Erro ao executar comando.", ephemeral=True)
        except Exception:
            await interaction.followup.send("❌ Erro ao executar comando.", ephemeral=True)

# =====================================
# STARTUP
# =====================================
def main():
    if not TOKEN:
        raise RuntimeError("TOKEN não configurado")
    keep_alive()
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
