from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timezone
from keep_alive import keep_alive

TOKEN = os.getenv("TOKEN")

# Auto reactions
AUTO_REACTIONS = ["❤️", "🔥", "💯", "💥", "🎀"]

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

# Logs
LOG_CHANNEL_ID = 1441663299065217114
MESSAGE_LOG_CHANNEL_ID = 1432715549116207248
IGNORE_CHANNEL_ID = 1384173137985540233

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="|", intents=intents)


# =============== TIMESTAMP ===============
@bot.tree.command(name="timestamp", description="Generates a global event time")
@app_commands.describe(date="DD/MM/YYYY", time="HH:MM")
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
        await interaction.response.send_message("⚠️ Format error. Use `DD/MM/YYYY` and `HH:MM`.")


# =============== PING ===============
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


# =============== INFO ===============
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


# =============== DELETE MESSAGE ===============
@bot.tree.command(name="apagar", description="Apaga mensagem pelo ID anonimamente")
@app_commands.describe(canal="Canal", mensagem_id="ID da mensagem")
async def apagar(interaction, canal: discord.TextChannel, mensagem_id: str):

    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(
            "🚫 Você não tem permissão.", ephemeral=True
        )

    try:
        mensagem = await canal.fetch_message(int(mensagem_id))
        await mensagem.delete()

        await interaction.response.send_message("✅ Mensagem apagada.", ephemeral=True)

        log = bot.get_channel(MESSAGE_LOG_CHANNEL_ID)
        if log:
            embed = discord.Embed(
                title="🧹 Mensagem apagada via comando",
                description=f"Canal: {canal.mention}\nID: `{mensagem_id}`",
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Ação anônima")
            await log.send(embed=embed)

    except discord.NotFound:
        await interaction.response.send_message("⚠️ Mensagem não encontrada.", ephemeral=True)


# =============== AUTO REACTIONS ===============
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
                e.type in ["image", "video", "gifv"]
                or (e.thumbnail and e.thumbnail.url)
                for e in message.embeds
            )

        if has_media:
            for emoji in AUTO_REACTIONS:
                try:
                    await message.add_reaction(emoji)
                except:
                    pass

    await bot.process_commands(message)


# =============== LOGS ===============
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🟢 **{member}** entrou! (ID: `{member.id}`)")


@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🔴 **{member}** saiu.")


@bot.event
async def on_message_delete(message):
    if message.author.bot or message.channel.id == IGNORE_CHANNEL_ID:
        return

    log = bot.get_channel(MESSAGE_LOG_CHANNEL_ID)
    if log:
        content = message.content or "[no text]"
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Channel", value=message.channel.mention)
        embed.add_field(name="Author", value=str(message.author))
        embed.add_field(name="Content", value=content)
        await log.send(embed=embed)


# =============== HELP PANEL ===============
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Moderação 🧹", style=discord.ButtonStyle.red)
    async def mod_button(self, interaction, button):
        embed = discord.Embed(
            title="🧹 Moderação",
            description="Comandos administrativos",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Comandos:",
            value="`/apagar <canal> <id>`\n`/timestamp`"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Utilidades ⚙️", style=discord.ButtonStyle.green)
    async def util_button(self, interaction, button):
        embed = discord.Embed(
            title="⚙️ Utilidades",
            description="Comandos úteis",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Comandos:",
            value="`/ping`\n`/timestamp`"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Voltar ⬅️", style=discord.ButtonStyle.grey)
    async def back_button(self, interaction, button):
        embed = discord.Embed(
            title="📘 Painel de Comandos — Bovary Bot",
            description="Escolha uma categoria:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=self)


@bot.tree.command(name="help", description="Mostra o painel de comandos")
async def help_command(interaction):
    embed = discord.Embed(
        title="📘 Painel de Comandos — Bovary Bot",
        description="Escolha uma categoria:",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=interaction.client.user.avatar.url)
    await interaction.response.send_message(embed=embed, view=HelpView())


# =============== INVITE VIEW (COOLDOWN 5 MIN + MENTION ROLE) ===============

INVITE_COOLDOWN_SECONDS = 5 * 60   # 5 minutos
STAFF_LOG_CHANNEL = 1441663299065217114  # canal onde staff recebe pedidos
CREW_LEADER_ROLE_ID = 1384173136177791048  # ID do cargo 『👑』Crew Leaders

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

        # Atualiza o horário da última solicitação
        last_invite_request[user.id] = now

        # Resposta para o usuário (ephemeral)
        await interaction.response.send_message(
            "✅ Your invite request has been sent to the staff!",
            ephemeral=True
        )

        # Envia para o canal da staff
        channel = interaction.client.get_channel(STAFF_LOG_CHANNEL)
        guild = interaction.guild

        # pega cargo de Crew Leaders
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

            # 🔥 AQUI está a mensagem do jeito que você pediu:
            message_text = (
                f"✨ **New announcement request!**\n"
                f"{crew_leader_role.mention if crew_leader_role else ''}, "
                f"**{user.display_name}** has requested a broadcast."
            )

            await channel.send(
                content=message_text,
                embed=embed
            )


# =============== INVITE PANEL (ÚNICA VERSÃO LIMPA) ===============
REQUIRED_INVITE_CHANNEL = 1444094610157600859

@bot.tree.command(name="invitepanel", description="Sends the official invite panel.")
async def invitepanel(interaction):

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
            "⏳ *Cooldown: 2 hours*"
        ),
        color=discord.Color.from_rgb(80,120,255)
    )

    embed.set_image(
        url="https://cdn.discordapp.com/attachments/1427794118440124567/1444131435106664469/Ekipa-w-GTA-Online-1280x720.jpg"
    )

    embed.set_thumbnail(url=interaction.client.user.avatar.url)

    embed.set_footer(
        text="Bovary Club Society • Premium Invite System",
        icon_url=interaction.client.user.avatar.url
    )

    await interaction.channel.send(embed=embed, view=InviteView())
    await interaction.response.send_message("✅ Panel sent!", ephemeral=True)


# =============== READY ===============
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("at Bovary Club Society 🏎️"))
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")


# =============== RUN ===============
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)

