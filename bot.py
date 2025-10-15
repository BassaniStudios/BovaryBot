from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import random
from datetime import datetime, timezone
import traceback
import time

# 🟢 Mantém o bot online (Flask server)
from keep_alive import keep_alive

# 🔑 Token do bot (configurado no Replit → Secrets)
TOKEN = os.getenv("TOKEN")

# ✋ Emojis automáticos
AUTO_REACTIONS = ["❤️", "🔥", "💯", "💥", "💕", "💎", "🎊", "🎉", "🎀"]

# 💬 Canais com reação automática
CHANNEL_IDS = [
    1384173879295213689, 1384174586345816134, 1424515140660760647,
    1424515636524220516, 1384173136853078038, 1384173136853078037,
    1424434022058033242, 1384173137071177753, 1424509207172087849,
    1424586421599076473
]

LOG_CHANNEL_ID = 1384173137985540230  # Canal de logs

# ⚙️ Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 🤖 Criação do bot
bot = commands.Bot(command_prefix="|", intents=intents)

# ===================== 🎟️ SISTEMA DE SORTEIO ===================== #

DATA_FILE = "giveaway.json"
participants = {}

def load_data():
    """🔄 Carrega dados salvos"""
    global participants
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                participants = json.load(f)
            except json.JSONDecodeError:
                participants = {}
    else:
        participants = {}

def save_data():
    """💾 Salva dados"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, indent=4, ensure_ascii=False)

# ➕ Adicionar participante
@bot.tree.command(name="add", description="Adiciona uma pessoa ao sorteio")
@app_commands.describe(name="Nome da pessoa para participar do sorteio")
async def add(interaction: discord.Interaction, name: str):
    name = name.strip().title()
    participants[name] = participants.get(name, 0) + 1
    save_data()
    await interaction.response.send_message(f"✅ **{name}** agora tem **{participants[name]}** entrada(s) no sorteio!")

# ✏️ Editar nome
@bot.tree.command(name="edit_name", description="Edita o nome de um participante existente")
@app_commands.describe(old="Nome atual", new="Novo nome")
async def edit_name(interaction: discord.Interaction, old: str, new: str):
    old = old.strip().title()
    new = new.strip().title()

    if old not in participants:
        await interaction.response.send_message(f"⚠️ O nome **{old}** não foi encontrado!")
        return

    participants[new] = participants.pop(old)
    save_data()
    await interaction.response.send_message(f"✏️ O participante **{old}** foi renomeado para **{new}** com sucesso!")

# ➖ Remover entrada
@bot.tree.command(name="remove_entry", description="Remove uma entrada de um participante")
@app_commands.describe(name="Nome da pessoa que vai perder uma entrada")
async def remove_entry(interaction: discord.Interaction, name: str):
    name = name.strip().title()

    if name not in participants:
        await interaction.response.send_message(f"⚠️ O nome **{name}** não está na lista!")
        return

    participants[name] -= 1
    if participants[name] <= 0:
        del participants[name]
        msg = f"🗑️ **{name}** foi completamente removido da lista."
    else:
        msg = f"➖ Uma entrada removida de **{name}**. Agora tem **{participants[name]}** entrada(s)."

    save_data()
    await interaction.response.send_message(msg)

# 📋 Listar participantes
@bot.tree.command(name="list", description="Mostra a lista de participantes do sorteio")
async def list_command(interaction: discord.Interaction):
    if not participants:
        await interaction.response.send_message("⚠️ A lista está vazia!")
        return
    formatted_list = "\n".join(
        [f"{i+1}. **{name}** — {count} entrada(s)" for i, (name, count) in enumerate(participants.items())]
    )
    await interaction.response.send_message(f"📝 **Lista de participantes:**\n{formatted_list}")

# 🎲 Sortear
@bot.tree.command(name="draw", description="Realiza o sorteio (apenas administradores)")
async def draw(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Apenas administradores podem usar este comando.", ephemeral=True)
        return

    if not participants:
        await interaction.response.send_message("⚠️ Não há participantes!")
        return

    pool = [name for name, count in participants.items() for _ in range(count)]
    winner = random.choice(pool)

    formatted_list = "\n".join(
        [f"{i+1}. **{name}** — {count} entrada(s)" for i, (name, count) in enumerate(participants.items())]
    )

    await interaction.response.send_message(
        f"🎉 **RESULTADO DO SORTEIO!** 🎉\n\n📝 **Lista de participantes:**\n{formatted_list}\n\n🏆 **Vencedor:** **{winner}** 🎊"
    )

    participants.clear()
    save_data()

# 🧹 Limpar lista
@bot.tree.command(name="clear_list", description="Limpa a lista de participantes (admin apenas)")
async def clear_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Apenas administradores podem usar este comando.", ephemeral=True)
        return

    participants.clear()
    save_data()
    await interaction.response.send_message("🧹 Lista de sorteio limpa com sucesso!")

# 🕒 Timestamp
@bot.tree.command(name="timestamp", description="Gera um horário global")
@app_commands.describe(
    date="Data no formato DD/MM/YYYY (opcional)",
    time="Horário em HH:MM (24h)"
)
async def timestamp(interaction: discord.Interaction, time: str, date: str = None):
    try:
        now = datetime.now()
        if date:
            day, month, year = map(int, date.split("/"))
        else:
            day, month, year = now.day, now.month, now.year

        h, m = map(int, time.split(":"))
        dt = datetime(year, month, day, h, m, tzinfo=timezone.utc)
        ts = int(dt.timestamp())

        await interaction.response.send_message(
            f"🕒 **Tempo Global:** <t:{ts}:F>\n"
            f"⏰ **Tempo Relativo:** <t:{ts}:R>\n\n"
            f"🧩 Use isso em mensagens futuras:\n"
            f"`<t:{ts}:F>` ou `<t:{ts}:R>`"
        )
    except Exception as e:
        await interaction.response.send_message("⚠️ Use o formato correto: `/timestamp time:19:30 date:14/10/2025`", ephemeral=True)
        print(e)

# 🏓 Ping
@bot.tree.command(name="ping", description="Mostra a latência do bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", description=f"**Latência:** `{latency}ms`", color=discord.Color.blue())
    embed.set_footer(text="Bovary Club Society")
    await interaction.response.send_message(embed=embed)

# ===================== 🔧 EVENTOS ===================== #

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("em Bovary Club Society 🏎️"), status=discord.Status.online)
    load_data()
    try:
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} está online com {len(synced)} comandos!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

@bot.event
async def on_error(event, *args, **kwargs):
    print(f"⚠️ Erro detectado em evento: {event}")
    traceback.print_exc()

@bot.event
async def on_command_error(ctx, error):
    print(f"⚠️ Erro em comando: {error}")
    traceback.print_exc()

# ===================== 🚀 EXECUÇÃO ===================== #

keep_alive()

while True:
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"⚠️ Bot caiu. Reiniciando em 5s...\nErro: {e}")
        time.sleep(5)
        
