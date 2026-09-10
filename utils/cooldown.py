"""
Gerenciador de cooldown persistente em JSON.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("bovary_bot.cooldown")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COOLDOWN_FILE = DATA_DIR / "cooldowns.json"


class CooldownManager:
    """Armazena e recupera cooldowns de usuários em arquivo JSON."""

    def __init__(self, filepath: Path = COOLDOWN_FILE):
        self.filepath = filepath
        self._data: Dict[str, str] = {}  # user_id -> ISO timestamp
        self._ensure_dir()
        self.load()

    def _ensure_dir(self) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        if not self.filepath.exists():
            self._data = {}
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Falha ao carregar cooldowns: %s. Iniciando vazio.", e)
            self._data = {}

    def save(self) -> None:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as e:
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
