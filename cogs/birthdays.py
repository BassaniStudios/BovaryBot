"""
Sistema de aniversários + signo — painel só com botões/selects (sem slash complicado).
"""
from __future__ import annotations

import logging
from calendar import month_name
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.helpers import make_embed, SERVER_TZ, safe_get_channel
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.birthdays")
FILE = "birthdays.json"

MONTHS = [
    ("1", "January"), ("2", "February"), ("3", "March"), ("4", "April"),
    ("5", "May"), ("6", "June"), ("7", "July"), ("8", "August"),
    ("9", "September"), ("10", "October"), ("11", "November"), ("12", "December"),
]

ZODIAC = [
    "Aries ♈", "Taurus ♉", "Gemini ♊", "Cancer ♋",
    "Leo ♌", "Virgo ♍", "Libra ♎", "Scorpio ♏",
    "Sagittarius ♐", "Capricorn ♑", "Aquarius ♒", "Pisces ♓",
]


def _zodiac_from_md(month: int, day: int) -> str:
    """Approximate Western zodiac from month/day."""
    md = (month, day)
    ranges = [
        ((3, 21), (4, 19), "Aries ♈"),
        ((4, 20), (5, 20), "Taurus ♉"),
        ((5, 21), (6, 20), "Gemini ♊"),
        ((6, 21), (7, 22), "Cancer ♋"),
        ((7, 23), (8, 22), "Leo ♌"),
        ((8, 23), (9, 22), "Virgo ♍"),
        ((9, 23), (10, 22), "Libra ♎"),
        ((10, 23), (11, 21), "Scorpio ♏"),
        ((11, 22), (12, 21), "Sagittarius ♐"),
        ((12, 22), (12, 31), "Capricorn ♑"),
        ((1, 1), (1, 19), "Capricorn ♑"),
        ((1, 20), (2, 18), "Aquarius ♒"),
        ((2, 19), (3, 20), "Pisces ♓"),
    ]
    for (m1, d1), (m2, d2), name in ranges:
        if (month == m1 and day >= d1) or (month == m2 and day <= d2):
            if m1 == m2 or month == m1 or month == m2:
                # handle wrap roughly
                if m1 < m2 and m1 <= month <= m2:
                    if month == m1 and day < d1:
                        continue
                    if month == m2 and day > d2:
                        continue
                    return name
                if m1 > m2:  # Capricorn wrap
                    if month == m1 and day >= d1:
                        return name
                    if month == m2 and day <= d2:
                        return name
    return "—"



class BirthdayPanel(discord.ui.View):
    def __init__(self, cog: "Birthdays"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🎂 Birthdays", style=discord.ButtonStyle.primary, custom_id="bday_list", row=0)
    async def list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_list(interaction)

    @discord.ui.button(label="📝 Register", style=discord.ButtonStyle.success, custom_id="bday_reg", row=0)
    async def reg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayModal(self.cog, interaction.user.id, mode="register"))

    @discord.ui.button(label="✏️ Edit mine", style=discord.ButtonStyle.secondary, custom_id="bday_edit", row=0)
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        entry = self.cog.get_user(interaction.user.id)
        if not entry:
            await interaction.response.send_message(
                "You have no birthday registered yet. Use **Register**.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(BirthdayModal(self.cog, interaction.user.id, mode="edit", entry=entry))

    @discord.ui.button(label="♈ Zodiac sign", style=discord.ButtonStyle.secondary, custom_id="bday_sign", row=1)
    async def sign_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choose your zodiac sign:",
            view=SignView(self.cog, interaction.user.id),
            ephemeral=True,
        )


class BirthdayModal(discord.ui.Modal, title="🎂 Register birthday"):
    """Private Discord modal for an exact birthday: English month + day only."""

    month = discord.ui.TextInput(
        label="Month",
        placeholder="e.g. September",
        required=True,
        max_length=12,
    )
    day = discord.ui.TextInput(
        label="Day",
        placeholder="e.g. 12",
        required=True,
        min_length=1,
        max_length=2,
    )

    def __init__(self, cog: "Birthdays", user_id: int, mode: str = "register", entry: Optional[Dict] = None):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.mode = mode
        self.entry = entry or {}

        if self.entry:
            month = int(self.entry.get("month", 1))
            day = int(self.entry.get("day", 1))
            self.month.default = MONTHS[month - 1][1]
            self.day.default = str(day)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This form is not yours.", ephemeral=True)
            return

        month_text = self.month.value.strip().lower()
        month_map = {name.lower(): int(value) for value, name in MONTHS}
        # Also accept common English abbreviations, while showing full names in the UI.
        aliases = {
            "jan": "january", "feb": "february", "mar": "march", "apr": "april",
            "may": "may", "jun": "june", "jul": "july", "aug": "august",
            "sep": "september", "sept": "september", "oct": "october",
            "nov": "november", "dec": "december",
        }
        month_text = aliases.get(month_text, month_text)
        month = month_map.get(month_text)

        try:
            day = int(self.day.value.strip())
        except ValueError:
            day = 0

        if month is None:
            await interaction.response.send_message(
                "❌ Invalid month. Please use an English month name, e.g. **September**.",
                ephemeral=True,
            )
            return

        try:
            # 2000 makes February 29 a valid birthday while we only store month/day.
            date(2000, month, day)
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid day for that month. Please enter a real date, e.g. **September 12**.",
                ephemeral=True,
            )
            return

        sign = _zodiac_from_md(month, day)
        self.cog.set_user(
            self.user_id,
            month=month,
            day=day,
            year=None,
            sign=sign,
        )

        month_name = MONTHS[month - 1][1]
        await interaction.response.send_message(
            f"✅ Birthday saved: **{month_name} {day}** · {sign}",
            ephemeral=True,
        )


