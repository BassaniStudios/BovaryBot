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
        await interaction.response.send_message(
            "Select **month**, **day** and optional **year** below.",
            view=RegisterView(self.cog, interaction.user.id, mode="register"),
            ephemeral=True,
        )

    @discord.ui.button(label="✏️ Edit mine", style=discord.ButtonStyle.secondary, custom_id="bday_edit", row=0)
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        entry = self.cog.get_user(interaction.user.id)
        if not entry:
            await interaction.response.send_message(
                "You have no birthday registered yet. Use **Register**.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Current: **{entry.get('month')}/{entry.get('day')}**"
            + (f"/{entry.get('year')}" if entry.get("year") else "")
            + f" · Sign: {entry.get('sign') or '—'}\nPick new values:",
            view=RegisterView(self.cog, interaction.user.id, mode="edit"),
            ephemeral=True,
        )

    @discord.ui.button(label="♈ Zodiac sign", style=discord.ButtonStyle.secondary, custom_id="bday_sign", row=1)
    async def sign_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choose your zodiac sign:",
            view=SignView(self.cog, interaction.user.id),
            ephemeral=True,
        )


class MonthSelect(discord.ui.Select):
    def __init__(self, parent: "RegisterView"):
        self.parent_view = parent
        options = [discord.SelectOption(label=name, value=val) for val, name in MONTHS]
        super().__init__(placeholder="Month", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.month = int(self.values[0])
        await interaction.response.defer()


class DaySelect(discord.ui.Select):
    def __init__(self, parent: "RegisterView"):
        self.parent_view = parent
        options = [discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 32)]
        super().__init__(placeholder="Day", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.day = int(self.values[0])
        await interaction.response.defer()


class YearSelect(discord.ui.Select):
    def __init__(self, parent: "RegisterView"):
        self.parent_view = parent
        year_now = datetime.now(SERVER_TZ).year
        years = list(range(year_now - 13, year_now - 70, -1))  # common adult range
        options = [discord.SelectOption(label="Prefer not to say", value="0")]
        options += [discord.SelectOption(label=str(y), value=str(y)) for y in years[:24]]
        super().__init__(placeholder="Year (optional)", min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        v = int(self.values[0])
        self.parent_view.year = v if v > 0 else None
        await interaction.response.defer()


class RegisterView(discord.ui.View):
    def __init__(self, cog: "Birthdays", user_id: int, mode: str = "register"):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.mode = mode
        self.month: Optional[int] = None
        self.day: Optional[int] = None
        self.year: Optional[int] = None
        self.add_item(MonthSelect(self))
        self.add_item(DaySelect(self))
        self.add_item(YearSelect(self))

    @discord.ui.button(label="✅ Save", style=discord.ButtonStyle.success, row=3)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This form is not yours.", ephemeral=True)
            return
        if not self.month or not self.day:
            await interaction.response.send_message("Select **month** and **day** first.", ephemeral=True)
            return
        # basic validation
        try:
            if self.year:
                date(self.year, self.month, self.day)
            else:
                date(2000, self.month, self.day)  # leap-safe check for day
        except ValueError:
            await interaction.response.send_message("Invalid date (e.g. 31 February).", ephemeral=True)
            return
        sign = _zodiac_from_md(self.month, self.day)
        self.cog.set_user(
            self.user_id,
            month=self.month,
            day=self.day,
            year=self.year,
            sign=sign,
        )
        y = f"/{self.year}" if self.year else ""
        await interaction.response.send_message(
            f"✅ Saved: **{self.month:02d}/{self.day:02d}{y}** · {sign}",
            ephemeral=True,
        )
        self.stop()


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
                "📝 **Register** — pick month / day / year from menus\n"
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
