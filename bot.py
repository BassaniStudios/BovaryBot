from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import random
from datetime import datetime, timezone

# 🟢 Keep the bot alive (Flask server)
from keep_alive import keep_alive

# 🔑 Bot token
TOKEN = os.getenv("TOKEN")

# ✋ Auto reaction emojis
AUTO_REACTIONS = ["❤️", "🔥", "💯", "💥", "💕", "💎", "🎊", "🎉", "🎀"]

# 💬 Channels where the bot reacts automatically
CHANNEL_IDS = [
    1384173879295213689, 1384174586345816134, 1424515140660760647,
    1424515636524220516, 1384173136853078038, 1384173136853078037,
    1424434022058033242, 1384173137071177753, 1424509207172087849,
    1424586421599076473
]

LOG_CHANNEL_ID = 1384173137985540230  # Log channel

# ⚙️ Bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 🤖 Bot creation
bot = commands.Bot(command_prefix="|", intents=intents)

# ===================== 🎟️ GIVEAWAY SYSTEM ===================== #

DATA_FILE = "giveaway.json"
participants = {}

# 🔄 Load existing data
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

# 💾 Save data
def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, indent=4, ensure_ascii=False)

# ➕ Add participant
@bot.tree.command(name="add", description="Add a person to the giveaway list (1 entry at a time)")
@app_commands.describe(name="Name of the person to participate in the giveaway")
async def add(interaction: discord.Interaction, name: str):
    name = name.strip().title()
    participants[name] = participants.get(name, 0) + 1
    save_data()
    await interaction.response.send_message(f"✅ **{name}** now has **{participants[name]}** entry(ies) in the giveaway!")

# ✏️ Edit participant name
@bot.tree.command(name="edit_name", description="Edit an existing participant's name in the list")
@app_commands.describe(old="Current name in the list", new="New name to replace with")
async def edit_name(interaction: discord.Interaction, old: str, new: str):
    old = old.strip().title()
    new = new.strip().title()

    if old not in participants:
        await interaction.response.send_message(f"⚠️ The name **{old}** was not found in the list!")
        return

    participants[new] = participants.pop(old)
    save_data()
    await interaction.response.send_message(f"✏️ The participant **{old}** has been renamed to **{new}** successfully!")

# ➖ Remove an entry
@bot.tree.command(name="remove_entry", description="Remove one entry from a participant (removes completely if reaches zero)")
@app_commands.describe(name="Name of the person to lose one entry")
async def remove_entry(interaction: discord.Interaction, name: str):
    name = name.strip().title()

    if name not in participants:
        await interaction.response.send_message(f"⚠️ The name **{name}** is not in the list!")
        return

    participants[name] -= 1
    if participants[name] <= 0:
        del participants[name]
        await interaction.response.send_message(f"🗑️ **{name}** has been completely removed from the list (0 entries left).")
    else:
        await interaction.response.send_message(f"➖ One entry removed from **{name}**. Now has **{participants[name]}** entry(ies).")

    save_data()

# 📋 Show participant list
@bot.tree.command(name="list", description="Show the current list of participants and their entries")
async def list_command(interaction: discord.Interaction):
    if not participants:
        await interaction.response.send_message("⚠️ The list is currently empty!")
        return
    formatted_list = "\n".join([f"{i+1}. **{name}** — {count} entry(ies)" for i, (name, count) in enumerate(participants.items())])
    await interaction.response.send_message(f"📝 **Participant List:**\n{formatted_list}")

# 🎲 Run giveaway (admin only)
@bot.tree.command(name="draw", description="Run the giveaway considering each participant's number of entries (admin only)")
async def draw(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 You don't have permission to use this command (admin only).", ephemeral=True)
        return

    if not participants:
        await interaction.response.send_message("⚠️ There are no participants to draw from!")
        return

    pool = []
    for name, count in participants.items():
        pool.extend([name] * count)

    winner = random.choice(pool)
    formatted_list = "\n".join([f"{i+1}. **{name}** — {count} entry(ies)" for i, (name, count) in enumerate(participants.items())])

    await interaction.response.send_message(
        f"🎉 **GIVEAWAY RESULT!** 🎉\n\n📝 **Participant List:**\n{formatted_list}\n\n🏆 **Winner:** **{winner}**! 🎊"
    )

    participants.clear()
    save_data()

# 🧹 Clear list (admin only)
@bot.tree.command(name="clear_list", description="Clear the current list of participants (admin only)")
async def clear_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 You don't have permission to use this command (admin only).", ephemeral=True)
        return

    if not participants:
        await interaction.response.send_message("⚠️ The list is already empty!")
        return

    participants.clear()
    save_data()
    await interaction.response.send_message("🧹 The giveaway list has been successfully cleared!")

# 🕒 Create a global timestamp
@bot.tree.command(name="timestamp", description="Generate a global time visible correctly across timezones")
@app_commands.describe(
    date="Date in DD/MM/YYYY format (optional, for future events)",
    time="Time in HH:MM format (24h)"
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
        timestamp = int(dt.timestamp())

        await interaction.response.send_message(
            f"🕒 **Global Time:** <t:{timestamp}:F>\n"
            f"⏰ **Relative Time:** <t:{timestamp}:R>\n\n"
            f"🧩 Use this in future messages:\n"
            f"`<t:{timestamp}:F>` or `<t:{timestamp}:R>`"
        )
    except Exception as e:
        await interaction.response.send_message("⚠️ Use the correct format: `/timestamp time:19:30 date:14/10/2025`", ephemeral=True)
        print(e)

# ===================== 🏓 PING COMMAND ===================== #

@bot.tree.command(name="ping", description="Shows the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"**Latency:** `{latency}ms`",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Bovary Club Society")
    await interaction.response.send_message(embed=embed)

# ===================== 🔧 EVENTS AND SETUP ===================== #

@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Game("in Bovary Club Society 🏎️"),
        status=discord.Status.online
    )
    load_data()
    try:
        synced = await bot.tree.sync()
        print(f"✅ {bot.user} is online with {len(synced)} synced slash commands!")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

# 🟢 Keep bot alive
keep_alive()
bot.run(TOKEN)
