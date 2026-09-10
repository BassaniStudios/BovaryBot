"""
Utilitários compartilhados do BovaryBot.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import discord
from discord.ext import commands


# Timezone do servidor (São Paulo / Brasil = UTC-3)
SERVER_TZ = timezone(timedelta(hours=-3))


def make_embed(
    title: str = "",
    description: str = "",
    color: Optional[discord.Color] = None,
) -> discord.Embed:
    """Cria um embed padronizado com footer e timestamp."""
    if color is None:
        color = discord.Color.blurple()
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Bova's Bot · Bovary Club Society")
    return embed


def safe_get_channel(
    bot_instance: commands.Bot,
    channel_id: Optional[int],
) -> Optional[discord.abc.GuildChannel]:
    """Retorna o canal ou None se não encontrado / id inválido."""
    if not channel_id:
        return None
    return bot_instance.get_channel(channel_id)


def is_media_in_message(message: discord.Message) -> bool:
    """Detecta se a mensagem contém imagem ou vídeo."""
    for a in message.attachments:
        if a.content_type and a.content_type.startswith(("image/", "video/")):
            return True
        if a.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm", ".mkv", ".gifv")
        ):
            return True

    for e in message.embeds:
        if getattr(e, "type", None) in ("image", "video", "gifv"):
            return True
        if getattr(e, "image", None) and getattr(e.image, "url", None):
            return True
        if getattr(e, "thumbnail", None) and getattr(e.thumbnail, "url", None):
            return True

    return False


def parse_channel_ids(raw: str) -> List[int]:
    """Converte string 'id1,id2,id3' em lista de ints."""
    if not raw or not raw.strip():
        return []
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


def load_int_env(key: str, default: Optional[int] = None) -> Optional[int]:
    """Carrega variável de ambiente como int de forma segura."""
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default
