from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os

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

# 🚀 Quando o bot iniciar
@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Game("in Bovary Club Society 🏎️"),
        status=discord.Status.online
    )
    try:
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} está online com {len(synced)} comandos de barra sincronizados!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

# 💫 Reações automáticas
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id in CHANNEL_IDS:
        for emoji in AUTO_REACTIONS:
            try:
                await message.add_reaction(emoji)
            except discord.errors.HTTPException:
                pass

    await bot.process_commands(message)

# ⚡ Comando de barra (/ping)
@bot.tree.command(name="ping", description="Verifica se o bot está ativo")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! Estou ativo!")

# 🎬 Enviar vídeo local
@bot.command(name="enviar")
async def enviar(ctx, caminho: str):
    """Envia um vídeo local para o canal atual"""
    try:
        await ctx.send("📤 Enviando vídeo...")
        await ctx.channel.send(file=discord.File(caminho))
        await ctx.send("✅ Vídeo enviado com sucesso!")
    except Exception as e:
        await ctx.send(f"❌ Erro ao enviar o vídeo: `{e}`")

@bot.tree.command(name="enviar", description="Envia um vídeo local para o canal")
@app_commands.describe(caminho="Caminho completo do arquivo de vídeo")
async def enviar_slash(interaction: discord.Interaction, caminho: str):
    try:
        await interaction.response.send_message("📤 Enviando vídeo...")
        await interaction.channel.send(file=discord.File(caminho))
        await interaction.followup.send("✅ Vídeo enviado com sucesso!")
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao enviar o vídeo: `{e}`")

# 🎨 Cores temáticas do Bovary Club
COR_ENTRADA = 0xFFD700
COR_SAIDA = 0xFF0000
COR_EDIT = 0xE67E22
COR_DELETE = 0x2C2F33

# 🗑️ Log: mensagem apagada
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    embed = discord.Embed(
        title="🗑️ Mensagem Apagada",
        description=f"💬 **Mensagem de {message.author.mention} foi removida.**",
        color=COR_DELETE
    )
    embed.add_field(name="📍 Canal", value=message.channel.mention, inline=True)
    embed.add_field(name="📅 Horário", value=message.created_at.strftime('%d/%m %H:%M'), inline=True)
    embed.add_field(name="🧾 Conteúdo", value=message.content or "*[Sem texto]*", inline=False)
    embed.set_footer(text="Bovary Club Society — Log Automático", icon_url=bot.user.avatar.url)
    await log_channel.send(embed=embed)

# ✏️ Log: mensagem editada
@bot.event
async def on_message_edit(antes, depois):
    if antes.author.bot or antes.content == depois.content:
        return
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    embed = discord.Embed(
        title="✏️ Mensagem Editada",
        color=COR_EDIT
    )
    embed.add_field(name="👤 Autor", value=antes.author.mention, inline=True)
    embed.add_field(name="📍 Canal", value=antes.channel.mention, inline=True)
    embed.add_field(name="💬 Antes", value=antes.content or "*[Sem texto]*", inline=False)
    embed.add_field(name="💬 Depois", value=depois.content or "*[Sem texto]*", inline=False)
    embed.set_footer(text="Bovary Club Society — Registro de Edição", icon_url=bot.user.avatar.url)
    await log_channel.send(embed=embed)

# 🏎️ Log: novo membro
@bot.event
async def on_member_join(membro):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    embed = discord.Embed(
        title="🏎️ Novo Piloto Chegou!",
        description=f"Bem-vindo(a) ao **Bovary Club Society**, {membro.mention}! 🥂",
        color=COR_ENTRADA
    )
    embed.set_thumbnail(url=membro.avatar.url if membro.avatar else membro.default_avatar.url)
    embed.set_footer(text=f"Conta criada em {membro.created_at.strftime('%d/%m/%Y')}")
    await log_channel.send(embed=embed)

# 🚪 Log: membro saiu
@bot.event
async def on_member_remove(membro):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    embed = discord.Embed(
        title="🚪 Membro Saiu do Clube",
        description=f"{membro.mention} deixou o **Bovary Club Society**.",
        color=COR_SAIDA
    )
    embed.set_thumbnail(url=membro.avatar.url if membro.avatar else membro.default_avatar.url)
    embed.set_footer(text="Esperamos vê-lo nas próximas corridas 🏁")
    await log_channel.send(embed=embed)

# ▶️ Rodar o bot
keep_alive()  # Mantém o bot online (Replit/Render)
bot.run(TOKEN)
