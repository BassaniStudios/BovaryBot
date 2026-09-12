"""
Bova's Bot — Official private bot of Bovary Club Society.
Version: 2.7.18
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bovary_bot")

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

# Profile auto-apply is OFF by default so Developer Portal banner/avatar stick.
# Set APPLY_BOT_PROFILE=true only if you want the bot to push ImageKit assets on boot.
APPLY_BOT_PROFILE = os.getenv("APPLY_BOT_PROFILE", "false").lower() in ("1", "true", "yes")
AVATAR_URL = os.getenv("BOT_AVATAR_URL", "")
BANNER_URL = os.getenv("BOT_BANNER_URL", "")


class BovaryBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="|",
            intents=intents,
            help_command=None,
        )
        self.config = self._load_config()
        self.cooldown_manager = CooldownManager()
        self._profile_applied = False

    def _load_config(self) -> dict:
        media_default = (
            "1384173879295213689,1384174586345816134,1424515140660760647,"
            "1424515636524220516,1384173136853078038,1425870476290428978,"
            "1424434022058033242,1384173137071177753,1424509207172087849,"
            "1424586421599076473,1425669117750284318,"
            "1384173137071177752,1425230894641451059,1542185824173424650,1425297078816473109"
        )
        cfg = {
            "GUILD_ID": load_int_env("GUILD_ID"),
            "LOG_CHANNEL_ID": load_int_env("LOG_CHANNEL_ID", 1441663299065217114),
            "MESSAGE_LOG_CHANNEL_ID": load_int_env("MESSAGE_LOG_CHANNEL_ID", 1432715549116207248),
            # General WebLogs channel (channel/admin events). Message edit/delete logs stay separate.
            "WEBLOGS_CHANNEL_ID": load_int_env("WEBLOGS_CHANNEL_ID", 1548153354675556412),
            "BOT_ROOM_CHANNEL_ID": load_int_env("BOT_ROOM_CHANNEL_ID", 1424436722984423529),
            # Auto backup of SQLite to a Discord channel (Render free mitigation)
            "BACKUP_CHANNEL_ID": load_int_env("BACKUP_CHANNEL_ID", 1548188378623778847),
            "BACKUP_INTERVAL_HOURS": load_int_env("BACKUP_INTERVAL_HOURS", 24) or 24,
            "IGNORE_CHANNEL_ID": load_int_env("IGNORE_CHANNEL_ID", 1384173137985540233),
            "STAFF_LOG_CHANNEL": load_int_env("STAFF_LOG_CHANNEL", 1444186478157500508),
            # DM inbox/support channel. Defaults to the existing staff log channel.
            "DM_INBOX_CHANNEL_ID": load_int_env("DM_INBOX_CHANNEL_ID", 1444186478157500508),
            "DM_AUTO_RESPONSE_ENABLED": os.getenv("DM_AUTO_RESPONSE_ENABLED", "false").lower() in ("1", "true", "yes"),
            # Automatic reminders for any <t:UNIX:R> timestamp found in guild messages/embeds.
            "TIMESTAMP_REMINDER_ENABLED": os.getenv("TIMESTAMP_REMINDER_ENABLED", "true").lower() in ("1", "true", "yes"),
            "TIMESTAMP_REMINDER_MINUTES": load_int_env("TIMESTAMP_REMINDER_MINUTES", 30) or 30,
            "TIMESTAMP_REMINDER_TEXT": os.getenv("TIMESTAMP_REMINDER_TEXT", ""),
            "DM_AUTO_RESPONSE_TEXT": os.getenv(
                "DM_AUTO_RESPONSE_TEXT",
                "Olá! Sua mensagem foi recebida. Nossa equipe foi notificada e responderá assim que possível.",
            ),
            "CREW_LEADER_ROLE_ID": load_int_env("CREW_LEADER_ROLE_ID", 1384173136177791048),
            "REQUIRED_INVITE_CHANNEL": load_int_env("REQUIRED_INVITE_CHANNEL", 1444094610157600859),
            "BOOST_CHANNEL_ID": load_int_env("BOOST_CHANNEL_ID", 1384173136638906407),
            "CHANNEL_IDS": parse_channel_ids(os.getenv("CHANNEL_IDS", media_default)),
            "MEDIA_SCORE_CHANNEL_IDS": parse_channel_ids(
                os.getenv("MEDIA_SCORE_CHANNEL_IDS", media_default)
            ),
            "INVITE_COOLDOWN_SECONDS": load_int_env("INVITE_COOLDOWN_SECONDS", 300) or 300,
            "AUTO_REACTIONS": ["❤️", "🔥", "💯", "💥", "🎀"],
            "PANEL_ACCESS_ROLE_ID": load_int_env("PANEL_ACCESS_ROLE_ID", 1542169549833773156),
            # Role allowed to call the HTTP API from the web panel
            "STAFF_API_ROLE_ID": load_int_env("STAFF_API_ROLE_ID", 1547647694997037137),
            "PANEL_URL": os.getenv("PANEL_URL", "https://bovaryclub.github.io/BovaryBot-Panel/"),
            # Panel secret is read only from the environment; never expose or default it in code.
            "PANEL_ACCESS_KEY": os.getenv("PANEL_ACCESS_KEY", ""),
            "PUBLIC_API_URL": os.getenv("PUBLIC_API_URL", ""),
        }
        return cfg

    async def setup_hook(self) -> None:
        # SQLite persistence: on a fresh/ephemeral deploy, recover the most
        # recent non-empty database backup from the configured Discord channel
        # before loading cogs that may read/write stored data.
        try:
            from cogs.backup import Backup
            restorer = Backup.__new__(Backup)
            restorer.bot = self
            await restorer.restore_latest_backup_if_needed()
        except Exception:
            logger.exception("Automatic SQLite restore check failed")

        # SQLite bootstrap + one-time JSON migration
        try:
            from utils.storage import _bootstrap
            _bootstrap()
        except Exception:
            logger.exception("SQLite bootstrap failed")

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

        guild_id = self.config.get("GUILD_ID")
        if guild_id:
            # Development/private-server mode: keep slash commands GUILD-ONLY.
            #
            # IMPORTANT: do not leave the same commands registered both globally
            # and in the guild. Discord treats global and guild commands as
            # separate command records, so users can see every command twice.
            # This also cleans up global commands left by older versions that
            # previously used copy_global_to(guild=...).
            guild = discord.Object(id=guild_id)

            # Copy the currently loaded commands into the target guild and sync
            # them immediately. Guild commands are the recommended choice for
            # development/testing because they update instantly.
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            # Remove every global command owned by this application. This is
            # intentionally done only when GUILD_ID is configured, because this
            # bot is deployed for a private Bovary Club server.
            self.tree.clear_commands(guild=None)
            global_synced = await self.tree.sync()

            logger.info(
                "Comandos sincronizados somente no guild %s (%d comandos); "
                "comandos globais removidos (%d)",
                guild_id,
                len(synced),
                len(global_synced),
            )
        else:
            # No GUILD_ID: publish the currently loaded commands globally.
            synced = await self.tree.sync()
            logger.info("Comandos sincronizados globalmente (%d comandos)", len(synced))

    async def on_ready(self):
        if not rotate_status.is_running():
            rotate_status.start()
        logger.info("✅ %s está online! (v2.7.16)", self.user)
        if APPLY_BOT_PROFILE and not self._profile_applied:
            self._profile_applied = True
            await self._apply_profile()

    async def _apply_profile(self):
        """Optional — only when APPLY_BOT_PROFILE=true. Otherwise use Developer Portal."""
        if not self.user:
            return
        try:
            import aiohttp
            kwargs = {}
            async with aiohttp.ClientSession() as session:
                if AVATAR_URL:
                    async with session.get(AVATAR_URL) as resp:
                        if resp.status == 200:
                            kwargs["avatar"] = await resp.read()
                if BANNER_URL:
                    async with session.get(BANNER_URL) as resp:
                        if resp.status == 200:
                            kwargs["banner"] = await resp.read()
            if kwargs:
                await self.user.edit(**kwargs)
                logger.info("Bot profile assets applied (APPLY_BOT_PROFILE=true)")
        except discord.HTTPException as e:
            logger.warning("Could not update bot profile assets: %s", e)
        except Exception:
            logger.exception("Profile update failed")

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


STATUS_INTERVAL_SECONDS = 2 * 60 * 60

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


bot = BovaryBot()
rotate_status.bot = bot  # type: ignore


if __name__ == "__main__":
    # API + health on same process (Render Web Service PORT)
    try:
        from api import start_api
        start_api(bot)
    except Exception:
        logger.exception("Failed to start API — bot will still run")
        try:
            from keep_alive import keep_alive
            keep_alive()
        except Exception:
            pass

    if not TOKEN:
        logger.critical("TOKEN não encontrado. Configure no arquivo .env / Render Environment")
        print("❌ ERRO: TOKEN não encontrado.")
    else:
        try:
            bot.run(TOKEN, log_handler=None)
        except Exception as e:
            logger.exception("Falha ao iniciar o bot: %s", e)
