"""
Bovary Economy — complete economy system for Bova's Bot.
Currency: Bovas coins
Main panel (members): Maze Bank channel
Member responses: Bovary Market channel
Admin panel [LOCKED]: Bank Admin channel
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import load_json, save_json
from utils.helpers import make_embed, SERVER_TZ

logger = logging.getLogger("bovary_bot.economy")

# ── Channel IDs (hardcoded production + env override possible via config) ──
BANK_CHANNEL_ID = 1559720971437350933       # Maze Bank — member panel
MARKET_CHANNEL_ID = 1559721230591066182     # Bovary Market — responses
ADMIN_CHANNEL_ID = 1426755523797057536      # Bank Admin — staff panel

CURRENCY = "Bovas coins"
CURRENCY_EMOJI = "🪙"
COLOR_MAIN = discord.Color.from_rgb(255, 193, 7)      # gold
COLOR_SUCCESS = discord.Color.from_rgb(46, 204, 113)
COLOR_FAIL = discord.Color.from_rgb(231, 76, 60)
COLOR_INFO = discord.Color.from_rgb(52, 152, 219)
COLOR_ADMIN = discord.Color.from_rgb(155, 89, 182)
COLOR_CASINO = discord.Color.from_rgb(212, 175, 55)   # luxurious gold
COLOR_CONSTRUCTION = discord.Color.from_rgb(149, 165, 166)

# ── Default general shop (pets, badges, consumables — cars moved to Benny's) ──
DEFAULT_SHOP: List[Dict[str, Any]] = [
    {"id": "pet_cat", "name": "🐱 Pet Cat", "price": 500, "type": "pet", "desc": "A cute cat that follows you.", "emoji": "🐱"},
    {"id": "pet_dog", "name": "🐶 Loyal Dog", "price": 800, "type": "pet", "desc": "Man's best friend (and Bova's).", "emoji": "🐶"},
    {"id": "pet_dragon", "name": "🐉 Mini Dragon", "price": 5000, "type": "pet", "desc": "A legendary pocket dragon.", "emoji": "🐉"},
    {"id": "pet_fenrir", "name": "🐺 Fenrir Pup", "price": 3500, "type": "pet", "desc": "Pup of the Fenrir Yakuza wolf.", "emoji": "🐺"},
    {"id": "badge_gold", "name": "⚜️ Gold Badge", "price": 3000, "type": "badge", "desc": "Symbol of prestige.", "emoji": "⚜️"},
    {"id": "badge_yakuza", "name": "🩸 Yakuza Badge", "price": 8000, "type": "badge", "desc": "Respect of the Fenrir family.", "emoji": "🩸"},
    {"id": "badge_bova", "name": "👑 Bova Badge", "price": 15000, "type": "badge", "desc": "Official club badge.", "emoji": "👑"},
    {"id": "item_coffee", "name": "☕ Bova's Coffee", "price": 50, "type": "consumable", "desc": "Restores energy (cosmetic).", "emoji": "☕"},
    {"id": "item_chip", "name": "🎰 Casino Chip", "price": 200, "type": "consumable", "desc": "Collectible item.", "emoji": "🎰"},
]

# ── Benny's Original Motor Workshop (cars) ──
BENNYS_SOUTHERN: List[Dict[str, Any]] = [
    {"id": "car_banshee", "name": "🏎️ Banshee", "price": 9000, "type": "car", "desc": "Classic sports car.", "emoji": "🏎️", "dealer": "southern"},
    {"id": "car_infernus", "name": "🔥 Infernus", "price": 14000, "type": "car", "desc": "Italian supercar.", "emoji": "🔥", "dealer": "southern"},
    {"id": "car_cheetah", "name": "🐆 Cheetah", "price": 11000, "type": "car", "desc": "Fast and sleek.", "emoji": "🐆", "dealer": "southern"},
    {"id": "car_green_sabre", "name": "🟢 Green Sabre", "price": 6500, "type": "car", "desc": "Muscle classic.", "emoji": "🟢", "dealer": "southern"},
    {"id": "car_pfister_comet", "name": "☄️ Pfister Comet", "price": 8500, "type": "car", "desc": "German precision.", "emoji": "☄️", "dealer": "southern"},
    {"id": "car_zentorno", "name": "⚡ Zentorno", "price": 22000, "type": "car", "desc": "Hypercar legend.", "emoji": "⚡", "dealer": "southern"},
    {"id": "car_cognoscenti", "name": "🖤 Cognoscenti", "price": 7500, "type": "car", "desc": "Luxury sedan.", "emoji": "🖤", "dealer": "southern"},
]

BENNYS_LEGENDARY: List[Dict[str, Any]] = [
    {"id": "car_kuruma", "name": "🛡️ Karin Kuruma", "price": 18000, "type": "car", "desc": "Armored sports sedan.", "emoji": "🛡️", "dealer": "legendary"},
    {"id": "car_jesterrr", "name": "🏁 JesterRR", "price": 16000, "type": "car", "desc": "Race-ready Jester.", "emoji": "🏁", "dealer": "legendary"},
    {"id": "car_bodhi", "name": "🛻 Bodhi", "price": 5500, "type": "car", "desc": "Off-road beast.", "emoji": "🛻", "dealer": "legendary"},
    {"id": "car_coquette_classic", "name": "🚘 Coquette Classic", "price": 12000, "type": "car", "desc": "Timeless classic.", "emoji": "🚘", "dealer": "legendary"},
]

# ── Warstock Cache & Carry (military) ──
WARSTOCK_ITEMS: List[Dict[str, Any]] = [
    {"id": "mil_rhino", "name": "🛡️ Rhino Tank", "price": 150000, "type": "military", "desc": "Heavy armor tank.", "emoji": "🛡️"},
    {"id": "mil_insurgent", "name": "🚙 Insurgent", "price": 45000, "type": "military", "desc": "Armored off-road.", "emoji": "🚙"},
    {"id": "mil_buzzard", "name": "🚁 Buzzard Attack Heli", "price": 120000, "type": "military", "desc": "Attack helicopter.", "emoji": "🚁"},
    {"id": "mil_barracks", "name": "🚛 Barracks", "price": 25000, "type": "military", "desc": "Troop transport.", "emoji": "🚛"},
    {"id": "mil_apc", "name": "🛡️ APC", "price": 90000, "type": "military", "desc": "Armored personnel carrier.", "emoji": "🛡️"},
]

# ── Elitas Travel (aircraft) ──
ELITAS_ITEMS: List[Dict[str, Any]] = [
    {"id": "plane_luxor", "name": "✈️ Luxor", "price": 80000, "type": "aircraft", "desc": "Luxury private jet.", "emoji": "✈️"},
    {"id": "plane_shamal", "name": "🛩️ Shamal", "price": 65000, "type": "aircraft", "desc": "Business jet.", "emoji": "🛩️"},
    {"id": "plane_vestra", "name": "🛫 Vestra", "price": 35000, "type": "aircraft", "desc": "Light private plane.", "emoji": "🛫"},
    {"id": "plane_mammatus", "name": "🛩️ Mammatus", "price": 20000, "type": "aircraft", "desc": "Small prop plane.", "emoji": "🛩️"},
    {"id": "heli_frogger", "name": "🚁 Frogger", "price": 40000, "type": "aircraft", "desc": "Civilian helicopter.", "emoji": "🚁"},
]

# ── DockTease (boats) ──
DOCKTEASE_ITEMS: List[Dict[str, Any]] = [
    {"id": "boat_seashark", "name": "🚤 Seashark", "price": 5000, "type": "boat", "desc": "Jet ski fun.", "emoji": "🚤"},
    {"id": "boat_dinghy", "name": "🛶 Dinghy", "price": 3500, "type": "boat", "desc": "Small inflatable.", "emoji": "🛶"},
    {"id": "boat_speeder", "name": "🚤 Speeder", "price": 18000, "type": "boat", "desc": "Fast motorboat.", "emoji": "🚤"},
    {"id": "boat_marquis", "name": "🛥️ Marquis", "price": 45000, "type": "boat", "desc": "Luxury yacht tender.", "emoji": "🛥️"},
    {"id": "boat_yacht", "name": "🛳️ Galaxy Super Yacht", "price": 500000, "type": "boat", "desc": "Ultra-exclusive luxury yacht. The ultimate flex.", "emoji": "🛳️"},
]

# ── Dynasty8 (apartments / common houses) ──
DYNASTY8_ITEMS: List[Dict[str, Any]] = [
    {"id": "prop_apt_low", "name": "🏠 Low-End Apartment", "price": 15000, "type": "property", "desc": "Basic starter home.", "emoji": "🏠"},
    {"id": "prop_apt_mid", "name": "🏢 Mid-Range Apartment", "price": 45000, "type": "property", "desc": "Comfortable living.", "emoji": "🏢"},
    {"id": "prop_apt_high", "name": "🏙️ High-End Apartment", "price": 120000, "type": "property", "desc": "Luxury city living.", "emoji": "🏙️"},
    {"id": "prop_house_suburb", "name": "🏡 Suburban House", "price": 85000, "type": "property", "desc": "Quiet neighborhood house.", "emoji": "🏡"},
    {"id": "prop_house_mansion", "name": "🏰 Mansion", "price": 350000, "type": "property", "desc": "Spacious luxury mansion.", "emoji": "🏰"},
]

# ── Maze Bank Foreclosures (business / underworld properties) ──
FORECLOSURES_ITEMS: List[Dict[str, Any]] = [
    {"id": "biz_nightclub", "name": "🕺 Nightclub", "price": 200000, "type": "business", "desc": "Own a nightclub.", "emoji": "🕺"},
    {"id": "biz_warehouse", "name": "🏭 Warehouse", "price": 75000, "type": "business", "desc": "Storage complex.", "emoji": "🏭"},
    {"id": "biz_bunker", "name": "🪖 Bunker", "price": 180000, "type": "business", "desc": "Underground bunker.", "emoji": "🪖"},
    {"id": "biz_mc_clubhouse", "name": "🏍️ MC Clubhouse", "price": 95000, "type": "business", "desc": "Motorcycle club HQ.", "emoji": "🏍️"},
    {"id": "biz_agency", "name": "🕵️ Agency", "price": 160000, "type": "business", "desc": "Private investigation agency.", "emoji": "🕵️"},
    {"id": "biz_arcade", "name": "🕹️ Arcade", "price": 110000, "type": "business", "desc": "Arcade business front.", "emoji": "🕹️"},
    {"id": "biz_hangar", "name": "✈️ Hangar", "price": 140000, "type": "business", "desc": "Aircraft hangar.", "emoji": "✈️"},
    {"id": "biz_facility", "name": "🔬 Facility", "price": 250000, "type": "business", "desc": "High-tech facility.", "emoji": "🔬"},
]

DEFAULT_SETTINGS = {
    "daily_amount": 250,
    "daily_streak_bonus": 25,   # per streak day
    "max_streak_bonus": 500,
    "work_min": 40,
    "work_max": 180,
    "work_cooldown": 21600,     # 6 hours
    "balance_cooldown": 1800,   # 30 minutes (public only)
    "daily_cooldown": 86400,    # 24 hours
    "rob_chance": 0.35,
    "rob_cooldown": 7200,
    "min_bet": 10,
    "max_bet": 10000,
    "currency_name": CURRENCY,
}


def _now_ts() -> float:
    return time.time()


def _fmt(n: int | float) -> str:
    return f"{int(n):,}".replace(",", ".")


def _fmt_time(seconds: int) -> str:
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"
    if seconds >= 60:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds}s"


# ═══════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════

class EconomyData:
    USERS_KEY = "economy_users"
    SHOP_KEY = "economy_shop"
    SETTINGS_KEY = "economy_settings"
    PANELS_KEY = "economy_panels"

    def __init__(self):
        self._ensure()

    def _ensure(self):
        users = load_json(self.USERS_KEY, {})
        if not isinstance(users, dict):
            users = {}
            save_json(self.USERS_KEY, users)
        shop = load_json(self.SHOP_KEY, None)
        if not shop:
            save_json(self.SHOP_KEY, DEFAULT_SHOP)
        settings = load_json(self.SETTINGS_KEY, None)
        if not settings:
            save_json(self.SETTINGS_KEY, DEFAULT_SETTINGS.copy())
        panels = load_json(self.PANELS_KEY, {})
        if not isinstance(panels, dict):
            save_json(self.PANELS_KEY, {})

    def get_user(self, user_id: int) -> Dict[str, Any]:
        users = load_json(self.USERS_KEY, {})
        uid = str(user_id)
        if uid not in users:
            users[uid] = {
                "wallet": 0,
                "last_daily": 0,
                "streak": 0,
                "inventory": {},
                "total_earned": 0,
                "total_spent": 0,
                "last_work": 0,
                "last_balance": 0,
                "last_rob": 0,
                "created_at": _now_ts(),
            }
            save_json(self.USERS_KEY, users)
        return users[uid]

    def save_user(self, user_id: int, data: Dict[str, Any]):
        users = load_json(self.USERS_KEY, {})
        users[str(user_id)] = data
        save_json(self.USERS_KEY, users)

    def add_money(self, user_id: int, amount: int, reason: str = "") -> int:
        u = self.get_user(user_id)
        u["wallet"] = max(0, int(u.get("wallet", 0)) + amount)
        if amount > 0:
            u["total_earned"] = int(u.get("total_earned", 0)) + amount
        else:
            u["total_spent"] = int(u.get("total_spent", 0)) + abs(amount)
        self.save_user(user_id, u)
        return u["wallet"]

    def set_money(self, user_id: int, amount: int) -> int:
        u = self.get_user(user_id)
        u["wallet"] = max(0, int(amount))
        self.save_user(user_id, u)
        return u["wallet"]

    def get_settings(self) -> Dict[str, Any]:
        s = load_json(self.SETTINGS_KEY, DEFAULT_SETTINGS.copy())
        for k, v in DEFAULT_SETTINGS.items():
            s.setdefault(k, v)
        return s

    def save_settings(self, data: Dict[str, Any]):
        save_json(self.SETTINGS_KEY, data)

    def get_shop(self) -> List[Dict[str, Any]]:
        return load_json(self.SHOP_KEY, DEFAULT_SHOP.copy())

    def save_shop(self, shop: List[Dict[str, Any]]):
        save_json(self.SHOP_KEY, shop)

    def get_all_users(self) -> Dict[str, Dict]:
        return load_json(self.USERS_KEY, {})

    def reset_user(self, user_id: int):
        users = load_json(self.USERS_KEY, {})
        users.pop(str(user_id), None)
        save_json(self.USERS_KEY, users)

    def reset_all(self):
        save_json(self.USERS_KEY, {})

    def get_panels(self) -> Dict:
        return load_json(self.PANELS_KEY, {})

    def save_panels(self, data: Dict):
        save_json(self.PANELS_KEY, data)

    def get_all_items(self) -> Dict[str, Dict]:
        """Combine all shop catalogs for inventory lookup."""
        items = {}
        for lst in (
            self.get_shop(),
            BENNYS_SOUTHERN,
            BENNYS_LEGENDARY,
            WARSTOCK_ITEMS,
            ELITAS_ITEMS,
            DOCKTEASE_ITEMS,
            DYNASTY8_ITEMS,
            FORECLOSURES_ITEMS,
        ):
            for it in lst:
                items[it["id"]] = it
        return items


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def is_staff(member: discord.Member, bot: commands.Bot) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = getattr(bot, "config", {})
    for key in ("PANEL_ACCESS_ROLE_ID", "STAFF_API_ROLE_ID", "CREW_LEADER_ROLE_ID"):
        rid = cfg.get(key)
        if rid and any(r.id == rid for r in member.roles):
            return True
    return False


async def post_to_market(
    bot: commands.Bot,
    user: discord.User | discord.Member,
    embed: discord.Embed,
    view: Optional[discord.ui.View] = None,
    content: str = "",
) -> Optional[discord.Message]:
    """Post result to Bovary Market and try to ping the user."""
    ch = bot.get_channel(MARKET_CHANNEL_ID)
    if ch is None:
        try:
            ch = await bot.fetch_channel(MARKET_CHANNEL_ID)
        except Exception:
            logger.exception("Cannot fetch Market channel")
            return None
    text = content or f"{user.mention}"
    try:
        return await ch.send(content=text, embed=embed, view=view)
    except Exception:
        logger.exception("Failed to post to Market")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# VISIBILITY CHOICE VIEW (public vs ephemeral)
# ═══════════════════════════════════════════════════════════════════════════

class VisibilityChoiceView(discord.ui.View):
    """Lets the user choose to view privately or post to channel."""

    def __init__(self, cog: "Economy", action: str, user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.action = action
        self.user_id = user_id

    @discord.ui.button(label="🔒 View Privately", style=discord.ButtonStyle.primary, custom_id="vis_private")
    async def private(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        embed, view = await self.cog.handle_member_action(interaction, self.action, force_private=True)
        if embed is None:
            return await interaction.followup.send("Action cancelled or error.", ephemeral=True)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📢 Post to Channel", style=discord.ButtonStyle.secondary, custom_id="vis_public")
    async def public(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        # Check public cooldown for balance
        if self.action == "balance":
            u = self.cog.data.get_user(self.user_id)
            settings = self.cog.data.get_settings()
            now = _now_ts()
            last = float(u.get("last_balance", 0))
            cd = settings.get("balance_cooldown", 1800)
            if now - last < cd:
                rem = int(cd - (now - last))
                embed = discord.Embed(
                    title="⏳ Cooldown",
                    description=f"Public balance view is on cooldown. Try again in **{_fmt_time(rem)}**.\n\nYou can still view privately anytime.",
                    color=COLOR_FAIL,
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)
            u["last_balance"] = now
            self.cog.data.save_user(self.user_id, u)

        embed, view = await self.cog.handle_member_action(interaction, self.action, force_private=False)
        if embed is None:
            return await interaction.followup.send("Action cancelled or error.", ephemeral=True)
        msg = await post_to_market(self.cog.bot, interaction.user, embed, view)
        if msg:
            await interaction.followup.send(
                f"✅ Result posted in <#{MARKET_CHANNEL_ID}> — go to the channel to see it!",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
# SHOP BUY VIEW (generic for any item list)
# ═══════════════════════════════════════════════════════════════════════════

class ShopBuyView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int, items: List[Dict], shop_name: str = "Shop"):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.shop_name = shop_name
        options = []
        for it in items[:25]:
            options.append(discord.SelectOption(
                label=f"{it.get('emoji', '')} {it['name']}"[:100],
                value=it["id"],
                description=f"{_fmt(it['price'])} {CURRENCY}"[:100],
            ))
        if options:
            select = discord.ui.Select(placeholder="Choose an item to buy…", options=options)
            select.callback = self._buy
            self.add_item(select)

    async def _buy(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your shop!", ephemeral=True)
        item_id = interaction.data["values"][0]
        # Search all catalogs
        all_items = self.cog.data.get_all_items()
        item = all_items.get(item_id)
        if not item:
            return await interaction.response.send_message("Item not found.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        if u["wallet"] < item["price"]:
            return await interaction.response.send_message(
                f"Insufficient balance. You need {_fmt(item['price'])}.", ephemeral=True
            )
        self.cog.data.add_money(self.user_id, -item["price"], "shop_buy")
        inv = u.get("inventory", {})
        inv[item_id] = inv.get(item_id, 0) + 1
        u = self.cog.data.get_user(self.user_id)
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)
        embed = discord.Embed(
            title="🛒 Purchase Successful!",
            description=f"You bought **{item.get('emoji', '')} {item['name']}** for **{_fmt(item['price'])}** {CURRENCY}.",
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
# MEMBER PANEL VIEW (persistent)
# ═══════════════════════════════════════════════════════════════════════════

class MemberPanelView(discord.ui.View):
    def __init__(self, cog: "Economy"):
        super().__init__(timeout=None)
        self.cog = cog

    async def _cooldown_reply(self, interaction: discord.Interaction, title: str, remaining: int):
        """Always send cooldown messages as ephemeral."""
        embed = discord.Embed(
            title=title,
            description=f"Please wait **{_fmt_time(remaining)}**.",
            color=COLOR_FAIL,
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _send_ephemeral_result(self, interaction: discord.Interaction, action: str):
        """Handle action and always reply ephemeral."""
        await interaction.response.defer(ephemeral=True)
        embed, view = await self.cog.handle_member_action(interaction, action, force_private=True)
        if embed is None:
            await interaction.followup.send("Action cancelled or error.", ephemeral=True)
            return
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ── Row 0 ──
    @discord.ui.button(label="💰 Balance", style=discord.ButtonStyle.primary, custom_id="eco_balance", row=0)
    async def btn_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Offer visibility choice
        view = VisibilityChoiceView(self.cog, "balance", interaction.user.id)
        embed = discord.Embed(
            title="💰 Balance",
            description="Choose how you want to view your balance:",
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📅 Daily", style=discord.ButtonStyle.success, custom_id="eco_daily", row=0)
    async def btn_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        u = self.cog.data.get_user(uid)
        settings = self.cog.data.get_settings()
        now = _now_ts()
        last = float(u.get("last_daily", 0))
        cd = settings.get("daily_cooldown", 86400)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="📅 Daily already claimed",
                description=f"Come back in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Success — post to market (public reward) but cooldown was ephemeral
        embed, _ = await self.cog.handle_member_action(interaction, "daily", force_private=False)
        if embed:
            msg = await post_to_market(self.cog.bot, interaction.user, embed)
            if msg:
                await interaction.followup.send(
                    f"✅ Daily claimed! Result posted in <#{MARKET_CHANNEL_ID}>.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="💸 Pay", style=discord.ButtonStyle.secondary, custom_id="eco_pay", row=0)
    async def btn_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PayModal(self.cog))

    @discord.ui.button(label="💼 Work", style=discord.ButtonStyle.secondary, custom_id="eco_work", row=0)
    async def btn_work(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        u = self.cog.data.get_user(uid)
        settings = self.cog.data.get_settings()
        now = _now_ts()
        last = float(u.get("last_work", 0))
        cd = settings.get("work_cooldown", 21600)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="💼 On cooldown",
                description=f"You can work again in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        embed, _ = await self.cog.handle_member_action(interaction, "work", force_private=False)
        if embed:
            msg = await post_to_market(self.cog.bot, interaction.user, embed)
            if msg:
                await interaction.followup.send(
                    f"✅ Work completed! Result posted in <#{MARKET_CHANNEL_ID}>.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Row 1 ──
    @discord.ui.button(label="🎒 Inventory", style=discord.ButtonStyle.secondary, custom_id="eco_inv", row=1)
    async def btn_inv(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = VisibilityChoiceView(self.cog, "inventory", interaction.user.id)
        embed = discord.Embed(
            title="🎒 Inventory",
            description="Choose how you want to view your inventory:",
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏆 Ranking", style=discord.ButtonStyle.primary, custom_id="eco_lb", row=1)
    async def btn_lb(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ranking is ALWAYS ephemeral for members
        await self._send_ephemeral_result(interaction, "leaderboard")

    @discord.ui.button(label="🛒 Shop", style=discord.ButtonStyle.primary, custom_id="eco_shop", row=1)
    async def btn_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Shop is ALWAYS ephemeral
        await self._send_ephemeral_result(interaction, "shop")

    @discord.ui.button(label="❓ Help", style=discord.ButtonStyle.secondary, custom_id="eco_help", row=1)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❓ Bovary Economy — Help",
            description=(
                f"**Currency:** {CURRENCY_EMOJI} {CURRENCY}\n\n"
                "**Panel buttons:**\n"
                "💰 **Balance** — view your wallet (private or public)\n"
                "📅 **Daily** — daily reward (+ streak) — 24h cooldown\n"
                "💸 **Pay** — transfer coins to another member\n"
                "💼 **Work** — earn coins — 6h cooldown\n"
                "🎒 **Inventory** — your items (private or public)\n"
                "🏆 **Ranking** — top richest (private only)\n"
                "🛒 **Shop** — pets, badges & consumables (private only)\n\n"
                "**Special shops:**\n"
                "🏎️ **Benny's** — cars (Southern SA Super Autos & Legendary Motorsport)\n"
                "🪖 **Warstock** — military vehicles\n"
                "✈️ **Elitas Travel** — aircraft\n"
                "🚤 **DockTease** — boats (incl. luxury yacht)\n"
                "🏠 **Dynasty8** — apartments & houses\n"
                "🏢 **Maze Bank Foreclosures** — businesses & underworld properties\n"
                "🎰 **Casino Resort** — coming soon\n"
                "🎮 **MC Lost** / **CEO Securo Serv** — games under construction\n\n"
                "Cooldown messages are always private (only you can see them)."
            ),
            color=COLOR_INFO,
        )
        embed.set_footer(text="Bovary Economy")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Row 2 — Vehicle & travel shops ──
    @discord.ui.button(label="🏎️ Benny's Workshop", style=discord.ButtonStyle.primary, custom_id="eco_bennys", row=2)
    async def btn_bennys(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "bennys")

    @discord.ui.button(label="🪖 Warstock", style=discord.ButtonStyle.danger, custom_id="eco_warstock", row=2)
    async def btn_warstock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "warstock")

    @discord.ui.button(label="✈️ Elitas Travel", style=discord.ButtonStyle.primary, custom_id="eco_elitas", row=2)
    async def btn_elitas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "elitas")

    @discord.ui.button(label="🚤 DockTease", style=discord.ButtonStyle.primary, custom_id="eco_docktease", row=2)
    async def btn_docktease(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "docktease")

    # ── Row 3 — Properties & Casino ──
    @discord.ui.button(label="🏠 Dynasty8", style=discord.ButtonStyle.success, custom_id="eco_dynasty8", row=3)
    async def btn_dynasty8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "dynasty8")

    @discord.ui.button(label="🏢 Maze Bank Foreclosures", style=discord.ButtonStyle.success, custom_id="eco_foreclosures", row=3)
    async def btn_foreclosures(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "foreclosures")

    @discord.ui.button(label="🎰 Casino Resort", style=discord.ButtonStyle.primary, custom_id="eco_casino", row=3)
    async def btn_casino(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎰 Casino Resort",
            description=(
                "**Under Construction** 🚧\n\n"
                "The luxurious Casino Resort is being prepared.\n"
                "High-stakes tables, exclusive rewards and VIP experiences coming soon.\n\n"
                "*Stay tuned — the house always wins… eventually.*"
            ),
            color=COLOR_CASINO,
        )
        embed.set_footer(text="Bovary Economy · Casino Resort · Coming Soon")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Row 4 — Future games ──
    @discord.ui.button(label="🎮 MC Lost", style=discord.ButtonStyle.secondary, custom_id="eco_mclost", row=4)
    async def btn_mclost(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎮 MC Lost",
            description=(
                "**Under Construction** 🚧\n\n"
                "This mini-game is currently being developed.\n"
                "Check back later for updates!"
            ),
            color=COLOR_CONSTRUCTION,
        )
        embed.set_footer(text="Bovary Economy · MC Lost · Coming Soon")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💼 CEO Securo Serv", style=discord.ButtonStyle.secondary, custom_id="eco_ceosecuro", row=4)
    async def btn_ceosecuro(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="💼 CEO Securo Serv",
            description=(
                "**Under Construction** 🚧\n\n"
                "This mini-game is currently being developed.\n"
                "Check back later for updates!"
            ),
            color=COLOR_CONSTRUCTION,
        )
        embed.set_footer(text="Bovary Economy · CEO Securo Serv · Coming Soon")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PayModal(discord.ui.Modal, title="💸 Pay Member"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.user_input = discord.ui.TextInput(
            label="User ID or @mention",
            placeholder="123456789 or mention",
            required=True,
        )
        self.amount_input = discord.ui.TextInput(
            label="Amount",
            placeholder="100",
            required=True,
        )
        self.add_item(self.user_input)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = self.user_input.value.strip().replace("<@", "").replace("!", "").replace(">", "")
        try:
            target_id = int(raw)
        except ValueError:
            return await interaction.followup.send("Invalid ID.", ephemeral=True)
        try:
            amount = int(self.amount_input.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.followup.send("Invalid amount.", ephemeral=True)
        if amount <= 0:
            return await interaction.followup.send("Amount must be positive.", ephemeral=True)
        if target_id == interaction.user.id:
            return await interaction.followup.send("You cannot pay yourself.", ephemeral=True)

        payer = self.cog.data.get_user(interaction.user.id)
        if payer["wallet"] < amount:
            return await interaction.followup.send(
                f"Insufficient balance. You have {_fmt(payer['wallet'])}.", ephemeral=True
            )

        self.cog.data.add_money(interaction.user.id, -amount, "pay")
        self.cog.data.add_money(target_id, amount, "pay_received")
        target = interaction.guild.get_member(target_id) if interaction.guild else None
        if target is None:
            try:
                target = await self.cog.bot.fetch_user(target_id)
            except Exception:
                target = None
        name = target.display_name if target and hasattr(target, "display_name") else str(target_id)

        embed = discord.Embed(
            title="💸 Transfer Completed",
            description=f"{interaction.user.mention} sent **{_fmt(amount)}** {CURRENCY} to **{name}**.",
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Bovary Economy")
        await post_to_market(self.cog.bot, interaction.user, embed)
        await interaction.followup.send(
            f"✅ Sent {_fmt(amount)} to {name}. See it in <#{MARKET_CHANNEL_ID}>",
            ephemeral=True,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN PANEL VIEW
# ═══════════════════════════════════════════════════════════════════════════

class AdminPanelView(discord.ui.View):
    def __init__(self, cog: "Economy"):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if not is_staff(interaction.user, self.cog.bot):
            await interaction.response.send_message("🔒 Access denied. Staff only.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="➕ Add Money", style=discord.ButtonStyle.success, custom_id="adm_add_money", row=0)
    async def add_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminMoneyModal(self.cog, "add"))

    @discord.ui.button(label="➖ Remove Money", style=discord.ButtonStyle.danger, custom_id="adm_rem_money", row=0)
    async def rem_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminMoneyModal(self.cog, "remove"))

    @discord.ui.button(label="✏️ Set Money", style=discord.ButtonStyle.primary, custom_id="adm_set_money", row=0)
    async def set_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminMoneyModal(self.cog, "set"))

    @discord.ui.button(label="🌐 All +", style=discord.ButtonStyle.success, custom_id="adm_all_add", row=1)
    async def all_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminAllModal(self.cog, "add"))

    @discord.ui.button(label="🌐 All −", style=discord.ButtonStyle.danger, custom_id="adm_all_rem", row=1)
    async def all_rem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminAllModal(self.cog, "remove"))

    @discord.ui.button(label="🔄 Reset User", style=discord.ButtonStyle.danger, custom_id="adm_reset_user", row=1)
    async def reset_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminResetUserModal(self.cog))

    @discord.ui.button(label="💥 Reset Server", style=discord.ButtonStyle.danger, custom_id="adm_reset_server", row=2)
    async def reset_server(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ConfirmResetView(self.cog)
        await interaction.response.send_message(
            "⚠️ Confirm RESET of ALL balances?", view=view, ephemeral=True
        )

    @discord.ui.button(label="⚙️ Settings", style=discord.ButtonStyle.secondary, custom_id="adm_settings", row=2)
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.cog.data.get_settings()
        embed = discord.Embed(title="⚙️ Current Settings", color=COLOR_ADMIN)
        for k, v in s.items():
            embed.add_field(name=k, value=str(v), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📅 Set Daily", style=discord.ButtonStyle.secondary, custom_id="adm_set_daily", row=2)
    async def set_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminDailyModal(self.cog))

    @discord.ui.button(label="🛒 Shop Add", style=discord.ButtonStyle.success, custom_id="adm_shop_add", row=3)
    async def shop_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminShopAddModal(self.cog))

    @discord.ui.button(label="🛒 Shop Remove", style=discord.ButtonStyle.danger, custom_id="adm_shop_rem", row=3)
    async def shop_rem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminShopRemModal(self.cog))

    @discord.ui.button(label="📋 Backup Wallets", style=discord.ButtonStyle.primary, custom_id="adm_backup", row=3)
    async def backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        users = self.cog.data.get_all_users()
        lines = ["user_id,wallet,streak,total_earned"]
        for uid, d in sorted(users.items(), key=lambda x: -x[1].get("wallet", 0)):
            lines.append(f"{uid},{d.get('wallet',0)},{d.get('streak',0)},{d.get('total_earned',0)}")
        content = "\n".join(lines)
        file = discord.File(
            fp=__import__("io").BytesIO(content.encode("utf-8")),
            filename=f"wallets_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        )
        await interaction.followup.send("Wallet backup:", file=file, ephemeral=True)

    @discord.ui.button(label="🏆 Post Ranking", style=discord.ButtonStyle.primary, custom_id="adm_post_lb", row=4)
    async def post_ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admins can post ranking publicly."""
        await interaction.response.defer(ephemeral=True)
        embed, _ = await self.cog.handle_member_action(interaction, "leaderboard", force_private=False)
        if embed:
            await post_to_market(self.cog.bot, interaction.user, embed)
            await interaction.followup.send(
                f"✅ Ranking posted in <#{MARKET_CHANNEL_ID}>.", ephemeral=True
            )


