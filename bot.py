from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import random
from datetime import datetime, timezone
from keep_alive import keep_alive  # 🔥 Mantém o bot ativo

# 🔑 Token
TOKEN = os.getenv("TOKEN")

# ✋ Emojis de auto-reação
AUTO_REACTIONS = ["❤️", "🔥", "💯", "💥", "💕", "💎", "🎊", "🎉", "🎀"]

# 💬 Canais onde o bot reage automaticamente
CHANNEL_IDS = [
    1384173879295213689,
    1384174586345816134,
    1424515140660760647,
    1424515636524220516,
    1384173136853078038,
    1425870476290428978,
    1424434022058033242,
    1384173137071177753,
    1424509207172087849,
    1424586421599076473,
    1425669117750284318
]


LOG_CHANNEL_ID = 1424436722984423529  # Canal de log

# ⚙️ Intents do bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# 🤖 Inicialização do bot
bot = commands.Bot(command_prefix="|", intents=intents)

# ===================== 🎟️ SISTEMA DE SORTEIO ===================== #

DATA_FILE = "giveaway.json"
participants = {}

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

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, indent=4, ensure_ascii=False)

# ➕ Adicionar participante
@bot.tree.command(name="add", description="Adiciona uma pessoa ao sorteio (1 entrada por vez)")
@app_commands.describe(name="Nome da pessoa que vai participar")
async def add(interaction: discord.Interaction, name: str):
    name = name.strip().title()
    participants[name] = participants.get(name, 0) + 1
    save_data()
    await interaction.response.send_message(f"✅ **{name}** agora tem **{participants[name]}** entrada(s)!")

# ✏️ Editar nome
@bot.tree.command(name="edit_name", description="Edita o nome de um participante")
@app_commands.describe(old="Nome atual", new="Novo nome")
async def edit_name(interaction: discord.Interaction, old: str, new: str):
    old, new = old.strip().title(), new.strip().title()
    if old not in participants:
        await interaction.response.send_message(f"⚠️ **{old}** não foi encontrado!")
        return
    participants[new] = participants.pop(old)
    save_data()
    await interaction.response.send_message(f"✏️ **{old}** foi renomeado para **{new}** com sucesso!")

# ➖ Remover entrada
@bot.tree.command(name="remove_entry", description="Remove uma entrada de um participante")
@app_commands.describe(name="Nome da pessoa")
async def remove_entry(interaction: discord.Interaction, name: str):
    name = name.strip().title()
    if name not in participants:
        await interaction.response.send_message(f"⚠️ **{name}** não está na lista!")
        return
    participants[name] -= 1
    if participants[name] <= 0:
        del participants[name]
        await interaction.response.send_message(f"🗑️ **{name}** foi completamente removido!")
    else:
        await interaction.response.send_message(f"➖ Uma entrada removida de **{name}**. Agora tem **{participants[name]}** entrada(s).")
    save_data()

# 📋 Mostrar lista
@bot.tree.command(name="list", description="Mostra a lista de participantes")
async def list_command(interaction: discord.Interaction):
    if not participants:
        await interaction.response.send_message("⚠️ Nenhum participante no momento!")
        return
    formatted = "\n".join([f"{i+1}. **{n}** — {c} entrada(s)" for i, (n, c) in enumerate(participants.items())])
    await interaction.response.send_message(f"📝 **Participantes:**\n{formatted}")

# 🎲 Sortear
@bot.tree.command(name="draw", description="Realiza o sorteio (apenas admin)")
async def draw(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Apenas administradores podem usar este comando.", ephemeral=True)
        return
    if not participants:
        await interaction.response.send_message("⚠️ Nenhum participante para sortear!")
        return
    pool = [n for n, c in participants.items() for _ in range(c)]
    winner = random.choice(pool)
    await interaction.response.send_message(f"🎉 **Resultado do Sorteio!** 🎉\n🏆 Vencedor: **{winner}**! 🎊")
    participants.clear()
    save_data()

# 🧹 Limpar lista
@bot.tree.command(name="clear_list", description="Limpa toda a lista (admin)")
async def clear_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Apenas admin pode limpar a lista.", ephemeral=True)
        return
    participants.clear()
    save_data()
    await interaction.response.send_message("🧹 Lista de sorteio limpa com sucesso!")

# 🕒 Gerar timestamp global
@bot.tree.command(name="timestamp", description="Gera um horário global para eventos")
@app_commands.describe(date="DD/MM/AAAA (opcional)", time="HH:MM (24h)")
async def timestamp(interaction: discord.Interaction, time: str, date: str = None):
    try:
        now = datetime.now()
        if date:
            d, m, y = map(int, date.split("/"))
        else:
            d, m, y = now.day, now.month, now.year
        h, mn = map(int, time.split(":"))
        dt = datetime(y, m, d, h, mn, tzinfo=timezone.utc)
        ts = int(dt.timestamp())
        await interaction.response.send_message(
            f"🕒 **Tempo Global:** <t:{ts}:F>\n⏰ **Tempo Relativo:** <t:{ts}:R>\n\nUse em mensagens:\n`t:{ts}:F` ou `t:{ts}:R`"
        )
    except Exception:
        await interaction.response.send_message("⚠️ Formato inválido! Use `/timestamp time:19:30 date:14/10/2025`")

# 🏓 Ping
@bot.tree.command(name="ping", description="Mostra a latência do bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latência: `{latency}ms`",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Bovary Club Society")
    await interaction.response.send_message(embed=embed)

# ===================== 👀 MONITOR DE ATIVIDADES ===================== #

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🟢 **{member}** entrou no servidor! (ID: `{member.id}`)")

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🔴 **{member}** saiu do servidor.")

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        content = message.content or "[sem texto]"
        await channel.send(
            f"🗑️ Mensagem apagada em {message.channel.mention}\n"
            f"👤 Autor: {message.author}\n💬 Conteúdo: {content}"
        )

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(
            f"✏️ Mensagem editada em {before.channel.mention}\n"
            f"👤 Autor: {before.author}\n"
            f"📄 Antes: {before.content}\n"
            f"📄 Depois: {after.content}"
        )

@bot.event
async def on_guild_channel_create(channel):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🆕 Canal criado: **{channel.name}** ({channel.mention})")

@bot.event
async def on_guild_channel_delete(channel):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🗑️ Canal apagado: **{channel.name}**")

# ===================== EVENTOS ===================== #

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("em Bovary Club Society 🏎️"))
    load_data()
    try:
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} está online com {len(synced)} comandos slash!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

# 🟢 Manter ativo
if __name__ == "__main__":
    keep_alive()
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ ERRO: TOKEN não encontrado. Configure no painel do Replit!")
