"""
Bova's Bot — Official bot of Bovary Club Society.

Modular architecture with cogs.
Configuration via .env (see .env.example).
"""
from __future__ import annotations

import os
import logging
import itertools
from pathlib import Path

from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks

from utils.helpers import load_int_env, parse_channel_ids
from utils.cooldown import CooldownManager

# Keep-alive opcional (Replit etc.)
try:
    from keep_alive import keep_alive
except Exception:
    def keep_alive():
        return None

# -------------------------
# Configuração de logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bovary_bot")

# -------------------------
# Carrega .env
# -------------------------
load_dotenv()

TOKEN = os.getenv("TOKEN")

# -------------------------
# Intents
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True


class BovaryBot(commands.Bot):
    """Bot principal com configuração centralizada."""

    def __init__(self):
        super().__init__(
            command_prefix="|",  # Prefixo legado (quase não usado)
            intents=intents,
            help_command=None,
        )
        self.config = self._load_config()
        self.cooldown_manager = CooldownManager()

    def _load_config(self) -> dict:
        """Carrega todas as configurações a partir do .env."""
        cfg = {
            "GUILD_ID": load_int_env("GUILD_ID"),
            "LOG_CHANNEL_ID": load_int_env("LOG_CHANNEL_ID", 1441663299065217114),
            "MESSAGE_LOG_CHANNEL_ID": load_int_env("MESSAGE_LOG_CHANNEL_ID", 1432715549116207248),
            "IGNORE_CHANNEL_ID": load_int_env("IGNORE_CHANNEL_ID", 1384173137985540233),
            "STAFF_LOG_CHANNEL": load_int_env("STAFF_LOG_CHANNEL", 1444186478157500508),
            "CREW_LEADER_ROLE_ID": load_int_env("CREW_LEADER_ROLE_ID", 1384173136177791048),
            "REQUIRED_INVITE_CHANNEL": load_int_env("REQUIRED_INVITE_CHANNEL", 1444094610157600859),
            "CHANNEL_IDS": parse_channel_ids(
                os.getenv(
                    "CHANNEL_IDS",
                    "1384173879295213689,1384174586345816134,1424515140660760647,"
                    "1424515636524220516,1384173136853078038,1425870476290428978,"
                    "1424434022058033242,1384173137071177753,1424509207172087849,"
                    "1424586421599076473,1425669117750284318",
                )
            ),
            "INVITE_COOLDOWN_SECONDS": load_int_env("INVITE_COOLDOWN_SECONDS", 300) or 300,
            "AUTO_REACTIONS": ["❤️", "🔥", "💯", "💥", "🎀"],
            "PANEL_ACCESS_ROLE_ID": load_int_env("PANEL_ACCESS_ROLE_ID", 1542169549833773156),
            "PANEL_URL": os.getenv("PANEL_URL", "https://bovaryclub.github.io/BovaryBot-Panel/"),
        }
        return cfg

    async def setup_hook(self) -> None:
        """Carrega todos os cogs no startup."""
        cogs_dir = Path(__file__).parent / "cogs"
        for file in cogs_dir.glob("*.py"):
            if file.name.startswith("_"):
                continue
            ext = f"cogs.{file.stem}"
            try:
                await self.load_extension(ext)
                logger.info("Cog carregado: %s", ext)
            except Exception:
                logger.exception("Falha ao carregar cog %s", ext)

        # Restringe comandos a um guild específico (mais rápido para sync)
        guild_id = self.config.get("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Comandos sincronizados no guild %s (%d comandos)", guild_id, len(synced))
        else:
            synced = await self.tree.sync()
            logger.info("Comandos sincronizados globalmente (%d comandos)", len(synced))

    async def on_ready(self):
        if not rotate_status.is_running():
            rotate_status.start()
        logger.info("✅ %s está online!", self.user)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ):
        logger.exception("Erro em slash command: %s", error)

        if isinstance(error, discord.app_commands.MissingPermissions):
            message = "🚫 Você não tem permissão para executar este comando."
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            message = f"⏳ Aguarde {error.retry_after:.1f}s antes de usar este comando novamente."
        else:
            message = "❌ Ocorreu um erro ao executar o comando."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception:
            pass


# -------------------------
# Status rotativo
# -------------------------
STATUS_INTERVAL_SECONDS = 2 * 60 * 60  # 2 horas

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

status_cycle = itertools.cycle(STATUS_ROTATION)


@tasks.loop(seconds=STATUS_INTERVAL_SECONDS)
async def rotate_status():
    bot_instance = rotate_status.bot  # type: ignore
    if bot_instance and bot_instance.is_ready():
        await bot_instance.change_presence(activity=next(status_cycle))


# -------------------------
# Startup
# -------------------------
bot = BovaryBot()
rotate_status.bot = bot  # type: ignore


if __name__ == "__main__":
    keep_alive()

    if not TOKEN:
        logger.critical("TOKEN não encontrado. Configure no arquivo .env")
        print("❌ ERRO: TOKEN não encontrado. Configure no arquivo .env")
    else:
        try:
            bot.run(TOKEN, log_handler=None)  # usamos nosso próprio logging
        except Exception as e:
            logger.exception("Falha ao iniciar o bot: %s", e)
