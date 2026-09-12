"""
Gerenciador de cooldown persistente — SQLite via storage.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.cooldown")

COOLDOWN_KEY = "cooldowns.json"


class CooldownManager:
    """Armazena e recupera cooldowns de usuários."""

    def __init__(self, filepath=None):
        self._data: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        raw = load_json(COOLDOWN_KEY, {})
        if isinstance(raw, dict):
            self._data = raw
        else:
            self._data = {}

    def save(self) -> None:
        try:
            save_json(COOLDOWN_KEY, self._data)
        except Exception as e:
            logger.error("Falha ao salvar cooldowns: %s", e)

    def get_last(self, user_id: int) -> Optional[datetime]:
        key = str(user_id)
        raw = self._data.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def set_now(self, user_id: int) -> None:
        key = str(user_id)
        self._data[key] = datetime.now(timezone.utc).isoformat()
        self.save()

    def remaining_seconds(self, user_id: int, cooldown_seconds: int) -> float:
        last = self.get_last(user_id)
        if not last:
            return 0.0
        now = datetime.now(timezone.utc)
        elapsed = (now - last).total_seconds()
        remaining = cooldown_seconds - elapsed
        return max(0.0, remaining)

    def is_on_cooldown(self, user_id: int, cooldown_seconds: int) -> bool:
        return self.remaining_seconds(user_id, cooldown_seconds) > 0
