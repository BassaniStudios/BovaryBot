from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import random
from datetime import datetime, timezone
from keep_alive import keep_alive  # 🔥 Keeps bot alive

# 🔑 Token
TOKEN = os.getenv("TOKEN")

# ✋ Auto-reaction emojis
AUTO_REACTIONS = ["❤️", "🔥", "💯", "💥", "🎀"]

# 💬 Channels where bot reacts automatically
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

# 📜 Log channels
LOG_CHANNEL_ID = 1424436722984423529         # Join/leave/channel logs
MESSAGE_LOG_CHANNEL_ID = 1432715549116207248 # Message delete/edit logs

# 🚫 Channel ignored for message logs
IGNORE_CHANNEL_ID = 1384173137985540233

# ⚙️ Bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# 🤖 Bot initialization
bot = commands.Bot(command_prefix="|", intents=intents)

# ===================== 🎟️ GIVEAWAY SYSTEM ===================== #

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

# ➕ Add participant
@bot.tree.command(name="add", description="Adds a person to the giveaway (1 entry per time)")
@app_commands.describe(name="Name of the person joining")
async def add(interaction: discord.Interaction, name: str):
    name = name.strip().title()
    participants[name] = participants.get(name, 0) + 1
    save_data()
    await interaction.response.send_message(f"✅ **{name}** now has **{participants[name]}** entry(ies)!")

# ✏️ Edit name
@bot.tree.command(name="edit_name", description="Edits a participant’s name")
@app_commands.describe(old="Current name", new="New name")
async def edit_name(interaction: discord.Interaction, old: str, new: str):
    old, new = old.strip().title(), new.strip().title()
    if old not in participants:
        await interaction.response.send_message(f"⚠️ **{old}** not found!")
        return
    participants[new] = participants.pop(old)
    save_data()
    await interaction.response.send_message(f"✏️ **{old}** renamed to **{new}** successfully!")

# ➖ Remove entry
@bot.tree.command(name="remove_entry", description="Removes one entry from a participant")
@app_commands.describe(name="Name of the person")
async def remove_entry(interaction: discord.Interaction, name: str):
    name = name.strip().title()
    if name not in participants:
        await interaction.response.send_message(f"⚠️ **{name}** not found!")
        return
    participants[name] -= 1
    if participants[name] <= 0:
        del participants[name]
        await interaction.response.send_message(f"🗑️ **{name}** completely removed!")
    else:
        await interaction.response.send_message(f"➖ One entry removed from **{name}**. Now has **{participants[name]}** entry(ies).")
    save_data()

# 📋 List participants
@bot.tree.command(name="list", description="Shows all participants")
async def list_command(interaction: discord.Interaction):
    if not participants:
        await interaction.response.send_message("⚠️ No participants yet!")
        return
    formatted = "\n".join([f"{i+1}. **{n}** — {c} entry(ies)" for i, (n, c) in enumerate(participants.items())])
    await interaction.response.send_message(f"📝 **Participants:**\n{formatted}")

# 🎲 Draw winner
@bot.tree.command(name="draw", description="Draws a winner (admin only)")
async def draw(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Admins only.", ephemeral=True)
        return
    if not participants:
        await interaction.response.send_message("⚠️ No participants to draw from!")
        return
    pool = [n for n, c in participants.items() for _ in range(c)]
    winner = random.choice(pool)
    await interaction.response.send_message(f"🎉 **Giveaway Result!** 🎉\n🏆 Winner: **{winner}**! 🎊")
    participants.clear()
    save_data()

# 🧹 Clear list
@bot.tree.command(name="clear_list", description="Clears the participant list (admin only)")
async def clear_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Admins only.", ephemeral=True)
        return
    participants.clear()
    save_data()
    await interaction.response.send_message("🧹 Giveaway list cleared!")

# 🕒 Timestamp generator
@bot.tree.command(name="timestamp", description="Generates a global event time")
@app_commands.describe(date="DD/MM/YYYY (optional)", time="HH:MM (24h)")
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
            f"🕒 **Global Time:** <t:{ts}:F>\n⏰ **Relative Time:** <t:{ts}:R>\n\nUse in messages:\n`t:{ts}:F` or `t:{ts}:R`"
        )
    except Exception:
        await interaction.response.send_message("⚠️ Invalid format! Use `/timestamp time:19:30 date:14/10/2025`")

