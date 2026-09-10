"""Compatibility shim — prefer api.start_api(bot) from bot.py."""
from api import keep_alive, app, health  # noqa: F401
