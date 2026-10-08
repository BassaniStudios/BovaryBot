"""
Bova's Bot — Official private bot of Bovary Club Society.
Version: 2.12.0
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
        # max_messages: discord.py internal message cache (default 1000 is too small
        # for delete-log recovery on active servers). Keep in sync with MESSAGE_CACHE_SIZE.
        try:
            _max_msg = int(os.getenv("MESSAGE_CACHE_SIZE", "12000").strip() or "12000")
            _max_msg = max(1000, min(_max_msg, 50_000))
        except (TypeError, ValueError):
            _max_msg = 12000
        super().__init__(
            command_prefix="|",
            intents=intents,
            help_command=None,
            max_messages=_max_msg,
        )
        self.config = self._load_config()
        self.cooldown_manager = CooldownManager()
        self._profile_applied = False

    def _load_config(self) -> dict:
        # Media channels for auto-react + ranking scans (updated 2026-10-05).
        media_default = (
            "1384173879295213689,1384174586345816134,1424515140660760647,"
            "1537555862372094112,1425870476290428978,1532220539257622649,"
            "1531071911499661352,1425669117750284318,1424509207172087849,"
            "1384173136853078038"
        )
        reactions_default = ["✨", "🌟", "💥", "🎉"]
        # Hardcoded defaults are the production Bovary IDs. Prefer setting them
        # explicitly in the environment so other deployments do not accidentally
        # use production channels.
        _hardcoded_defaults_used = []
        def _chan(key, default):
            val = load_int_env(key, default)
            if os.getenv(key) is None or str(os.getenv(key, "")).strip() == "":
                _hardcoded_defaults_used.append(key)
            return val

        def _channel_list(key: str, default: str) -> list:
            """Parse CHANNEL_IDS / MEDIA_SCORE…; empty env falls back to default."""
            raw = os.getenv(key)
            if raw is None or not str(raw).strip():
                if raw is not None:
                    _hardcoded_defaults_used.append(key)
                return parse_channel_ids(default)
            return parse_channel_ids(raw)

        def _reactions_list() -> list:
            raw = os.getenv("AUTO_REACTIONS")
            if raw is None or not str(raw).strip():
                return list(reactions_default)
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            return parts or list(reactions_default)

        cfg = {
            "GUILD_ID": load_int_env("GUILD_ID", 1384173136085258292),  # main Bovary server (commands live here)
            "LOG_CHANNEL_ID": _chan("LOG_CHANNEL_ID", 1441663299065217114),
            "MESSAGE_LOG_CHANNEL_ID": _chan("MESSAGE_LOG_CHANNEL_ID", 1432715549116207248),
            # General WebLogs channel (channel/admin events). Message edit/delete logs stay separate.
            "WEBLOGS_CHANNEL_ID": _chan("WEBLOGS_CHANNEL_ID", 1548153354675556412),
            "BOT_ROOM_CHANNEL_ID": _chan("BOT_ROOM_CHANNEL_ID", 1424436722984423529),
            "NAME_HISTORY_LOG_CHANNEL_ID": _chan("NAME_HISTORY_LOG_CHANNEL_ID", 1441663299065217114),
            # Auto backup of SQLite to a Discord channel (Render free mitigation)
            "BACKUP_CHANNEL_ID": _chan("BACKUP_CHANNEL_ID", 1548438716391890994),  # home server backup room
            "BACKUP_GUILD_ID": load_int_env("BACKUP_GUILD_ID", 1426594245510430903),  # casa = backup only (NO commands)

            "BACKUP_INTERVAL_HOURS": load_int_env("BACKUP_INTERVAL_HOURS", 24) or 24,
            "IGNORE_CHANNEL_ID": _chan("IGNORE_CHANNEL_ID", 1384173137985540233),
            "STAFF_LOG_CHANNEL": load_int_env("STAFF_LOG_CHANNEL", 1444186478157500508),
            # DM inbox/support channel → bot-chat
            "DM_INBOX_CHANNEL_ID": load_int_env("DM_INBOX_CHANNEL_ID", 1548188378623778847),
            "DM_AUTO_RESPONSE_ENABLED": os.getenv("DM_AUTO_RESPONSE_ENABLED", "false").lower() in ("1", "true", "yes"),
            # Automatic reminders for any <t:UNIX:R> timestamp found in guild messages/embeds.
            "TIMESTAMP_REMINDER_ENABLED": os.getenv("TIMESTAMP_REMINDER_ENABLED", "true").lower() in ("1", "true", "yes"),
            "TIMESTAMP_REMINDER_MINUTES": load_int_env("TIMESTAMP_REMINDER_MINUTES", 30) or 30,
            "TIMESTAMP_REMINDER_TEXT": os.getenv("TIMESTAMP_REMINDER_TEXT", ""),
            "DM_AUTO_RESPONSE_TEXT": os.getenv(
                "DM_AUTO_RESPONSE_TEXT",
                "Hello! Your message was received. Our team has been notified and will reply as soon as possible.",
            ),
            "CREW_LEADER_ROLE_ID": load_int_env("CREW_LEADER_ROLE_ID", 1384173136177791048),
            "REQUIRED_INVITE_CHANNEL": load_int_env("REQUIRED_INVITE_CHANNEL", 1444094610157600859),
            "CHANNEL_IDS": _channel_list("CHANNEL_IDS", media_default),
            "MEDIA_SCORE_CHANNEL_IDS": _channel_list("MEDIA_SCORE_CHANNEL_IDS", media_default),
            # Channels ignored by media/reaction ranking scans
            "EXCLUDE_MEDIA_RANKING_CHANNELS": parse_channel_ids(
                "1384173137662574739,1548153354675556412,1548188378623778847,"
                "1424436722984423529,1444740208208908338"
            ),
            # Channels used for chat word-count ranking
            "CHAT_RANKING_CHANNEL_IDS": parse_channel_ids(
                "1384173137071177752,1425230894641451059,1542185824173424650,"
                "1384173137071177757,1444094610157600859,1553823431349371042,"
                "1531417799300350073,1554302868293554196"
            ),
            "INVITE_COOLDOWN_SECONDS": load_int_env("INVITE_COOLDOWN_SECONDS", 300) or 300,
            "AUTO_REACTIONS": _reactions_list(),
            "PANEL_ACCESS_ROLE_ID": load_int_env("PANEL_ACCESS_ROLE_ID", 1542169549833773156),
            # Role allowed to call the HTTP API from the web panel
            "STAFF_API_ROLE_ID": load_int_env("STAFF_API_ROLE_ID", 1547647694997037137),
            # Role allowed to use ONLY /fenrir (FiveMHosts)
            "FIVEM_HOSTS_ROLE_ID": load_int_env("FIVEM_HOSTS_ROLE_ID", 1537850168999809215),
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
        # Cogs intentionally removed in v2.9.x — never load even if leftover
        # files remain in an old Git repo / Render workspace.
        BLOCKED_COGS = {
            "autorole",
            "autofeed",
            "autofeeds",
            "auto_role",
            "auto_feed",
            "auto_feeds",
        }
        for file in cogs_dir.glob("*.py"):
            if file.name.startswith("_"):
                continue
            stem = file.stem
            if stem in BLOCKED_COGS or stem.startswith("autorole") or stem.startswith("autofeed"):
                logger.warning(
                    "Ignorando cog legado (removido): cogs.%s — delete o arquivo %s do repositório",
                    stem, file.name,
                )
                continue
            ext = f"cogs.{stem}"
            try:
                await self.load_extension(ext)
                logger.info("Cog carregado: %s", ext)
            except Exception:
                logger.exception("Falha ao carregar cog %s", ext)

        self._install_slash_command_access_policy()

        # Slash sync is intentionally NOT awaited here. A full guild command PUT
        # can hit Discord 429 for many minutes and would block setup_hook, which
        # delays READY — bot appears offline while only the Flask /health is up.
        import asyncio
        asyncio.create_task(self._sync_app_commands_background())

    async def _sync_app_commands_background(self) -> None:
        """Sync slash commands after READY — single guild PUT with 429 retries.

        Root cause of missing commands after many deploys:
        - Multiple tree.sync() calls (guild + global wipe + backup clear) hit
          Discord's application-command rate limit hard.
        - A single 10-minute timeout aborts while discord.py is still retrying 429s,
          so the guild never gets a successful overwrite and slash menus stay empty
          or stale.

        New strategy (safe after a long uptime / recovered bucket):
        - Optional short delay (default 60s; override with COMMAND_SYNC_DELAY_SECONDS).
        - ONE primary operation: copy_global_to + sync(guild=main).
        - Global wipe is OFF by default (ENABLE_GLOBAL_COMMAND_CLEAR=true to re-enable).
        - Up to 5 attempts; on 429 sleep retry_after (or 60–120s) and try again.
        - Overall budget 30 minutes.
        - SKIP_COMMAND_SYNC=true skips entirely.
        - FORCE_COMMAND_RESYNC=true does a clear+sync wipe first (use rarely).
        """
        import asyncio
        import discord

        if str(os.getenv("SKIP_COMMAND_SYNC", "")).strip().lower() in {"1", "true", "yes", "on"}:
            logger.warning("SKIP_COMMAND_SYNC set — slash commands will NOT be re-registered this boot")
            return

        try:
            await self.wait_until_ready()
        except Exception:
            pass

        try:
            delay = max(0, int(os.getenv("COMMAND_SYNC_DELAY_SECONDS", "60")))
        except ValueError:
            delay = 60

        if delay:
            logger.info(
                "Aguardando %ss antes do sync de slash commands. "
                "Não reinicie o serviço durante esta espera.",
                delay,
            )
            await asyncio.sleep(delay)

        force_wipe = str(os.getenv("FORCE_COMMAND_RESYNC", "")).strip().lower() in {
            "1", "true", "yes", "on",
        }
        clear_globals = str(os.getenv("ENABLE_GLOBAL_COMMAND_CLEAR", "")).strip().lower() in {
            "1", "true", "yes", "on",
        }

        async def _once() -> list:
            import discord
            main_id = self.config.get("GUILD_ID")
            casa_id = self.config.get("BACKUP_GUILD_ID")
            targets = []
            if main_id:
                targets.append(int(main_id))
            if casa_id and int(casa_id) not in targets:
                targets.append(int(casa_id))

            if not targets:
                synced = await self.tree.sync()
                logger.info("Comandos sincronizados globalmente (%d)", len(synced))
                return list(synced)

            all_synced = []
            for gid in targets:
                guild = discord.Object(id=gid)
                if force_wipe:
                    try:
                        self.tree.clear_commands(guild=guild)
                        wiped = await self.tree.sync(guild=guild)
                        logger.info("FORCE wipe guild %s (%d residual)", gid, len(wiped))
                    except Exception:
                        logger.exception("Falha wipe guild %s", gid)

                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                all_synced = list(synced)
                names = sorted({c.name for c in synced})
                logger.info(
                    "Slash OK no guild %s: %d comandos. Exemplos: %s",
                    gid,
                    len(synced),
                    ", ".join(names[:20]) + ("…" if len(names) > 20 else ""),
                )

            if clear_globals:
                try:
                    self.tree.clear_commands(guild=None)
                    global_synced = await self.tree.sync()
                    logger.info("Globais limpos (%d residual)", len(global_synced))
                except Exception:
                    logger.exception("Falha ao limpar globais")

            names = sorted({c.name for c in all_synced})
            cursed = [n for n in names if n.startswith("cursedhoroscope")]
            if cursed:
                logger.info("Cursed Horoscope registrado: %s", ", ".join(cursed))
            return all_synced

        max_attempts = 5
        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                await asyncio.wait_for(_once(), timeout=300)
                return
            except asyncio.TimeoutError as e:
                last_err = e
                logger.error(
                    "Sync attempt %d/%d timed out (300s). Aguardando 90s…",
                    attempt, max_attempts,
                )
                await asyncio.sleep(90)
            except discord.HTTPException as e:
                last_err = e
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after is None:
                        try:
                            retry_after = float((e.response.json() or {}).get("retry_after", 60))
                        except Exception:
                            retry_after = 90.0
                    wait = max(30.0, float(retry_after) + 5.0)
                    logger.warning(
                        "Rate limit 429 no sync (attempt %d/%d). Aguardando %.0fs…",
                        attempt, max_attempts, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.exception(
                        "HTTP %s no sync (attempt %d/%d)", e.status, attempt, max_attempts
                    )
                    await asyncio.sleep(30)
            except Exception as e:
                last_err = e
                logger.exception("Sync attempt %d/%d failed", attempt, max_attempts)
                await asyncio.sleep(30)

        logger.error(
            "Sync de slash commands FALHOU após %d tentativas. Último erro: %s. "
            "Use /sync_commands no Discord (staff) ou POST /api/sync-commands, "
            "ou reinicie UMA vez com COMMAND_SYNC_DELAY_SECONDS=120.",
            max_attempts,
            last_err,
        )

    def _install_slash_command_access_policy(self) -> None:
        """Slash access:

        Full access:
          - Bot owner user ID (B4ssani)
          - Lider role (PANEL_ACCESS_ROLE_ID)

        Special staff (Host Meet Organizer + Bot Staff API):
          - All slash commands EXCEPT a fixed blacklist
          - No channel restriction (whole server)

        FiveMHosts role:
          - ONLY /fenrir (nothing else)

        Everyone else: blocked on slash (panel buttons still work).
        """
        OWNER_USER_ID = 921803925051572266  # B4ssani — full access
        primary_role = int(self.config.get("PANEL_ACCESS_ROLE_ID") or 1542169549833773156)  # Lider
        special_roles = {
            int(self.config.get("CREW_LEADER_ROLE_ID") or 1384173136177791048),  # Host Meet Organizer
            int(self.config.get("STAFF_API_ROLE_ID") or 1547647694997037137),    # Bot Staff API
        }
        # Role that may ONLY use /fenrir
        fivem_hosts_role = int(self.config.get("FIVEM_HOSTS_ROLE_ID") or 1537850168999809215)  # FiveMHosts
        fivem_hosts_allowed = {"fenrir"}
        # Commands special roles may NOT use
        special_denied = {
            "say",
            "backup_export",
            "backup_hint",
            "backup_now",
            "backup_restore",
            "cmd_add",
            "cmd_list",
            "cmd_remove",
            "commands_panel",
            "db_status",
            "dm_auto_response",
            "dm_history",
            "panel",
            "purge",
            "sync_commands",
            "weblogs_config",
            "nitroraffles",
            "nitroraffles_panel",
            "nitroraffles_result",
            "nitroraffles_reset",
            "nitroraffles_test",
        }

        async def role_check(interaction: discord.Interaction) -> bool:
            member = interaction.user
            if not isinstance(member, discord.Member):
                raise discord.app_commands.CheckFailure("Guild member context required.")

            command_name = (
                getattr(interaction.command, "qualified_name", None)
                or getattr(interaction.command, "name", "")
                or ""
            )
            # Group subcommands use "parent sub" — compare by leaf name too
            leaf = command_name.split()[-1] if command_name else ""

            # Owner always full access
            if int(member.id) == OWNER_USER_ID:
                return True

            role_ids = {r.id for r in member.roles}

            # Lider — full access
            if primary_role in role_ids:
                return True

            # Special roles — all except blacklist, any channel
            if role_ids & special_roles:
                if command_name in special_denied or leaf in special_denied:
                    raise discord.app_commands.CheckFailure(
                        "Este comando é restrito ao Lider / dono do bot."
                    )
                return True

            # FiveMHosts — only /fenrir
            if fivem_hosts_role in role_ids:
                if command_name in fivem_hosts_allowed or leaf in fivem_hosts_allowed:
                    return True
                raise discord.app_commands.CheckFailure(
                    "Your role can only use the /fenrir command."
                )

            raise discord.app_commands.CheckFailure(
                "Este slash command é restrito aos cargos autorizados."
            )

        self.tree.interaction_check = role_check  # type: ignore[method-assign]
        count = len(list(self.tree.walk_commands()))
        logger.info(
            "Slash policy: owner=%s Lider=%s special=%s fivem_hosts=%s denied=%s | %d commands",
            OWNER_USER_ID,
            primary_role,
            sorted(special_roles),
            fivem_hosts_role,
            sorted(special_denied),
            count,
        )

    async def on_ready(self):
        if not rotate_status.is_running():
            rotate_status.start()

        version = "2.7.19"
        try:
            version_path = Path(__file__).parent / "VERSION"
            if version_path.exists():
                version = version_path.read_text(encoding="utf-8").strip() or version
        except Exception:
            pass

        logger.info("✅ %s está online! (v%s)", self.user, version)

        # Validate critical privileged intents (Message Content + Members).
        # Member join/leave logging is driven by Discord's native Guild Members gateway events.
        try:
            if not self.intents.members:
                logger.error(
                    "MEMBERS INTENT DISABLED IN CODE: native join/leave events cannot be received."
                )
            if not self.intents.message_content:
                logger.warning(
                    "INTENT WARNING: message_content is disabled. "
                    "Message Log, sticky, timestamp reminders and auto-reactions will be limited."
                )
            if self.intents.members:
                logger.info(
                    "Members intent enabled: native member join/leave events are available."
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
        elif isinstance(error, discord.app_commands.CheckFailure):
            message = str(error) or "🚫 Você não tem o cargo necessário para usar este slash command."
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