class AdminMoneyModal(discord.ui.Modal, title="Manage Balance"):
    def __init__(self, cog: "Economy", mode: str):
        super().__init__()
        self.cog = cog
        self.mode = mode
        self.uid = discord.ui.TextInput(label="User ID", required=True)
        self.amt = discord.ui.TextInput(label="Amount", required=True)
        self.add_item(self.uid)
        self.add_item(self.amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.uid.value.strip())
            amount = int(self.amt.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Invalid values.", ephemeral=True)
        if self.mode == "add":
            bal = self.cog.data.add_money(uid, amount, "admin_add")
            msg = f"Added {_fmt(amount)}. New balance: {_fmt(bal)}"
        elif self.mode == "remove":
            bal = self.cog.data.add_money(uid, -amount, "admin_remove")
            msg = f"Removed {_fmt(amount)}. New balance: {_fmt(bal)}"
        else:
            bal = self.cog.data.set_money(uid, amount)
            msg = f"Balance set to {_fmt(bal)}"
        await interaction.response.send_message(f"✅ {msg}", ephemeral=True)


class AdminAllModal(discord.ui.Modal, title="All Users"):
    def __init__(self, cog: "Economy", mode: str):
        super().__init__()
        self.cog = cog
        self.mode = mode
        self.amt = discord.ui.TextInput(label="Amount", required=True)
        self.add_item(self.amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amt.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Invalid.", ephemeral=True)
        users = self.cog.data.get_all_users()
        delta = amount if self.mode == "add" else -amount
        for uid in list(users.keys()):
            self.cog.data.add_money(int(uid), delta, f"admin_all_{self.mode}")
        await interaction.response.send_message(f"✅ Applied to {len(users)} users.", ephemeral=True)


class AdminResetUserModal(discord.ui.Modal, title="Reset User"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.uid = discord.ui.TextInput(label="User ID", required=True)
        self.add_item(self.uid)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.uid.value.strip())
        except ValueError:
            return await interaction.response.send_message("Invalid ID.", ephemeral=True)
        self.cog.data.reset_user(uid)
        await interaction.response.send_message(f"✅ User {uid} reset.", ephemeral=True)


class ConfirmResetView(discord.ui.View):
    def __init__(self, cog: "Economy"):
        super().__init__(timeout=30)
        self.cog = cog

    @discord.ui.button(label="CONFIRM SERVER RESET", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.data.reset_all()
        await interaction.response.edit_message(content="💥 Server economy reset.", view=None)


class AdminDailyModal(discord.ui.Modal, title="Set Daily Amount"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.amt = discord.ui.TextInput(label="Base daily amount", required=True)
        self.add_item(self.amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            v = int(self.amt.value)
        except ValueError:
            return await interaction.response.send_message("Invalid.", ephemeral=True)
        s = self.cog.data.get_settings()
        s["daily_amount"] = v
        self.cog.data.save_settings(s)
        await interaction.response.send_message(f"✅ Daily base = {_fmt(v)}", ephemeral=True)


class AdminShopAddModal(discord.ui.Modal, title="Add Item to Shop"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.iid = discord.ui.TextInput(label="Unique ID (e.g. pet_new)", required=True)
        self.name = discord.ui.TextInput(label="Name", required=True)
        self.price = discord.ui.TextInput(label="Price", required=True)
        self.typ = discord.ui.TextInput(label="Type (pet/badge/consumable)", required=True, default="pet")
        self.emoji = discord.ui.TextInput(label="Emoji", required=False, default="🎁")
        self.add_item(self.iid)
        self.add_item(self.name)
        self.add_item(self.price)
        self.add_item(self.typ)
        self.add_item(self.emoji)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price.value)
        except ValueError:
            return await interaction.response.send_message("Invalid price.", ephemeral=True)
        shop = self.cog.data.get_shop()
        shop.append({
            "id": self.iid.value.strip(),
            "name": self.name.value.strip(),
            "price": price,
            "type": self.typ.value.strip().lower(),
            "desc": "",
            "emoji": self.emoji.value or "🎁",
        })
        self.cog.data.save_shop(shop)
        await interaction.response.send_message(f"✅ Item `{self.iid.value}` added.", ephemeral=True)


class AdminShopRemModal(discord.ui.Modal, title="Remove Item from Shop"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.iid = discord.ui.TextInput(label="Item ID", required=True)
        self.add_item(self.iid)

    async def on_submit(self, interaction: discord.Interaction):
        shop = self.cog.data.get_shop()
        new = [i for i in shop if i["id"] != self.iid.value.strip()]
        if len(new) == len(shop):
            return await interaction.response.send_message("Item not found.", ephemeral=True)
        self.cog.data.save_shop(new)
        await interaction.response.send_message("✅ Item removed.", ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
# COG
# ═══════════════════════════════════════════════════════════════════════════

class Economy(commands.Cog):
    """Bovary Economy system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = EconomyData()
        self.bot.add_view(MemberPanelView(self))
        self.bot.add_view(AdminPanelView(self))

    async def cog_load(self):
        logger.info("Bovary Economy loaded")

    # ── Member action handlers ─────────────────────────────────────────────

    async def handle_member_action(
        self,
        interaction: discord.Interaction,
        action: str,
        force_private: bool = False,
    ) -> Tuple[Optional[discord.Embed], Optional[discord.ui.View]]:
        uid = interaction.user.id
        u = self.data.get_user(uid)
        settings = self.data.get_settings()

        if action == "balance":
            embed = discord.Embed(
                title=f"{CURRENCY_EMOJI} Your Wallet",
                description=f"**Balance:** {_fmt(u['wallet'])} {CURRENCY}",
                color=COLOR_MAIN,
            )
            embed.add_field(name="Daily Streak", value=str(u.get("streak", 0)), inline=True)
            embed.add_field(name="Total Earned", value=_fmt(u.get("total_earned", 0)), inline=True)
            embed.add_field(name="Total Spent", value=_fmt(u.get("total_spent", 0)), inline=True)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Bovary Economy")
            return embed, None

        if action == "daily":
            now = _now_ts()
            last = float(u.get("last_daily", 0))
            cd = settings.get("daily_cooldown", 86400)
            if now - last < cd:
                remaining = int(cd - (now - last))
                embed = discord.Embed(
                    title="📅 Daily already claimed",
                    description=f"Come back in **{_fmt_time(remaining)}**.",
                    color=COLOR_FAIL,
                )
                return embed, None
            # streak
            if now - last < 48 * 3600:
                streak = int(u.get("streak", 0)) + 1
            else:
                streak = 1
            base = settings["daily_amount"]
            bonus = min(settings["max_streak_bonus"], streak * settings["daily_streak_bonus"])
            total = base + bonus
            u["last_daily"] = now
            u["streak"] = streak
            self.data.save_user(uid, u)
            self.data.add_money(uid, total, "daily")
            embed = discord.Embed(
                title="📅 Daily Claimed!",
                description=(
                    f"You received **{_fmt(total)}** {CURRENCY}\n"
                    f"(base {_fmt(base)} + streak x{streak} = +{_fmt(bonus)})\n\n"
                    f"🔥 Current streak: **{streak}** days"
                ),
                color=COLOR_SUCCESS,
            )
            embed.set_footer(text="Bovary Economy")
            return embed, None

        if action == "work":
            now = _now_ts()
            last = float(u.get("last_work", 0))
            cd = settings.get("work_cooldown", 21600)
            if now - last < cd:
                rem = int(cd - (now - last))
                embed = discord.Embed(
                    title="💼 On cooldown",
                    description=f"You can work again in **{_fmt_time(rem)}**.",
                    color=COLOR_FAIL,
                )
                return embed, None
            pay = random.randint(settings["work_min"], settings["work_max"])
            jobs = [
                "You delivered orders for Bovary Café and earned",
                "You cleaned the Fenrir server and received",
                "You organized a meet and earned",
                "You sold memes in chat and made",
                "You helped Nazar and he paid you",
                "You designed a badge and received",
            ]
            text = random.choice(jobs)
            u["last_work"] = now
            self.data.save_user(uid, u)
            self.data.add_money(uid, pay, "work")
            embed = discord.Embed(
                title="💼 Work Completed",
                description=f"{text} **{_fmt(pay)}** {CURRENCY}!",
                color=COLOR_SUCCESS,
            )
            return embed, None

        if action == "shop":
            shop = self.data.get_shop()
            if not shop:
                embed = discord.Embed(
                    title="🛒 Shop Empty",
                    description="No items available.",
                    color=COLOR_INFO,
                )
                return embed, None
            lines = []
            for it in shop:
                lines.append(
                    f"{it.get('emoji','🎁')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY} (`{it['type']}`)"
                )
            embed = discord.Embed(
                title="🛒 Bovary Shop",
                description="\n".join(lines[:30]),
                color=COLOR_MAIN,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, shop, "Bovary Shop")
            return embed, view

        if action == "bennys":
            embed = discord.Embed(
                title="🏎️ Benny's Original Motor Workshop",
                description="Premium vehicles from Los Santos dealers.",
                color=COLOR_MAIN,
            )
            # Southern San Andreas Super Autos
            southern_lines = []
            for it in BENNYS_SOUTHERN:
                southern_lines.append(
                    f"{it.get('emoji','🚗')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                )
            embed.add_field(
                name="🏁 Southern San Andreas Super Autos",
                value="\n".join(southern_lines) or "—",
                inline=False,
            )
            # Legendary Motorsport
            legendary_lines = []
            for it in BENNYS_LEGENDARY:
                legendary_lines.append(
                    f"{it.get('emoji','🚗')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                )
            embed.add_field(
                name="🏆 Legendary Motorsport",
                value="\n".join(legendary_lines) or "—",
                inline=False,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            all_cars = BENNYS_SOUTHERN + BENNYS_LEGENDARY
            view = ShopBuyView(self, uid, all_cars, "Benny's")
            return embed, view

        if action == "warstock":
            lines = [
                f"{it.get('emoji','🪖')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in WARSTOCK_ITEMS
            ]
            embed = discord.Embed(
                title="🪖 Warstock Cache & Carry",
                description="Military vehicles and equipment.\n\n" + "\n".join(lines),
                color=COLOR_FAIL,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, WARSTOCK_ITEMS, "Warstock")
            return embed, view

        if action == "elitas":
            lines = [
                f"{it.get('emoji','✈️')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in ELITAS_ITEMS
            ]
            embed = discord.Embed(
                title="✈️ Elitas Travel",
                description="Aircraft for the skies of Los Santos.\n\n" + "\n".join(lines),
                color=COLOR_INFO,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, ELITAS_ITEMS, "Elitas Travel")
            return embed, view

        if action == "docktease":
            lines = [
                f"{it.get('emoji','🚤')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in DOCKTEASE_ITEMS
            ]
            embed = discord.Embed(
                title="🚤 DockTease",
                description=(
                    "Boats and watercraft.\n"
                    "Includes the exclusive **Galaxy Super Yacht**.\n\n"
                    + "\n".join(lines)
                ),
                color=COLOR_INFO,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, DOCKTEASE_ITEMS, "DockTease")
            return embed, view

        if action == "dynasty8":
            lines = [
                f"{it.get('emoji','🏠')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in DYNASTY8_ITEMS
            ]
            embed = discord.Embed(
                title="🏠 Dynasty8",
                description="Apartments and common houses.\n\n" + "\n".join(lines),
                color=COLOR_SUCCESS,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, DYNASTY8_ITEMS, "Dynasty8")
            return embed, view

        if action == "foreclosures":
            lines = [
                f"{it.get('emoji','🏢')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in FORECLOSURES_ITEMS
            ]
            embed = discord.Embed(
                title="🏢 Maze Bank Foreclosures",
                description=(
                    "Nightclubs, complexes, warehouses, bunkers,\n"
                    "MC clubhouses, agencies and underworld properties.\n\n"
                    + "\n".join(lines)
                ),
                color=COLOR_ADMIN,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, FORECLOSURES_ITEMS, "Foreclosures")
            return embed, view

        if action == "inventory":
            inv = u.get("inventory", {})
            if not inv:
                embed = discord.Embed(
                    title="🎒 Empty Inventory",
                    description="Buy items from the shops!",
                    color=COLOR_INFO,
                )
                return embed, None
            all_items = self.data.get_all_items()
            lines = []
            for iid, qty in inv.items():
                item = all_items.get(iid, {})
                name = item.get("name", iid)
                emoji = item.get("emoji", "🎁")
                lines.append(f"{emoji} **{name}** ×{qty}")
            embed = discord.Embed(
                title="🎒 Your Inventory",
                description="\n".join(lines),
                color=COLOR_INFO,
            )
            return embed, None

        if action == "leaderboard":
            users = self.data.get_all_users()
            ranked = sorted(users.items(), key=lambda x: x[1].get("wallet", 0), reverse=True)[:15]
            lines = []
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid_s, d) in enumerate(ranked):
                medal = medals[i] if i < 3 else f"`{i+1}.`"
                member = interaction.guild.get_member(int(uid_s)) if interaction.guild else None
                name = member.display_name if member else f"User {uid_s}"
                lines.append(f"{medal} **{name}** — {_fmt(d.get('wallet', 0))} {CURRENCY}")
            embed = discord.Embed(
                title=f"🏆 Ranking — {CURRENCY}",
                description="\n".join(lines) or "Nobody yet.",
                color=COLOR_MAIN,
            )
            return embed, None

        return None, None

    # ── Slash (admin + optional) ───────────────────────────────────────────

    eco = app_commands.Group(name="economy", description="Bovary Economy (staff + utility)")

    @eco.command(name="panel", description="[LOCKED] Post member panel in Maze Bank")
    async def panel_cmd(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user, self.bot):
            return await interaction.response.send_message("🔒 Staff only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ch = self.bot.get_channel(BANK_CHANNEL_ID) or await self.bot.fetch_channel(BANK_CHANNEL_ID)
        embed = discord.Embed(
            title=f"{CURRENCY_EMOJI} MAZE BANK",
            description=(
                f"**Welcome to the Bovary Economy system!**\n\n"
                f"Currency: **{CURRENCY}**\n\n"
                "Use the buttons below to:\n"
                "• Check balance & claim daily\n"
                "• Work, pay others, view inventory\n"
                "• Browse shops (cars, military, planes, boats, properties)\n"
                "• Ranking (private only)\n\n"
                "🔒 Cooldown messages are always private.\n"
                "🛒 Shops open in private view only."
            ),
            color=COLOR_MAIN,
        )
        embed.set_footer(text="Bovary Economy · Maze Bank · Click the buttons")
        view = MemberPanelView(self)
        msg = await ch.send(embed=embed, view=view)
        panels = self.data.get_panels()
        panels["member"] = {"channel_id": BANK_CHANNEL_ID, "message_id": msg.id}
        self.data.save_panels(panels)
        await interaction.followup.send(
            f"✅ Panel posted in <#{BANK_CHANNEL_ID}> (Maze Bank)", ephemeral=True
        )

    @eco.command(name="adminpanel", description="[LOCKED] Post admin panel in Bank Admin")
    async def adminpanel_cmd(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user, self.bot):
            return await interaction.response.send_message("🔒 Staff only.", ephemeral=True)
        if interaction.channel_id != ADMIN_CHANNEL_ID:
            return await interaction.response.send_message(
                f"This panel can only be posted in <#{ADMIN_CHANNEL_ID}>.", ephemeral=True
            )
        embed = discord.Embed(
            title="🛡️ BANK ADMIN — Economy Control",
            description=(
                "**Staff-only panel.**\n\n"
                "Manage balances, shop, settings and backups.\n"
                "Use **Post Ranking** to publish the leaderboard publicly."
            ),
            color=COLOR_ADMIN,
        )
        view = AdminPanelView(self)
        await interaction.response.send_message(embed=embed, view=view)

    @eco.command(name="balance", description="View your balance (slash shortcut)")
    async def bal_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        u = self.data.get_user(target.id)
        embed = discord.Embed(
            title=f"{CURRENCY_EMOJI} Wallet of {target.display_name}",
            description=f"**{_fmt(u['wallet'])}** {CURRENCY}",
            color=COLOR_MAIN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