# 🏓 Ping
@bot.tree.command(name="ping", description="Shows bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: `{latency}ms`",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Bovary Club Society")
    await interaction.response.send_message(embed=embed)

# ===================== ℹ️ INFO COMMAND ===================== #

@bot.tree.command(name="info", description="Mostra informações sobre o bot, servidor e usuário")
async def info(interaction: discord.Interaction):

    bot_user = interaction.client.user
    server = interaction.guild
    user = interaction.user

    embed = discord.Embed(
        title="ℹ️ Informações do Bot",
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_thumbnail(url=bot_user.avatar.url if bot_user.avatar else None)

    embed.add_field(
        name="🤖 Bot",
        value=(
            f"**Nome:** {bot_user.name}\n"
            f"**ID:** `{bot_user.id}`\n"
            f"**Latência:** `{round(bot.latency * 1000)}ms`"
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ Servidor",
        value=(
            f"**Nome:** {server.name}\n"
            f"**ID:** `{server.id}`\n"
            f"**Membros:** `{server.member_count}`"
        ),
        inline=False
    )

    embed.add_field(
        name="👤 Usuário",
        value=(
            f"**Nome:** {user.display_name}\n"
            f"**ID:** `{user.id}`"
        ),
        inline=False
    )

    embed.set_footer(text="Bovary Club Society")

    await interaction.response.send_message(embed=embed)

# ===================== 🧹 DELETE MESSAGE BY ID (ANON) ===================== #

@bot.tree.command(name="apagar", description="Apaga uma mensagem pelo ID (anonimamente)")
@app_commands.describe(
    canal="Canal onde está a mensagem",
    mensagem_id="ID da mensagem que deseja apagar"
)
async def apagar(interaction: discord.Interaction, canal: discord.TextChannel, mensagem_id: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("🚫 Você não tem permissão para apagar mensagens.", ephemeral=True)
        return

    try:
        mensagem = await canal.fetch_message(int(mensagem_id))
        await mensagem.delete()
        await interaction.response.send_message("✅ Mensagem apagada com sucesso!", ephemeral=True)

        msg_log = bot.get_channel(MESSAGE_LOG_CHANNEL_ID)
        if msg_log:
            embed = discord.Embed(
                title="🧹 Mensagem apagada via comando",
                description=f"Canal: {canal.mention}\nID da mensagem: `{mensagem_id}`",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            embed.set_footer(text="Ação executada anonimamente")
            await msg_log.send(embed=embed)

    except discord.NotFound:
        await interaction.response.send_message("⚠️ Mensagem não encontrada.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("🚫 Não tenho permissão para apagar mensagens nesse canal.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ocorreu um erro: `{e}`", ephemeral=True)

# ===================== 💬 AUTO REACTIONS ===================== #

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id in CHANNEL_IDS:
        has_media = False

        if message.attachments:
            has_media = any(
                a.content_type and a.content_type.startswith(("image/", "video/"))
                for a in message.attachments
            )

        if not has_media and message.embeds:
            has_media = any(
                e.type in ["image", "video", "gifv"] or (e.thumbnail and e.thumbnail.url)
                for e in message.embeds
            )

        if has_media:
            for emoji in AUTO_REACTIONS:
                try:
                    await message.add_reaction(emoji)
                except discord.errors.HTTPException:
                    continue

    await bot.process_commands(message)

# ===================== 👀 ACTIVITY MONITOR ===================== #

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🟢 **{member}** joined the server! (ID: `{member.id}`)")

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🔴 **{member}** left the server.")

@bot.event
async def on_message_delete(message):
    if message.author.bot or message.channel.id == IGNORE_CHANNEL_ID:
        return

    msg_log = bot.get_channel(MESSAGE_LOG_CHANNEL_ID)
    if msg_log:
        content = message.content or "[no text]"
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Author", value=str(message.author), inline=True)
        embed.add_field(name="Content", value=content, inline=False)
        if message.author.avatar:
            embed.set_thumbnail(url=message.author.avatar.url)
        embed.set_footer(text="Bova’s bot | Delete log")
        await msg_log.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content or before.channel.id == IGNORE_CHANNEL_ID:
        return

    msg_log = bot.get_channel(MESSAGE_LOG_CHANNEL_ID)
    if msg_log:
        before_content = before.content or "[no text]"
        after_content = after.content or "[no text]"
        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Author", value=str(before.author), inline=True)
        embed.add_field(name="Before", value=before_content, inline=False)
        embed.add_field(name="After", value=after_content, inline=False)
        if before.author.avatar:
            embed.set_thumbnail(url=before.author.avatar.url)
        embed.set_footer(text="Bova’s bot | Edit log")
        await msg_log.send(embed=embed)

@bot.event
async def on_guild_channel_create(channel):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🆕 Channel created: **{channel.name}** ({channel.mention})")

@bot.event
async def on_guild_channel_delete(channel):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🗑️ Channel deleted: **{channel.name}**")

# ==========================================
# 📘 PAINEL DE COMANDOS COM BOTÕES ELEGANTES
# ==========================================

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    # 🎟️ GIVEAWAY BUTTON
    @discord.ui.button(label="Giveaway 🎟️", style=discord.ButtonStyle.blurple)
    async def giveaway_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="🎟️ Sistema de Giveaway",
            description="Comandos relacionados ao sistema de sorteios",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="Comandos:",
            value=(
                "`/add <nome>` — Adiciona 1 entrada\n"
                "`/edit_name <old> <new>` — Renomeia participante\n"
                "`/remove_entry <nome>` — Remove 1 entrada\n"
                "`/list` — Lista participantes\n"
                "`/draw` — Sorteia um vencedor (admin)\n"
                "`/clear_list` — Limpa a lista (admin)"
            ),
            inline=False
        )

        embed.set_footer(text="Bovary Club Society")
        await interaction.response.edit_message(embed=embed, view=self)

    # 🧹 MODERAÇÃO BUTTON
    @discord.ui.button(label="Moderação 🧹", style=discord.ButtonStyle.red)
    async def mod_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="🧹 Moderação",
            description="Comandos administrativos disponíveis no bot",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Comandos:",
            value=(
                "`/apagar <canal> <id>` — Apaga mensagem anonimamente\n"
                "`/timestamp` — Cria horários globais"
            ),
            inline=False
        )
        embed.set_footer(text="Bovary Club Society")

        await interaction.response.edit_message(embed=embed, view=self)

    # ⚙️ UTILIDADE BUTTON
    @discord.ui.button(label="Utilidades ⚙️", style=discord.ButtonStyle.green)
    async def util_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="⚙️ Utilidades",
            description="Comandos gerais e úteis do bot",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Comandos:",
            value=(
                "`/ping` — Mostra a latência\n"
                "`/timestamp` — Horário global"
            ),
            inline=False
        )
        embed.set_footer(text="Bovary Club Society")

        await interaction.response.edit_message(embed=embed, view=self)

    # 🔙 VOLTAR
    @discord.ui.button(label="Voltar ⬅️", style=discord.ButtonStyle.grey)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            title="📘 Painel de Comandos — Bovary Bot",
            description="Escolha uma categoria abaixo:",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Bovary Club Society")

        await interaction.response.edit_message(embed=embed, view=self)

# ============================
# 📌 COMANDO SLASH: /help
# ============================

@bot.tree.command(name="help", description="Mostra o painel de comandos do bot")
async def help_command(interaction: discord.Interaction):

    embed = discord.Embed(
        title="📘 Painel de Comandos — Bovary Bot",
        description="Escolha uma categoria usando os botões abaixo:",
        color=discord.Color.blue()
    )

    embed.set_thumbnail(
        url=interaction.client.user.avatar.url if interaction.client.user.avatar else None
    )
    embed.set_footer(text="Bovary Club Society")

    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view)

# ===================== EVENTS ===================== #

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("at Bovary Club Society 🏎️"))
    load_data()
    try:
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} is online with {len(synced)} slash commands!")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

# ===================== EXECUTION ===================== #

if __name__ == "__main__":
    keep_alive()
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ ERROR: TOKEN not found. Configure it in Replit panel!")
