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

try:
    from keep_alive import keep_alive
except Exception:
    def keep_alive():
        return None

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

# Profile assets (set once on ready if URLs are set)
AVATAR_URL = os.getenv(
    "BOT_AVATAR_URL",
    "https://ik.imagekit.io/BassaniStudios/bovary%20pic%20meet/setembro/teste.png?updatedAt=1788398770003",
)
BANNER_URL = os.getenv(
    "BOT_BANNER_URL",
    "https://ik.imagekit.io/BassaniStudios/bovary%20pic%20meet/setembro/qweweqwewqewqeqweqweqwe.png",
)


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
            # chat channels for media scoring
            "1384173137071177752,1425230894641451059,1542185824173424650,1425297078816473109"
        )
        cfg = {
            "GUILD_ID": load_int_env("GUILD_ID"),
            "LOG_CHANNEL_ID": load_int_env("LOG_CHANNEL_ID", 1441663299065217114),
            "MESSAGE_LOG_CHANNEL_ID": load_int_env("MESSAGE_LOG_CHANNEL_ID", 1432715549116207248),
            "BOT_ROOM_CHANNEL_ID": load_int_env("BOT_ROOM_CHANNEL_ID", 1424436722984423529),
            "IGNORE_CHANNEL_ID": load_int_env("IGNORE_CHANNEL_ID", 1384173137985540233),
            "STAFF_LOG_CHANNEL": load_int_env("STAFF_LOG_CHANNEL", 1444186478157500508),
            "CREW_LEADER_ROLE_ID": load_int_env("CREW_LEADER_ROLE_ID", 1384173136177791048),
            "REQUIRED_INVITE_CHANNEL": load_int_env("REQUIRED_INVITE_CHANNEL", 1444094610157600859),
            "BOOST_CHANNEL_ID": load_int_env("BOOST_CHANNEL_ID", 1384173136638906407),
            "CHANNEL_IDS": parse_channel_ids(os.getenv("CHANNEL_IDS", media_default)),
            "MEDIA_SCORE_CHANNEL_IDS": parse_channel_ids(
                os.getenv(
                    "MEDIA_SCORE_CHANNEL_IDS",
                    "1384173879295213689,1384174586345816134,1424515140660760647,"
                    "1424515636524220516,1384173136853078038,1425870476290428978,"
                    "1424434022058033242,1384173137071177753,1424509207172087849,"
                    "1424586421599076473,1425669117750284318,"
                    "1384173137071177752,1425230894641451059,1542185824173424650,1425297078816473109",
                )
            ),
            "INVITE_COOLDOWN_SECONDS": load_int_env("INVITE_COOLDOWN_SECONDS", 300) or 300,
            "AUTO_REACTIONS": ["❤️", "🔥", "💯", "💥", "🎀"],
            "PANEL_ACCESS_ROLE_ID": load_int_env("PANEL_ACCESS_ROLE_ID", 1542169549833773156),
            "PANEL_URL": os.getenv("PANEL_URL", "https://bovaryclub.github.io/BovaryBot-Panel/"),
            "PANEL_ACCESS_KEY": os.getenv("PANEL_ACCESS_KEY", "BOVA-CORE-2026"),
        }
        return cfg

    async def setup_hook(self) -> None:
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
        if not self._profile_applied:
            self._profile_applied = True
            await self._apply_profile()

    async def _apply_profile(self):
        """Update bot avatar/banner when possible (rate-limited by Discord)."""
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
                logger.info("Bot profile avatar/banner updated")
        except discord.HTTPException as e:
            # Often hits rate limit if avatar already set recently
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
    keep_alive()

    if not TOKEN:
        logger.critical("TOKEN não encontrado. Configure no arquivo .env")
        print("❌ ERRO: TOKEN não encontrado. Configure no arquivo .env")
    else:
        try:
            bot.run(TOKEN, log_handler=None)
        except Exception as e:
            logger.exception("Falha ao iniciar o bot: %s", e)
