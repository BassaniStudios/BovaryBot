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
# Optional local GIF/PNG for avatar (takes priority over BOT_AVATAR_URL when set)
AVATAR_FILE = os.getenv("BOT_AVATAR_FILE", "").strip()


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
        # Hardcoded defaults are the production Bovary IDs. Prefer setting them
        # explicitly in the environment so other deployments do not accidentally
        # use production channels.
        _hardcoded_defaults_used = []
        def _chan(key, default):
            val = load_int_env(key, default)
            if os.getenv(key) is None or str(os.getenv(key, "")).strip() == "":
                _hardcoded_defaults_used.append(key)
            return val

        cfg = {
            "GUILD_ID": load_int_env("GUILD_ID", 1384173136085258292),  # main Bovary server (commands live here)
            "LOG_CHANNEL_ID": _chan("LOG_CHANNEL_ID", 1441663299065217114),
            "MESSAGE_LOG_CHANNEL_ID": _chan("MESSAGE_LOG_CHANNEL_ID", 1432715549116207248),
            # General WebLogs channel (channel/admin events). Message edit/delete logs stay separate.
            "WEBLOGS_CHANNEL_ID": _chan("WEBLOGS_CHANNEL_ID", 1548153354675556412),
            "BOT_ROOM_CHANNEL_ID": _chan("BOT_ROOM_CHANNEL_ID", 1424436722984423529),
            # Auto backup of SQLite to a Discord channel (Render free mitigation)
            "BACKUP_CHANNEL_ID": _chan("BACKUP_CHANNEL_ID", 1548438716391890994),  # home server backup room
            "BACKUP_GUILD_ID": load_int_env("BACKUP_GUILD_ID", 1426594245510430903),  # casa = backup only (NO commands)

            "BACKUP_INTERVAL_HOURS": load_int_env("BACKUP_INTERVAL_HOURS", 24) or 24,
            "IGNORE_CHANNEL_ID": _chan("IGNORE_CHANNEL_ID", 1384173137985540233),
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
        if _hardcoded_defaults_used:
            logger.warning(
                "Using hardcoded production channel defaults for: %s — "
                "set these explicitly in the environment for safety.",
                ", ".join(_hardcoded_defaults_used),
            )
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

            # Remove every global command owned by this application.
            self.tree.clear_commands(guild=None)
            global_synced = await self.tree.sync()

            # Home/casa server is backup-only: strip any slash commands left there
            # from older deploys so they do not appear or fire on that guild.
            home_id = self.config.get("BACKUP_GUILD_ID")
            if home_id and int(home_id) != int(guild_id):
                try:
                    home = discord.Object(id=int(home_id))
                    self.tree.clear_commands(guild=home)
                    cleared_home = await self.tree.sync(guild=home)
                    logger.info(
                        "Servidor casa %s é só backup — comandos removidos (%d residual)",
                        home_id, len(cleared_home),
                    )
                except Exception:
                    logger.exception("Falha ao limpar comandos do servidor casa %s", home_id)

            logger.info(
                "Comandos sincronizados SOMENTE no servidor principal %s (%d); "
                "globais removidos (%d). Casa = backup only.",
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

        version = "2.7.18"
        try:
            version_path = Path(__file__).parent / "VERSION"
            if version_path.exists():
                version = version_path.read_text(encoding="utf-8").strip() or version
        except Exception:
            pass

        logger.info("✅ %s está online! (v%s)", self.user, version)

        # Validate critical privileged intents (Message Content + Members)
        try:
            if not self.intents.message_content:
                logger.warning(
                    "INTENT WARNING: message_content is disabled. "
                    "Message Log, sticky, timestamp reminders and auto-reactions will be limited."
                )
            if not self.intents.members:
                logger.warning(
                    "INTENT WARNING: members is disabled. "
                    "Join/leave logs, namehistory, welcome and staff role checks may fail."
                )
        except Exception:
            logger.exception("Could not validate intents")

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

            # Local file takes priority (useful for the built-in assets/bovas_bot_avatar.gif)
            if AVATAR_FILE:
                path = Path(AVATAR_FILE)
                if not path.is_file():
                    # also try relative to project root
                    path = Path(__file__).resolve().parent / AVATAR_FILE
                if path.is_file():
                    kwargs["avatar"] = path.read_bytes()
                    logger.info("Using local avatar file: %s", path)
                else:
                    logger.warning("BOT_AVATAR_FILE not found: %s", AVATAR_FILE)

            async with aiohttp.ClientSession() as session:
                if "avatar" not in kwargs and AVATAR_URL:
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
        except discord.NotFound:
            # Interaction token expired (>15 min) or unknown — nothing to do
            pass
        except Exception:
            logger.exception("Failed to send app command error message")


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
