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
async def adicionar(interaction: discord.Interaction, nome: str):
    nome = nome.strip().title()
    participants[nome] = participants.get(nome, 0) + 1
    save_data()
    await interaction.response.send_message(f"✅ {nome} agora tem **{participants[nome]}** entrada(s) no sorteio!")

# 📋 Mostra lista
@bot.tree.command(name="lista", description="Mostra a lista atual de participantes e suas entradas")
async def lista(interaction: discord.Interaction):
    if not participants:
        await interaction.response.send_message("⚠️ A lista está vazia!")
        return
    lista_formatada = "\n".join([f"{i+1}. **{nome}** — {qtd} entrada(s)" for i, (nome, qtd) in enumerate(participants.items())])
    await interaction.response.send_message(f"📝 **Lista de Participantes:**\n{lista_formatada}")

# 🎲 Sorteio (apenas para administradores)
@bot.tree.command(name="sortear", description="Realiza o sorteio considerando o número de entradas de cada participante (somente admins)")
async def sortear(interaction: discord.Interaction):
    # Verifica permissão
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Você não tem permissão para usar este comando (apenas administradores).", ephemeral=True)
        return

    if not participants:
        await interaction.response.send_message("⚠️ Não há participantes para sortear!")
        return

    pool = []
    for nome, qtd in participants.items():
        pool.extend([nome] * qtd)

    vencedor = random.choice(pool)
    lista_formatada = "\n".join([f"{i+1}. **{nome}** — {qtd} entrada(s)" for i, (nome, qtd) in enumerate(participants.items())])

    await interaction.response.send_message(
        f"🎉 **SORTEIO REALIZADO!** 🎉\n\n📝 **Lista de Participantes:**\n{lista_formatada}\n\n🏆 **Vencedor:** **{vencedor}**! 🎊"
    )

    # Limpa após sorteio
    participants.clear()
    save_data()

# 🧹 Limpar lista (apenas para administradores)
@bot.tree.command(name="limpar_lista", description="Limpa a lista atual de participantes (somente admins)")
async def limpar_lista(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Você não tem permissão para usar este comando (apenas administradores).", ephemeral=True)
        return

    if not participants:
        await interaction.response.send_message("⚠️ A lista já está vazia!")
        return

    participants.clear()
    save_data()
    await interaction.response.send_message("🧹 A lista de sorteio foi limpa com sucesso!")

# ===================== 🔧 EVENTOS E OUTROS COMANDOS ===================== #

@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Game("in Bovary Club Society 🏎️"),
        status=discord.Status.online
    )

    try:
        guild_id = 1384173136085258292  # ID do seu servidor
        guild = discord.Object(id=guild_id)

        # Sincroniza apenas com o Bovary Club Society (instantâneo)
        synced = await bot.tree.sync(guild=guild)

        print(f"✅ {bot.user} está online e sincronizou {len(synced)} comandos no servidor Bovary Club Society!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")