class SignSelect(discord.ui.Select):
    def __init__(self, parent: "SignView"):
        self.parent_view = parent
        options = [discord.SelectOption(label=z, value=z) for z in ZODIAC]
        super().__init__(placeholder="Zodiac sign", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.sign = self.values[0]
        await interaction.response.defer()


class SignView(discord.ui.View):
    def __init__(self, cog: "Birthdays", user_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.sign: Optional[str] = None
        self.add_item(SignSelect(self))

    @discord.ui.button(label="✅ Save sign", style=discord.ButtonStyle.success)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your form.", ephemeral=True)
            return
        if not self.sign:
            await interaction.response.send_message("Pick a sign first.", ephemeral=True)
            return
        entry = self.cog.get_user(self.user_id) or {}
        entry["sign"] = self.sign
        entry["user_id"] = self.user_id
        self.cog.data.setdefault("users", {})[str(self.user_id)] = entry
        self.cog._save()
        await interaction.response.send_message(f"✅ Sign saved: **{self.sign}**", ephemeral=True)
        self.stop()


class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(FILE, {"users": {}, "panel_channel_id": None, "announce_channel_id": None})
        self.daily.start()

    def cog_unload(self):
        self.daily.cancel()
        self._save()

    def _save(self):
        save_json(FILE, self.data)

    def get_user(self, user_id: int) -> Optional[Dict]:
        return self.data.get("users", {}).get(str(user_id))

    def set_user(self, user_id: int, *, month: int, day: int, year: Optional[int], sign: str):
        self.data.setdefault("users", {})[str(user_id)] = {
            "user_id": user_id,
            "month": month,
            "day": day,
            "year": year,
            "sign": sign,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    async def show_list(self, interaction: discord.Interaction):
        users = self.data.get("users") or {}
        if not users:
            await interaction.response.send_message("No birthdays registered yet.", ephemeral=True)
            return
        # sort by month, day
        items = sorted(users.values(), key=lambda u: (u.get("month", 99), u.get("day", 99)))
        lines = []
        for u in items[:40]:
            uid = u.get("user_id")
            m, d = u.get("month"), u.get("day")
            y = u.get("year")
            sign = u.get("sign") or ""
            date_s = f"{m:02d}/{d:02d}" + (f"/{y}" if y else "")
            lines.append(f"• <@{uid}> — **{date_s}** {sign}")
        embed = make_embed(
            title="🎂 Registered birthdays",
            description="\n".join(lines),
            color=discord.Color.from_rgb(255, 120, 180),
        )
        embed.set_footer(text=f"{len(items)} total · Bova's Bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(hours=1)
    async def daily(self):
        now = datetime.now(SERVER_TZ)
        if now.hour != 9:
            return
        today_key = now.strftime("%Y-%m-%d")
        if self.data.get("last_announce") == today_key:
            return
        m, d = now.month, now.day
        hits = [
            u for u in (self.data.get("users") or {}).values()
            if u.get("month") == m and u.get("day") == d
        ]
        if not hits:
            self.data["last_announce"] = today_key
            self._save()
            return
        ch_id = self.data.get("announce_channel_id") or self.bot.config.get("LOG_CHANNEL_ID")
        ch = safe_get_channel(self.bot, ch_id) if ch_id else None
        if not ch:
            return
        mentions = " ".join(f"<@{u['user_id']}>" for u in hits)
        embed = discord.Embed(
            title="🎉 Happy Birthday!",
            description=f"Today we celebrate:\n{mentions}\n\nHave an amazing day! 🎂✨",
            color=discord.Color.from_rgb(255, 100, 160),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_image(url="https://ik.imagekit.io/BassaniStudios/bovary%20pic%20meet/setembro/bova%20logo%20?updatedAt=1788801048503")
        embed.set_footer(text="Bova's Bot · Birthday system")
        try:
            await ch.send(content=mentions, embed=embed)
            self.data["last_announce"] = today_key
            self._save()
        except Exception:
            logger.exception("Birthday announce failed")

    @daily.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="birthday_panel", description="Post the easy birthday panel (buttons only)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def birthday_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎂 Birthdays · Bovary Club",
            description=(
                "**No slash typing needed.**\n\n"
                "🎂 **Birthdays** — list registered dates\n"
                "📝 **Register** — enter your exact birthday (English month + day)\n"
                "✏️ **Edit mine** — change only your date\n"
                "♈ **Zodiac sign** — set or override your sign\n"
            ),
            color=discord.Color.from_rgb(255, 120, 180),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None)
        embed.set_footer(text="Bova's Bot · Easy panel")
        view = BirthdayPanel(self)
        await interaction.response.send_message(embed=embed, view=view)
        self.data["panel_channel_id"] = interaction.channel_id
        self._save()
        self.bot.add_view(view)

    @app_commands.command(name="birthday_announce_channel", description="Channel for daily birthday announcements")
    @app_commands.checks.has_permissions(administrator=True)
    async def birthday_announce_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.data["announce_channel_id"] = channel.id
        self._save()
        await interaction.response.send_message(f"✅ Announcements → {channel.mention}", ephemeral=True)

    async def cog_load(self):
        self.bot.add_view(BirthdayPanel(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
