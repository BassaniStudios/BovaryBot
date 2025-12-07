from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os
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
LOG_CHANNEL_ID = 1441663299065217114         # Join/leave/channel logs
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


# ===================== 🕒 TIMESTAMP ===================== #

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
            f"🕒 **Global Time:** <t:{ts}:F>\n"
            f"⏰ **Relative Time:** <t:{ts}:R>\n\n"
            f"Use in messages:\n`t:{ts}:F` or `t:{ts}:R`"
        )
    except Exception:
        await interaction.response.send_message("⚠️ Invalid format! Use `/timestamp time:19:30 date:14/10/2025`")


# ===================== 🏓 PING ===================== #

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

        # Check attachments
        if message.attachments:
            has_media = any(
                a.content_type and a.content_type.startswith(("image/", "video/"))
                for a in message.attachments
            )

        # Check embeds
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


# =========================================================
# 📨 REQUEST INVITE SYSTEM (COOLDOWN + STAFF NOTIFICATION)
# =========================================================

INVITE_COOLDOWN_SECONDS = 5 * 60   # 5 minutos
STAFF_LOG_CHANNEL = 1444186478157500508  # 📩┃request-invitations
CREW_LEADER_ROLE_ID = 1444179094983020605  # ID do cargo Host - invitations

last_invite_request = {}  # cooldown por usuário


class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Invite ✉️", style=discord.ButtonStyle.blurple)
    async def request_invite(self, interaction: discord.Interaction, button):

        user = interaction.user
        now = datetime.now(timezone.utc)

        # --- VERIFICA COOLDOWN ---
        if user.id in last_invite_request:
            diff = (now - last_invite_request[user.id]).total_seconds()
            remaining = INVITE_COOLDOWN_SECONDS - diff

            if remaining > 0:
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)

                return await interaction.response.send_message(
                    f"⏳ You must wait **{minutes}m {seconds}s** before requesting another invite.",
                    ephemeral=True
                )

        last_invite_request[user.id] = now

        await interaction.response.send_message(
            "✅ Your invite request has been sent to the staff!",
            ephemeral=True
        )

        channel = interaction.client.get_channel(STAFF_LOG_CHANNEL)
        guild = interaction.guild

        crew_leader_role = guild.get_role(CREW_LEADER_ROLE_ID)

        if channel:
            embed = discord.Embed(
                title="📨 New Invite Request",
                description=(
                    f"👤 **User:** {user.mention}\n"
                    f"⏰ **Time:** <t:{int(now.timestamp())}:R>"
                ),
                color=discord.Color.blue(),
                timestamp=now
            )
            embed.set_footer(text="Bovary Club • Invite System")

            message_text = (
                f"✨ **New announcement request!**\n"
                f"{crew_leader_role.mention if crew_leader_role else ''}, "
                f"**{user.display_name}** has requested a broadcast."
            )

            await channel.send(content=message_text, embed=embed)


# ============================
# 📌 /invitepanel COMMAND
# ============================

REQUIRED_INVITE_CHANNEL = 1444094610157600859

@bot.tree.command(name="invitepanel", description="Sends the official invite panel.")
async def invitepanel(interaction: discord.Interaction):

    if interaction.channel_id != REQUIRED_INVITE_CHANNEL:
        return await interaction.response.send_message(
            f"❌ Use this command only in <#{REQUIRED_INVITE_CHANNEL}>.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="🚗 **Bovary Club – Invitation Request Panel**",
        description=(
            "Click the button below to request an invite.\n"
            "Your request will be forwarded automatically to the staff.\n\n"
            "⏳ *Cooldown: 5 minutes*"
        ),
        color=discord.Color.from_rgb(80, 120, 255)
    )

    embed.set_image(url="https://cdn.discordapp.com/attachments/1427794118440124567/1444131435106664469/Ekipa-w-GTA-Online-1280x720.jpg")
    embed.set_thumbnail(url=interaction.client.user.avatar.url)
    embed.set_footer(
        text="Bovary Club Society • Premium Invite System",
        icon_url=interaction.client.user.avatar.url
    )

    await interaction.channel.send(embed=embed, view=InviteView())
    await interaction.response.send_message("✅ Panel sent!", ephemeral=True)

    temp_msg = await interaction.channel.send(
        f"📨 {interaction.user.mention} has requested an invite!"
    )
    await temp_msg.delete(delay=300)


# ===================== EVENTS ===================== #

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("at Bovary Club Society 🏎️"))
    try:
        bot.add_view(InviteView())  # 🔥 registra a View dos botões permanentes
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
