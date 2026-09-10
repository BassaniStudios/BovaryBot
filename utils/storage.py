"""JSON storage helpers for configs and stats."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("bovary_bot.storage")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _path(name: str) -> Path:
    return DATA_DIR / name


def load_json(name: str, default: Any = None) -> Any:
    path = _path(name)
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load %s: %s", name, e)
        return default if default is not None else {}


def save_json(name: str, data: Any) -> None:
    path = _path(name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.error("Failed to save %s: %s", name, e)


def default_autorole() -> Dict:
    return {
        "title": "Choose your roles",
        "description": "React below to get access to the channels you care about.",
        "color": 0xB450FF,
        "roles": [],
        "message_id": None,
        "channel_id": None,
    }


def default_stats() -> Dict:
    return {
        "messages": {},
        "reactions_given": {},
        "joins": 0,
        "leaves": 0,
        "hourly": {str(i): 0 for i in range(24)},
        "weekday": {str(i): 0 for i in range(7)},
        "media_scores": {},
        "weekly_top": None,
    }
