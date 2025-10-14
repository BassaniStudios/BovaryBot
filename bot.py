from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import random

# 🟢 Mantém o bot online (servidor Flask)
from keep_alive import keep_alive

# 🔑 Token do bot
TOKEN = os.getenv("TOKEN")

# ✋ Emojis automáticos (atualizados)
AUTO_REACTIONS = ["❤️", "🔥", "💯", "💥", "💕", "💎", "🎊", "🎉", "🎀"]

# 💬 Canais onde o bot reage automaticamente
CHANNEL_IDS = [
    1384173879295213689, 1384174586345816134, 1424515140660760647,
    1424515636524220516, 1384173136853078038, 1384173136853078037,
    1424434022058033242, 1384173137071177753, 1424509207172087849,
    1424586421599076473
]

LOG_CHANNEL_ID = 1384173137985540230  # Canal de logs

# ⚙️ Permissões (intents)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 🤖 Criação do bot
bot = commands.Bot(command_prefix="|", intents=intents)

# ===================== 🎟️ SISTEMA DE SORTEIO ===================== #

DATA_FILE = "sorteio.json"
participants = {}

# 🔄 Carregar dados existentes
def load_data():
    global participants
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                participants = json.load(f)
            except json.JSONDecodeError:
                participants = {}
    else:
        participants = {}

# 💾 Salvar dados
def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, indent=4, ensure_ascii=False)

# ➕ Adiciona participante
@bot.tree.command(name="adicionar", description="Adiciona uma pessoa à lista do sorteio (1 entrada por vez)")
@app_commands.describe(nome="Nome da pessoa que vai participar do sorteio")
async def adicionar(interaction: discord.Interaction, nome:
