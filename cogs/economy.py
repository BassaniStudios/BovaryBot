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
COLOR_PURPLE = discord.Color.from_rgb(142, 68, 173)
COLOR_ORANGE = discord.Color.from_rgb(230, 126, 34)
COLOR_LILAC = discord.Color.from_rgb(155, 89, 182)
COLOR_LIGHT_BLUE = discord.Color.from_rgb(133, 193, 233)

# ── Default general shop (removed from member panel — empty for compatibility) ──
DEFAULT_SHOP: List[Dict[str, Any]] = []

# ── Benny's Original Motor Workshop (cars) ──
BENNYS_SOUTHERN: List[Dict[str, Any]] = [
    {"id": "car_vigero", "name": "🚗 Vigero", "price": 5500, "type": "car", "desc": "Classic muscle coupe.", "emoji": "🚗", "dealer": "southern"},
    {"id": "car_sultan", "name": "🏎️ Sultan", "price": 8000, "type": "car", "desc": "Tunable sports sedan.", "emoji": "🏎️", "dealer": "southern"},
    {"id": "car_peyote", "name": "🚘 Peyote", "price": 4500, "type": "car", "desc": "Vintage convertible classic.", "emoji": "🚘", "dealer": "southern"},
    {"id": "car_baller", "name": "🚙 Baller", "price": 9500, "type": "car", "desc": "Luxury SUV.", "emoji": "🚙", "dealer": "southern"},
    {"id": "car_issi", "name": "🚕 Issi", "price": 3500, "type": "car", "desc": "Compact city car.", "emoji": "🚕", "dealer": "southern"},
    {"id": "car_panto", "name": "🚙 Panto", "price": 2800, "type": "car", "desc": "Tiny city runabout.", "emoji": "🚙", "dealer": "southern"},
    {"id": "car_tailgater", "name": "🚗 Tailgater", "price": 7200, "type": "car", "desc": "Executive sedan.", "emoji": "🚗", "dealer": "southern"},
]

BENNYS_LEGENDARY: List[Dict[str, Any]] = [
    {"id": "car_entity_xf", "name": "⚡ Entity XF", "price": 20000, "type": "car", "desc": "Hypercar masterpiece.", "emoji": "⚡", "dealer": "legendary"},
    {"id": "car_zentorno", "name": "🔥 Zentorno", "price": 22000, "type": "car", "desc": "Hypercar legend.", "emoji": "🔥", "dealer": "legendary"},
    {"id": "car_coquette_d1", "name": "🏁 Coquette D1", "price": 16000, "type": "car", "desc": "Classic racing coupe.", "emoji": "🏁", "dealer": "legendary"},
    {"id": "car_ztype", "name": "🚘 Z-Type", "price": 14000, "type": "car", "desc": "Vintage luxury classic.", "emoji": "🚘", "dealer": "legendary"},
    {"id": "car_zion_cabrio", "name": "🌞 Zion Cabrio", "price": 11000, "type": "car", "desc": "Stylish convertible.", "emoji": "🌞", "dealer": "legendary"},
    {"id": "car_dubsta_6x6", "name": "🛻 Dubsta 6x6", "price": 18000, "type": "car", "desc": "Six-wheel off-road beast.", "emoji": "🛻", "dealer": "legendary"},
    {"id": "car_kamacho", "name": "🚙 Kamacho", "price": 13500, "type": "car", "desc": "Rugged off-road truck.", "emoji": "🚙", "dealer": "legendary"},
    {"id": "car_patriot", "name": "🛡️ Patriot", "price": 10000, "type": "car", "desc": "Military-inspired SUV.", "emoji": "🛡️", "dealer": "legendary"},
]

# ── Lost MC Shop (motorcycles — part of Benny's) ──
BENNYS_LOST_MC: List[Dict[str, Any]] = [
    {"id": "bike_daemon", "name": "🏍️ Daemon", "price": 6500, "type": "motorcycle", "desc": "Classic chopper.", "emoji": "🏍️", "dealer": "lost_mc"},
    {"id": "bike_nemesis", "name": "🏍️ Nemesis", "price": 7200, "type": "motorcycle", "desc": "Aggressive street bike.", "emoji": "🏍️", "dealer": "lost_mc"},
    {"id": "bike_sanctus", "name": "☠️ Sanctus", "price": 15000, "type": "motorcycle", "desc": "Custom Lost MC chopper.", "emoji": "☠️", "dealer": "lost_mc"},
    {"id": "bike_pcj600", "name": "🏍️ PCJ-600", "price": 4800, "type": "motorcycle", "desc": "Sporty street motorcycle.", "emoji": "🏍️", "dealer": "lost_mc"},
    {"id": "bike_ruffian", "name": "🏍️ Ruffian", "price": 5500, "type": "motorcycle", "desc": "Fast street fighter.", "emoji": "🏍️", "dealer": "lost_mc"},
    {"id": "bike_sanchez", "name": "🏍️ Sanchez", "price": 4200, "type": "motorcycle", "desc": "Dirt bike legend.", "emoji": "🏍️", "dealer": "lost_mc"},
    {"id": "bike_hakuchou", "name": "🏍️ Hakuchou", "price": 12000, "type": "motorcycle", "desc": "High-speed sports bike.", "emoji": "🏍️", "dealer": "lost_mc"},
]

# ── Warstock Cache & Carry (military) ──
WARSTOCK_ITEMS: List[Dict[str, Any]] = [
    {"id": "mil_rhino", "name": "🛡️ Rhino Tank", "price": 185000, "type": "military", "desc": "Heavy armor tank.", "emoji": "🛡️"},
    {"id": "mil_insurgent", "name": "🚙 Insurgent", "price": 45000, "type": "military", "desc": "Armored off-road.", "emoji": "🚙"},
    {"id": "mil_buzzard", "name": "🚁 Buzzard Attack Heli", "price": 145000, "type": "military", "desc": "Attack helicopter.", "emoji": "🚁"},
    {"id": "mil_barracks", "name": "🚛 Barracks", "price": 25000, "type": "military", "desc": "Troop transport.", "emoji": "🚛"},
    {"id": "mil_apc", "name": "🛡️ APC", "price": 110000, "type": "military", "desc": "Armored personnel carrier.", "emoji": "🛡️"},
    {"id": "mil_submarine", "name": "🚢 Kosatka Submarine", "price": 48000, "type": "military", "desc": "Permanent submarine. Required to access Cayo Perico Heist.", "emoji": "🚢"},
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
    {"id": "boat_seashark", "name": "🚤 Seashark", "price": 4500, "type": "boat", "desc": "Jet ski fun.", "emoji": "🚤"},
    {"id": "boat_dinghy", "name": "🛶 Dinghy", "price": 3200, "type": "boat", "desc": "Small inflatable.", "emoji": "🛶"},
    {"id": "boat_suntrap", "name": "⛵ Suntrap", "price": 6500, "type": "boat", "desc": "Small leisure boat.", "emoji": "⛵"},
    {"id": "boat_jetmax", "name": "🚤 Jetmax", "price": 12000, "type": "boat", "desc": "High-speed runabout.", "emoji": "🚤"},
    {"id": "boat_speeder", "name": "🚤 Speeder", "price": 16000, "type": "boat", "desc": "Fast motorboat.", "emoji": "🚤"},
    {"id": "boat_squalo", "name": "🛥️ Squalo", "price": 22000, "type": "boat", "desc": "Sleek performance boat.", "emoji": "🛥️"},
    {"id": "boat_tropic", "name": "⛵ Tropic", "price": 28000, "type": "boat", "desc": "Luxury speedboat.", "emoji": "⛵"},
    {"id": "boat_marquis", "name": "🛥️ Marquis", "price": 42000, "type": "boat", "desc": "Luxury yacht tender.", "emoji": "🛥️"},
    {"id": "boat_toro", "name": "🚤 Toro", "price": 55000, "type": "boat", "desc": "Premium powerboat.", "emoji": "🚤"},
    {"id": "boat_yacht", "name": "🛳️ Galaxy Super Yacht", "price": 280000, "type": "boat", "desc": "Ultra-exclusive luxury yacht. The ultimate flex.", "emoji": "🛳️"},
]

# ── Dynasty8 (apartments / common houses) ──
DYNASTY8_ITEMS: List[Dict[str, Any]] = [
    {"id": "prop_apt_low", "name": "🏠 Low-End Apartment", "price": 12000, "type": "property", "desc": "Basic starter home.", "emoji": "🏠"},
    {"id": "prop_apt_mid", "name": "🏢 Mid-Range Apartment", "price": 38000, "type": "property", "desc": "Comfortable living.", "emoji": "🏢"},
    {"id": "prop_apt_high", "name": "🏙️ High-End Apartment", "price": 95000, "type": "property", "desc": "Luxury city living.", "emoji": "🏙️"},
    {"id": "prop_house_suburb", "name": "🏡 Suburban House", "price": 72000, "type": "property", "desc": "Quiet neighborhood house.", "emoji": "🏡"},
    {"id": "prop_house_mansion", "name": "🏰 Mansion", "price": 220000, "type": "property", "desc": "Spacious luxury mansion.", "emoji": "🏰"},
]

# ── Maze Bank Foreclosures (business / underworld properties) ──
FORECLOSURES_ITEMS: List[Dict[str, Any]] = [
    {"id": "biz_nightclub", "name": "🕺 Nightclub", "price": 175000, "type": "business", "desc": "Own a nightclub.", "emoji": "🕺"},
    {"id": "biz_warehouse", "name": "🏭 Warehouse", "price": 65000, "type": "business", "desc": "Storage complex.", "emoji": "🏭"},
    {"id": "biz_bunker", "name": "🪖 Bunker", "price": 155000, "type": "business", "desc": "Underground bunker.", "emoji": "🪖"},
    {"id": "biz_mc_clubhouse", "name": "🏍️ MC Clubhouse", "price": 85000, "type": "business", "desc": "Motorcycle club HQ.", "emoji": "🏍️"},
    {"id": "biz_agency", "name": "🕵️ Agency", "price": 140000, "type": "business", "desc": "Private investigation agency.", "emoji": "🕵️"},
    {"id": "biz_arcade", "name": "🕹️ Arcade", "price": 95000, "type": "business", "desc": "Arcade business front.", "emoji": "🕹️"},
    {"id": "biz_hangar", "name": "✈️ Hangar", "price": 125000, "type": "business", "desc": "Aircraft hangar.", "emoji": "✈️"},
    {"id": "biz_facility", "name": "🔬 Facility", "price": 210000, "type": "business", "desc": "High-tech facility.", "emoji": "🔬"},
]


# ── Cayo Perico Heist preparation items (buyable only inside Cayo panel) ──
CAYO_PREP_ITEMS: List[Dict[str, Any]] = [
    {"id": "cayo_longfin", "name": "🚤 Longfin Boat", "price": 900, "type": "cayo_prep", "desc": "Fast approach vessel for the island.", "emoji": "🚤"},
    {"id": "cayo_plasma", "name": "⚡ Plasma Cutter", "price": 700, "type": "cayo_prep", "desc": "Cuts through reinforced glass and metal.", "emoji": "⚡"},
    {"id": "cayo_fingerprint", "name": "🖐️ Fingerprint Clone", "price": 800, "type": "cayo_prep", "desc": "Clones biometric access prints.", "emoji": "🖐️"},
    {"id": "cayo_charges", "name": "💣 Demolition Charges", "price": 950, "type": "cayo_prep", "desc": "Controlled explosives for barriers.", "emoji": "💣"},
    {"id": "cayo_torch", "name": "🔥 Cutting Torch", "price": 550, "type": "cayo_prep", "desc": "Precision cutting tool.", "emoji": "🔥"},
]

CAYO_INVITE_ITEM = {
    "id": "cayo_invite",
    "name": "🎟️ Cayo Perico Invite",
    "type": "consumable",
    "desc": "One-time invitation to launch the Cayo Perico Heist.",
    "emoji": "🎟️",
}

CAYO_PREP_IDS = [it["id"] for it in CAYO_PREP_ITEMS]

# Heist quiz questions (Cayo Perico themed)
CAYO_QUIZ = [
    {
        "q": "What is the name of the island compound owned by El Rubio?",
        "options": ["Cayo Perico", "Los Santos Island", "Vice City Keys", "Sandy Shores"],
        "correct": 0,
    },
    {
        "q": "Which primary approach vehicle is ideal for a stealth entry to Cayo Perico?",
        "options": ["Rhino Tank", "Longfin Boat", "Buzzard Attack Heli", "Oppressor Mk II"],
        "correct": 1,
    },
]


# ── Casino Resort items ──
CASINO_PENTHOUSE = {
    "id": "casino_penthouse",
    "name": "🏨 Master Penthouse",
    "price": 320000,
    "type": "property",
    "desc": "Premium casino residence with private services and exclusive access.",
    "emoji": "🏨",
}

CASINO_MEMBERSHIP_TIERS = {
    "standard": {"name": "Standard", "emoji": "🃏", "price_key": "casino_membership_standard", "discount": 0.05},
    "vip": {"name": "VIP", "emoji": "💎", "price_key": "casino_membership_vip", "discount": 0.10},
    "diamond": {"name": "Diamond", "emoji": "👑", "price_key": "casino_membership_diamond", "discount": 0.15},
}

# Podium vehicles (rotating collection — fixed list for now, one can be "featured")
CASINO_PODIUM = [
    {"id": "podium_paragon", "name": "🏎️ Paragon R", "price": 28000, "type": "car", "desc": "Casino podium exclusive sports car.", "emoji": "🏎️", "dealer": "podium"},
    {"id": "podium_thrax", "name": "⚡ Thrax", "price": 45000, "type": "car", "desc": "Ultra-rare podium hypercar.", "emoji": "⚡", "dealer": "podium"},
    {"id": "podium_italirsx", "name": "🏁 Itali RSX", "price": 38000, "type": "car", "desc": "Podium Italian supercar.", "emoji": "🏁", "dealer": "podium"},
]

MUSIC_EVENTS = [
    "House Night",
    "Techno Night",
    "DJ Session",
    "Underground Party",
]

DEFAULT_SETTINGS = {
    "daily_amount": 300,
    "daily_streak_bonus": 30,   # per streak day
    "max_streak_bonus": 600,
    "work_min": 80,
    "work_max": 220,
    "work_cooldown": 21600,     # 6 hours
    "balance_cooldown": 1800,   # 30 minutes (public only)
    "daily_cooldown": 86400,    # 24 hours
    "min_bet": 10,
    "max_bet": 10000,
    "currency_name": CURRENCY,
    "motoclub_cooldown": 18000,  # 5 hours
    "ceo_cooldown": 18000,       # 5 hours
    "motoclub_reward_min": 320,
    "motoclub_reward_max": 850,
    "ceo_fast_reward_min": 450,
    "ceo_fast_reward_max": 1200,
    "ceo_safe_reward_min": 200,
    "ceo_safe_reward_max": 480,
    "ceo_premium_reward_min": 800,
    "ceo_premium_reward_max": 1800,
    "ceo_premium_cost": 200,
    "cayo_heist_prize_min": 4000,
    "cayo_heist_prize_max": 9000,
    # Casino
    "lucky_wheel_cooldown": 86400,
    "casino_membership_standard": 5000,
    "casino_membership_vip": 15000,
    "casino_membership_diamond": 40000,
    "casino_penthouse_price": 320000,
    # Music Locker
    "music_entry_fee": 50,
    "music_entry_reward": 80,
    "music_event_reward_min": 120,
    "music_event_reward_max": 280,
    "music_vip_price": 12000,
    "music_vip_bonus_mult": 1.5,
    "music_event_cooldown": 86400,
}

# Street / location names used in MotoClub route choices
MOTOCLUB_STREETS = [
    "Tongva Hills", "Sandy Shores", "Chumash", "East Vinewood",
    "Paleto Bay", "Grapeseed", "Harmony", "Grand Senora Desert",
    "La Mesa", "Cypress Flats", "El Burro Heights", "Mirror Park",
    "Rockford Hills", "Vinewood Hills", "Del Perro", "Vespucci Beach",
    "Legion Square", "Pillbox Hill", "Little Seoul", "Strawberry",
    "Rancho", "Davis", "Chamberlain Hills", "Banning",
    "Port of LS", "Elysian Island", "Terminal", "Murrieta Heights",
]

MOTOCLUB_PRODUCTS = [
    {"id": "weed", "name": "🌿 Weed", "emoji": "🌿"},
    {"id": "coke", "name": "❄️ Cocaine", "emoji": "❄️"},
    {"id": "meth", "name": "💎 Meth", "emoji": "💎"},
    {"id": "lsd", "name": "🌈 LSD", "emoji": "🌈"},
]


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
                "last_motoclub": 0,
                "last_ceo": 0,
                "last_lucky_wheel": 0,
                "last_music_event": 0,
                "casino_membership": None,
                "music_vip": False,
                "created_at": _now_ts(),
            }
            save_json(self.USERS_KEY, users)
        u = users[uid]
        u.setdefault("last_motoclub", 0)
        u.setdefault("last_ceo", 0)
        u.setdefault("last_lucky_wheel", 0)
        u.setdefault("last_music_event", 0)
        u.setdefault("casino_membership", None)
        u.setdefault("music_vip", False)
        return u

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
            BENNYS_SOUTHERN,
            BENNYS_LEGENDARY,
            BENNYS_LOST_MC,
            WARSTOCK_ITEMS,
            ELITAS_ITEMS,
            DOCKTEASE_ITEMS,
            DYNASTY8_ITEMS,
            FORECLOSURES_ITEMS,
            CAYO_PREP_ITEMS,
        ):
            for it in lst:
                items[it["id"]] = it
        items[CAYO_INVITE_ITEM["id"]] = CAYO_INVITE_ITEM
        items[CASINO_PENTHOUSE["id"]] = CASINO_PENTHOUSE
        for it in CASINO_PODIUM:
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
# MOTOCLUB MISSION VIEWS
# ═══════════════════════════════════════════════════════════════════════════

class MotoClubStartView(discord.ui.View):
    """Ephemeral menu to start a MotoClub product delivery."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        options = [
            discord.SelectOption(
                label=p["name"],
                value=p["id"],
                description=f"Deliver {p['name']}",
                emoji=p["emoji"],
            )
            for p in MOTOCLUB_PRODUCTS
        ]
        select = discord.ui.Select(placeholder="Choose product to deliver…", options=options)
        select.callback = self._start
        self.add_item(select)

    async def _start(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your mission.", ephemeral=True)
        product_id = interaction.data["values"][0]
        product = next((p for p in MOTOCLUB_PRODUCTS if p["id"] == product_id), None)
        if not product:
            return await interaction.response.send_message("Invalid product.", ephemeral=True)

        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_motoclub", 0))
        cd = settings.get("motoclub_cooldown", 18000)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ MotoClub Cooldown",
                description=f"You can start another delivery in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        view = MotoClubStageView(self.cog, self.user_id, product, stage=1)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class MotoClubStageView(discord.ui.View):
    """One stage of the delivery: pick a route (3 good / 1 bad)."""

    def __init__(self, cog: "Economy", user_id: int, product: Dict, stage: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        self.product = product
        self.stage = stage
        self.streets = random.sample(MOTOCLUB_STREETS, 4)
        self.bad_index = random.randint(0, 3)

        options = [
            discord.SelectOption(label=s, value=str(i), description=f"Route via {s}")
            for i, s in enumerate(self.streets)
        ]
        select = discord.ui.Select(placeholder="Choose your route…", options=options)
        select.callback = self._choose
        self.add_item(select)

    def build_embed(self) -> discord.Embed:
        stage_label = "Stage 1 of 2" if self.stage == 1 else "Stage 2 of 2 — Final stretch"
        dest = random.choice(["Paleto Bay", "Sandy Shores", "Grapeseed", "Harmony", "Chumash"])
        embed = discord.Embed(
            title=f"🏍️ MotoClub Delivery — {self.product['name']}",
            description=(
                f"**{stage_label}**\n\n"
                f"You have a delivery of **{self.product['name']}** heading to **{dest}**.\n"
                f"Which route do you take?\n\n"
                f"Choose carefully — one wrong turn ends the run."
            ),
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="MotoClub · 75% success chance per stage · 2 stages required")
        return embed

    async def _choose(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your mission.", ephemeral=True)
        choice = int(interaction.data["values"][0])
        if choice == self.bad_index:
            u = self.cog.data.get_user(self.user_id)
            u["last_motoclub"] = _now_ts()
            self.cog.data.save_user(self.user_id, u)
            embed = discord.Embed(
                title="💥 Delivery Failed",
                description=(
                    f"You took a wrong turn near **{self.streets[choice]}**.\n"
                    f"Cops spotted the load and the run is over.\n\n"
                    f"Better luck next time."
                ),
                color=COLOR_FAIL,
            )
            embed.set_footer(text="MotoClub · Cooldown started")
            return await interaction.response.edit_message(embed=embed, view=None)

        if self.stage == 1:
            next_view = MotoClubStageView(self.cog, self.user_id, self.product, stage=2)
            embed = next_view.build_embed()
            return await interaction.response.edit_message(embed=embed, view=next_view)

        settings = self.cog.data.get_settings()
        reward = random.randint(
            settings.get("motoclub_reward_min", 280),
            settings.get("motoclub_reward_max", 750),
        )
        u = self.cog.data.get_user(self.user_id)
        u["last_motoclub"] = _now_ts()
        self.cog.data.save_user(self.user_id, u)
        self.cog.data.add_money(self.user_id, reward, "motoclub")
        embed = discord.Embed(
            title="✅ Delivery Successful!",
            description=(
                f"You delivered **{self.product['name']}** safely through both checkpoints.\n\n"
                f"Reward: **{_fmt(reward)}** {CURRENCY}"
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="MotoClub · Cooldown started (5h)")
        await interaction.response.edit_message(embed=embed, view=None)
        public = discord.Embed(
            title="🏍️ MotoClub Delivery Complete",
            description=f"{interaction.user.mention} successfully delivered **{self.product['name']}** and earned **{_fmt(reward)}** {CURRENCY}!",
            color=COLOR_SUCCESS,
        )
        await post_to_market(self.cog.bot, interaction.user, public)


# ═══════════════════════════════════════════════════════════════════════════
# CEO SECURO SERV MISSION VIEW
# ═══════════════════════════════════════════════════════════════════════════

class CEOMissionView(discord.ui.View):
    """Choose acquisition route: Fast / Safe / Premium."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="⚡ Fast Route", style=discord.ButtonStyle.danger, row=0)
    async def fast(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "fast")

    @discord.ui.button(label="🛡️ Safe Route", style=discord.ButtonStyle.success, row=0)
    async def safe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "safe")

    @discord.ui.button(label="💎 Premium Transport", style=discord.ButtonStyle.primary, row=0)
    async def premium(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "premium")

    async def _resolve(self, interaction: discord.Interaction, route: str):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your mission.", ephemeral=True)

        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_ceo", 0))
        cd = settings.get("ceo_cooldown", 18000)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ CEO SecuroServ Cooldown",
                description=f"You can start another acquisition in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.edit_message(embed=embed, view=None)

        if route == "fast":
            success_chance = 0.40
            cost = 0
            rmin = settings.get("ceo_fast_reward_min", 400)
            rmax = settings.get("ceo_fast_reward_max", 1100)
            route_name = "Fast Route"
            time_desc = "Quick but risky"
        elif route == "safe":
            success_chance = 0.80
            cost = 0
            rmin = settings.get("ceo_safe_reward_min", 180)
            rmax = settings.get("ceo_safe_reward_max", 420)
            route_name = "Safe Route"
            time_desc = "Slow and steady"
        else:
            success_chance = 0.90
            cost = settings.get("ceo_premium_cost", 150)
            rmin = settings.get("ceo_premium_reward_min", 700)
            rmax = settings.get("ceo_premium_reward_max", 1600)
            route_name = "Premium Transport"
            time_desc = "Expensive, high success"

        if cost > 0 and u["wallet"] < cost:
            embed = discord.Embed(
                title="💸 Insufficient Funds",
                description=f"Premium Transport costs **{_fmt(cost)}** {CURRENCY}. You only have **{_fmt(u['wallet'])}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.edit_message(embed=embed, view=None)

        if cost > 0:
            self.cog.data.add_money(self.user_id, -cost, "ceo_premium_cost")

        success = random.random() < success_chance
        u = self.cog.data.get_user(self.user_id)
        u["last_ceo"] = now
        self.cog.data.save_user(self.user_id, u)

        if success:
            reward = random.randint(rmin, rmax)
            self.cog.data.add_money(self.user_id, reward, "ceo_securo")
            embed = discord.Embed(
                title="✅ Acquisition Successful!",
                description=(
                    f"**{route_name}** ({time_desc})\n\n"
                    f"Merchandise secured.\n"
                    f"Reward: **{_fmt(reward)}** {CURRENCY}"
                    + (f"\nCost paid: **{_fmt(cost)}** {CURRENCY}" if cost else "")
                ),
                color=COLOR_SUCCESS,
            )
            embed.set_footer(text="CEO SecuroServ · Cooldown started (5h)")
            await interaction.response.edit_message(embed=embed, view=None)
            public = discord.Embed(
                title="💼 CEO SecuroServ — Acquisition Complete",
                description=f"{interaction.user.mention} completed a **{route_name}** acquisition and earned **{_fmt(reward)}** {CURRENCY}!",
                color=COLOR_SUCCESS,
            )
            await post_to_market(self.cog.bot, interaction.user, public)
        else:
            embed = discord.Embed(
                title="💥 Acquisition Failed",
                description=(
                    f"**{route_name}** went wrong.\n"
                    f"The shipment was compromised or intercepted.\n\n"
                    + (f"You lost the **{_fmt(cost)}** premium fee." if cost else "No payout this time.")
                ),
                color=COLOR_FAIL,
            )
            embed.set_footer(text="CEO SecuroServ · Cooldown started (5h)")
            await interaction.response.edit_message(embed=embed, view=None)



# ═══════════════════════════════════════════════════════════════════════════
# CAYO PERICO HEIST SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

def _has_submarine(u: Dict) -> bool:
    inv = u.get("inventory", {})
    return inv.get("mil_submarine", 0) >= 1


def _cayo_prep_progress(u: Dict) -> Tuple[int, List[str]]:
    inv = u.get("inventory", {})
    owned = []
    missing = []
    for it in CAYO_PREP_ITEMS:
        if inv.get(it["id"], 0) >= 1:
            owned.append(it["id"])
        else:
            missing.append(it["id"])
    return len(owned), missing


class CayoMainView(discord.ui.View):
    """Main Cayo Perico panel (ephemeral)."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self, u: Dict) -> discord.Embed:
        inv = u.get("inventory", {})
        lines = []
        for it in CAYO_PREP_ITEMS:
            qty = inv.get(it["id"], 0)
            status = "✅" if qty >= 1 else "❌"
            lines.append(
                f"{status} {it.get('emoji', '')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                + (f" (owned ×{qty})" if qty else "")
            )
        owned_count, missing = _cayo_prep_progress(u)
        invite_qty = inv.get("cayo_invite", 0)
        embed = discord.Embed(
            title="🏝️ Cayo Perico Heist",
            description=(
                "Prepare your gear, deliver the full set to receive an **Invite**, "
                "then launch the Heist for a big payout.\n\n"
                f"**Prep progress:** {owned_count}/5 items\n"
                f"**Invites owned:** {invite_qty}\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_LIGHT_BLUE,
        )
        embed.set_footer(text="Requires Kosatka Submarine · All actions private")
        return embed

    @discord.ui.button(label="🛒 Buy Prep Items", style=discord.ButtonStyle.primary, row=0)
    async def buy_prep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your panel.", ephemeral=True)
        view = CayoBuyView(self.cog, self.user_id)
        embed = discord.Embed(
            title="🛒 Cayo Perico — Prep Shop",
            description="Select an item to purchase. You need **all 5** to deliver for an Invite.",
            color=COLOR_LIGHT_BLUE,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📦 Deliver Prep Set", style=discord.ButtonStyle.success, row=0)
    async def deliver(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your panel.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        owned_count, missing = _cayo_prep_progress(u)
        if owned_count < 5:
            names = []
            for it in CAYO_PREP_ITEMS:
                if it["id"] in missing:
                    names.append(it["name"])
            embed = discord.Embed(
                title="📦 Incomplete Set",
                description=(
                    f"You still need:\n• " + "\n• ".join(names)
                    + "\n\nBuy the missing items first."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        inv = u.get("inventory", {})
        for iid in CAYO_PREP_IDS:
            inv[iid] = max(0, inv.get(iid, 0) - 1)
            if inv[iid] == 0:
                inv.pop(iid, None)
        inv["cayo_invite"] = inv.get("cayo_invite", 0) + 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)

        embed = discord.Embed(
            title="✅ Prep Set Delivered!",
            description=(
                "You handed over the full preparation kit.\n\n"
                f"Received: **🎟️ Cayo Perico Invite** ×1\n"
                f"Invites now: **{inv['cayo_invite']}**\n\n"
                "Use **Launch Heist** when you are ready."
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🚀 Launch Heist", style=discord.ButtonStyle.danger, row=0)
    async def launch(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your panel.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        if inv.get("cayo_invite", 0) < 1:
            embed = discord.Embed(
                title="🎟️ No Invite",
                description="You need a **Cayo Perico Invite**. Deliver a full prep set first.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Consume invite
        inv["cayo_invite"] -= 1
        if inv["cayo_invite"] <= 0:
            inv.pop("cayo_invite", None)
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)

        # Start quiz stage 1
        view = CayoQuizView(self.cog, self.user_id, stage=0)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CayoBuyView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        options = []
        for it in CAYO_PREP_ITEMS:
            options.append(discord.SelectOption(
                label=f"{it.get('emoji', '')} {it['name']}"[:100],
                value=it["id"],
                description=f"{_fmt(it['price'])} {CURRENCY}"[:100],
            ))
        select = discord.ui.Select(placeholder="Choose prep item to buy…", options=options)
        select.callback = self._buy
        self.add_item(select)

    async def _buy(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your shop.", ephemeral=True)
        item_id = interaction.data["values"][0]
        item = next((it for it in CAYO_PREP_ITEMS if it["id"] == item_id), None)
        if not item:
            return await interaction.response.send_message("Item not found.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        if u["wallet"] < item["price"]:
            return await interaction.response.send_message(
                f"Insufficient balance. You need {_fmt(item['price'])} {CURRENCY}.",
                ephemeral=True,
            )
        self.cog.data.add_money(self.user_id, -item["price"], "cayo_prep_buy")
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        inv[item_id] = inv.get(item_id, 0) + 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)
        owned, _ = _cayo_prep_progress(u)
        embed = discord.Embed(
            title="✅ Purchase Successful",
            description=(
                f"You bought **{item.get('emoji', '')} {item['name']}** "
                f"for **{_fmt(item['price'])}** {CURRENCY}.\n\n"
                f"Prep progress: **{owned}/5**"
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CayoQuizView(discord.ui.View):
    """Stages 0 and 1: multiple-choice quiz. Stage 2: reward choice."""

    def __init__(self, cog: "Economy", user_id: int, stage: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.stage = stage  # 0, 1, or 2

        if stage < 2:
            qdata = CAYO_QUIZ[stage]
            options = [
                discord.SelectOption(label=opt[:100], value=str(i))
                for i, opt in enumerate(qdata["options"])
            ]
            select = discord.ui.Select(placeholder="Choose your answer…", options=options)
            select.callback = self._answer
            self.add_item(select)
        else:
            # Final reward choice — 4 buttons (one random bag is 40%, rest 20%)
            pcts = [0.20, 0.20, 0.20, 0.40]
            random.shuffle(pcts)
            for label, pct in zip("ABCD", pcts):
                self.add_item(CayoRewardButton(self.cog, self.user_id, label, pct))

    def build_embed(self) -> discord.Embed:
        if self.stage < 2:
            qdata = CAYO_QUIZ[self.stage]
            embed = discord.Embed(
                title=f"🏝️ Cayo Perico Heist — Question {self.stage + 1}/2",
                description=f"**{qdata['q']}**\n\nSelect the correct answer below.",
                color=COLOR_LIGHT_BLUE,
            )
            embed.set_footer(text="Wrong answer ends the heist with no payout")
            return embed
        embed = discord.Embed(
            title="🏝️ Cayo Perico Heist — Final Score!",
            description=(
                "You reached the compound vault.\n\n"
                "Choose one of the **4 loot bags**. All are wins:\n"
                "• Three bags contain **20%** of the total prize\n"
                "• One bag contains **40%** of the total prize\n\n"
                "Pick wisely — the values are hidden."
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="All choices are successful — higher % is better")
        return embed

    async def _answer(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your heist.", ephemeral=True)
        choice = int(interaction.data["values"][0])
        qdata = CAYO_QUIZ[self.stage]
        if choice != qdata["correct"]:
            embed = discord.Embed(
                title="💥 Heist Failed",
                description=(
                    f"Wrong answer.\n"
                    f"Correct was: **{qdata['options'][qdata['correct']]}**\n\n"
                    "The guards were alerted. No payout this run."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.edit_message(embed=embed, view=None)

        next_stage = self.stage + 1
        next_view = CayoQuizView(self.cog, self.user_id, stage=next_stage)
        embed = next_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=next_view)


class CayoRewardButton(discord.ui.Button):
    def __init__(self, cog: "Economy", user_id: int, label: str, pct: float):
        super().__init__(label=f"Loot Bag {label}", style=discord.ButtonStyle.primary)
        self.cog = cog
        self.user_id = user_id
        self.pct = pct

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your heist.", ephemeral=True)
        settings = self.cog.data.get_settings()
        total = random.randint(
            settings.get("cayo_heist_prize_min", 3500),
            settings.get("cayo_heist_prize_max", 7500),
        )
        reward = int(total * self.pct)
        self.cog.data.add_money(self.user_id, reward, "cayo_heist")
        embed = discord.Embed(
            title="🏆 Heist Complete!",
            description=(
                f"You grabbed **Loot Bag** and escaped Cayo Perico!\n\n"
                f"Total heist value: **{_fmt(total)}** {CURRENCY}\n"
                f"Your share (**{int(self.pct*100)}%**): **{_fmt(reward)}** {CURRENCY}"
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Cayo Perico Heist · Invite consumed")
        await interaction.response.edit_message(embed=embed, view=None)
        public = discord.Embed(
            title="🏝️ Cayo Perico Heist Successful",
            description=f"{interaction.user.mention} completed the Cayo Perico Heist and earned **{_fmt(reward)}** {CURRENCY}!",
            color=COLOR_SUCCESS,
        )
        await post_to_market(self.cog.bot, interaction.user, public)



# ═══════════════════════════════════════════════════════════════════════════
# MEMBER PANEL VIEW (persistent)

# ═══════════════════════════════════════════════════════════════════════════
# CASINO RESORT
# ═══════════════════════════════════════════════════════════════════════════

class CasinoMainView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self, u: Dict) -> discord.Embed:
        settings = self.cog.data.get_settings()
        inv = u.get("inventory", {})
        membership = u.get("casino_membership")
        mem_txt = "None"
        if membership and membership in CASINO_MEMBERSHIP_TIERS:
            t = CASINO_MEMBERSHIP_TIERS[membership]
            mem_txt = f"{t['emoji']} {t['name']}"
        has_ph = inv.get("casino_penthouse", 0) >= 1
        embed = discord.Embed(
            title="🎰 Diamond Casino & Resort",
            description=(
                "Welcome to the most luxurious establishment in Los Santos.\n\n"
                f"**Membership:** {mem_txt}\n"
                f"**Master Penthouse:** {'✅ Owned' if has_ph else '❌ Not owned'}\n\n"
                "• **Lucky Wheel** — one spin per day\n"
                "• **Membership** — Standard / VIP / Diamond perks\n"
                "• **Podium Collection** — exclusive vehicles\n"
                "• **Master Penthouse** — premium residence"
            ),
            color=COLOR_CASINO,
        )
        embed.set_footer(text="Casino Resort · All actions private")
        return embed

    @discord.ui.button(label="🎡 Lucky Wheel", style=discord.ButtonStyle.primary, row=0)
    async def lucky_wheel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_lucky_wheel", 0))
        cd = settings.get("lucky_wheel_cooldown", 86400)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ Lucky Wheel Cooldown",
                description=f"You can spin again in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        u["last_lucky_wheel"] = now
        self.cog.data.save_user(self.user_id, u)

        # Weighted rewards — vehicle is rare (~3%)
        roll = random.random()
        if roll < 0.03:
            # Podium vehicle (random from list if not owned, else cash)
            candidates = [p for p in CASINO_PODIUM if u.get("inventory", {}).get(p["id"], 0) < 1]
            if candidates:
                prize = random.choice(candidates)
                inv = u.get("inventory", {})
                inv[prize["id"]] = 1
                u["inventory"] = inv
                self.cog.data.save_user(self.user_id, u)
                embed = discord.Embed(
                    title="🎡 JACKPOT — Podium Vehicle!",
                    description=f"The wheel landed on **{prize.get('emoji','🏎️')} {prize['name']}**!\nIt has been added to your Garage.",
                    color=COLOR_SUCCESS,
                )
            else:
                amt = random.randint(2500, 5000)
                self.cog.data.add_money(self.user_id, amt, "lucky_wheel")
                embed = discord.Embed(
                    title="🎡 Big Cash Win!",
                    description=f"You already own the podium cars.\nReceived **{_fmt(amt)}** {CURRENCY} instead!",
                    color=COLOR_SUCCESS,
                )
        elif roll < 0.18:
            amt = random.randint(800, 1800)
            self.cog.data.add_money(self.user_id, amt, "lucky_wheel")
            embed = discord.Embed(
                title="🎡 Lucky Wheel — Cash",
                description=f"You won **{_fmt(amt)}** {CURRENCY}!",
                color=COLOR_SUCCESS,
            )
        elif roll < 0.40:
            amt = random.randint(200, 500)
            self.cog.data.add_money(self.user_id, amt, "lucky_wheel")
            embed = discord.Embed(
                title="🎡 Lucky Wheel — Small Cash",
                description=f"You won **{_fmt(amt)}** {CURRENCY}.",
                color=COLOR_INFO,
            )
        elif roll < 0.55:
            embed = discord.Embed(
                title="🎡 Lucky Wheel — Cosmetic Chip",
                description="You won a **Decoration Chip** (cosmetic collectible).\n*Chips are tracked as a fun flex — no mechanical effect yet.*",
                color=COLOR_INFO,
            )
            inv = u.get("inventory", {})
            inv["casino_chip"] = inv.get("casino_chip", 0) + 1
            u["inventory"] = inv
            self.cog.data.save_user(self.user_id, u)
        else:
            embed = discord.Embed(
                title="🎡 Lucky Wheel — Better Luck Next Time",
                description="The wheel stopped on nothing this time.\nCome back tomorrow!",
                color=COLOR_FAIL,
            )
        embed.set_footer(text="Lucky Wheel · 1 spin per day")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🃏 Membership", style=discord.ButtonStyle.secondary, row=0)
    async def membership(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        current = u.get("casino_membership")
        lines = []
        for key, tier in CASINO_MEMBERSHIP_TIERS.items():
            price = settings.get(tier["price_key"], 0)
            owned = "✅" if current == key else ""
            lines.append(
                f"{tier['emoji']} **{tier['name']}** — {_fmt(price)} {CURRENCY} "
                f"({int(tier['discount']*100)}% shop discount) {owned}"
            )
        embed = discord.Embed(
            title="🃏 Casino Membership",
            description=(
                "Higher tiers unlock better discounts and prestige.\n"
                "Purchasing a higher tier replaces your current one.\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_CASINO,
        )
        view = CasinoMembershipView(self.cog, self.user_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏎️ Podium Collection", style=discord.ButtonStyle.primary, row=1)
    async def podium(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        lines = [
            f"{it.get('emoji','🏎️')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
            for it in CASINO_PODIUM
        ]
        embed = discord.Embed(
            title="🏎️ Podium Collection",
            description=(
                "Exclusive vehicles displayed on the casino podium.\n"
                "Collection rotates periodically in future updates.\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_CASINO,
        )
        embed.set_footer(text="Select below to purchase · Private")
        view = ShopBuyView(self.cog, self.user_id, CASINO_PODIUM, "Podium Collection")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏨 Master Penthouse", style=discord.ButtonStyle.success, row=1)
    async def penthouse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        price = settings.get("casino_penthouse_price", CASINO_PENTHOUSE["price"])
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        if inv.get("casino_penthouse", 0) >= 1:
            embed = discord.Embed(
                title="🏨 Master Penthouse",
                description="You already own the **Master Penthouse**.\nEnjoy private services and exclusive casino access.",
                color=COLOR_SUCCESS,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        if u["wallet"] < price:
            embed = discord.Embed(
                title="💸 Insufficient Funds",
                description=f"Master Penthouse costs **{_fmt(price)}** {CURRENCY}.\nYou have **{_fmt(u['wallet'])}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        self.cog.data.add_money(self.user_id, -price, "casino_penthouse")
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        inv["casino_penthouse"] = 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)
        embed = discord.Embed(
            title="🏨 Welcome Home!",
            description=(
                f"You purchased the **Master Penthouse** for **{_fmt(price)}** {CURRENCY}.\n\n"
                "Private elevators, exclusive lounges and the best view of the Strip are yours."
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CasinoMembershipView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        options = [
            discord.SelectOption(
                label=f"{t['emoji']} {t['name']}",
                value=key,
                description=f"{int(t['discount']*100)}% discount",
            )
            for key, t in CASINO_MEMBERSHIP_TIERS.items()
        ]
        select = discord.ui.Select(placeholder="Choose membership tier…", options=options)
        select.callback = self._buy
        self.add_item(select)

    async def _buy(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        key = interaction.data["values"][0]
        tier = CASINO_MEMBERSHIP_TIERS[key]
        settings = self.cog.data.get_settings()
        price = settings.get(tier["price_key"], 0)
        u = self.cog.data.get_user(self.user_id)
        if u.get("casino_membership") == key:
            return await interaction.response.send_message(
                f"You already have **{tier['name']}** membership.", ephemeral=True
            )
        if u["wallet"] < price:
            return await interaction.response.send_message(
                f"Need **{_fmt(price)}** {CURRENCY}. You have **{_fmt(u['wallet'])}**.",
                ephemeral=True,
            )
        self.cog.data.add_money(self.user_id, -price, "casino_membership")
        u = self.cog.data.get_user(self.user_id)
        u["casino_membership"] = key
        self.cog.data.save_user(self.user_id, u)
        embed = discord.Embed(
            title=f"{tier['emoji']} Membership Upgraded",
            description=(
                f"You are now a **{tier['name']}** member.\n"
                f"Shop discount: **{int(tier['discount']*100)}%**\n"
                f"Paid: **{_fmt(price)}** {CURRENCY}"
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
# MUSIC LOCKER
# ═══════════════════════════════════════════════════════════════════════════

class MusicLockerView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self, u: Dict) -> discord.Embed:
        settings = self.cog.data.get_settings()
        is_vip = bool(u.get("music_vip"))
        # Event of the day (stable per calendar day)
        day_index = int(_now_ts() // 86400) % len(MUSIC_EVENTS)
        event_name = MUSIC_EVENTS[day_index]
        embed = discord.Embed(
            title="🎵 The Music Locker",
            description=(
                "**Los Santos · Underground Nightlife**\n\n"
                f"Tonight's event: **{event_name}**\n"
                f"VIP Access: {'✅ Unlocked (free entry + bonus rewards)' if is_vip else '❌ Not unlocked'}\n\n"
                f"• **Enter Club** — pay {_fmt(settings.get('music_entry_fee', 50))} "
                f"(free for VIP) · small presence bonus\n"
                f"• **Join Event** — daily musical event reward (1× / day)\n"
                f"• **Unlock VIP** — permanent VIP for {_fmt(settings.get('music_vip_price', 12000))} {CURRENCY}"
            ),
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="Music Locker · Underground · Private")
        return embed

    @discord.ui.button(label="🚪 Enter Club", style=discord.ButtonStyle.primary, row=0)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        fee = settings.get("music_entry_fee", 50)
        reward = settings.get("music_entry_reward", 80)
        is_vip = bool(u.get("music_vip"))
        if not is_vip:
            if u["wallet"] < fee:
                return await interaction.response.send_message(
                    f"Entry costs **{_fmt(fee)}** {CURRENCY}.", ephemeral=True
                )
            self.cog.data.add_money(self.user_id, -fee, "music_entry")
        self.cog.data.add_money(self.user_id, reward, "music_presence")
        net = reward if is_vip else reward - fee
        embed = discord.Embed(
            title="🎵 Welcome to The Music Locker",
            description=(
                ("VIP entry — free. " if is_vip else f"Paid **{_fmt(fee)}** entry. ")
                + f"Presence bonus: **{_fmt(reward)}** {CURRENCY}.\n"
                f"Net: **{_fmt(net)}** {CURRENCY}."
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎧 Join Event", style=discord.ButtonStyle.success, row=0)
    async def event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_music_event", 0))
        cd = settings.get("music_event_cooldown", 86400)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ Event Cooldown",
                description=f"You already enjoyed tonight's event.\nCome back in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        day_index = int(now // 86400) % len(MUSIC_EVENTS)
        event_name = MUSIC_EVENTS[day_index]
        rmin = settings.get("music_event_reward_min", 120)
        rmax = settings.get("music_event_reward_max", 280)
        reward = random.randint(rmin, rmax)
        if u.get("music_vip"):
            mult = settings.get("music_vip_bonus_mult", 1.5)
            reward = int(reward * mult)

        u["last_music_event"] = now
        self.cog.data.save_user(self.user_id, u)
        self.cog.data.add_money(self.user_id, reward, "music_event")

        embed = discord.Embed(
            title=f"🎧 {event_name}",
            description=(
                f"You spent the night on the floor at **{event_name}**.\n\n"
                f"Reward: **{_fmt(reward)}** {CURRENCY}"
                + (" (VIP bonus applied)" if u.get("music_vip") else "")
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Music Locker · Daily event")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        public = discord.Embed(
            title="🎵 Music Locker",
            description=f"{interaction.user.mention} hit **{event_name}** and earned **{_fmt(reward)}** {CURRENCY}!",
            color=COLOR_PURPLE,
        )
        await post_to_market(self.cog.bot, interaction.user, public)

    @discord.ui.button(label="⭐ Unlock VIP", style=discord.ButtonStyle.secondary, row=0)
    async def vip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        if u.get("music_vip"):
            return await interaction.response.send_message(
                "You already have permanent **VIP Access**.", ephemeral=True
            )
        price = settings.get("music_vip_price", 12000)
        if u["wallet"] < price:
            return await interaction.response.send_message(
                f"VIP costs **{_fmt(price)}** {CURRENCY}. You have **{_fmt(u['wallet'])}**.",
                ephemeral=True,
            )
        self.cog.data.add_money(self.user_id, -price, "music_vip")
        u = self.cog.data.get_user(self.user_id)
        u["music_vip"] = True
        self.cog.data.save_user(self.user_id, u)
        embed = discord.Embed(
            title="⭐ VIP Access Unlocked",
            description=(
                f"Permanent VIP for **{_fmt(price)}** {CURRENCY}.\n"
                "• Free club entry\n"
                "• +50% event rewards\n"
                "• Prestige status at The Music Locker"
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)



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

    async def _under_construction(self, interaction: discord.Interaction, title: str, extra: str = ""):
        embed = discord.Embed(
            title=title,
            description=(
                "**Under Construction** 🚧\n\n"
                "This feature is currently being developed.\n"
                "Check back later for updates!"
                + (f"\n\n{extra}" if extra else "")
            ),
            color=COLOR_CONSTRUCTION,
        )
        embed.set_footer(text=f"Bovary Economy · {title} · Coming Soon")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Row 0 — Core actions (green) ──
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

    @discord.ui.button(label="💼 Work", style=discord.ButtonStyle.success, custom_id="eco_work", row=0)
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

    @discord.ui.button(label="💰 Balance", style=discord.ButtonStyle.success, custom_id="eco_balance", row=0)
    async def btn_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = VisibilityChoiceView(self.cog, "balance", interaction.user.id)
        embed = discord.Embed(
            title="💰 Balance",
            description="Choose how you want to view your balance:",
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="💸 Pay", style=discord.ButtonStyle.success, custom_id="eco_pay", row=0)
    async def btn_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PayModal(self.cog))

    # ── Row 1 — Blue shops ──
    @discord.ui.button(label="🏎️ Benny's Workshop", style=discord.ButtonStyle.primary, custom_id="eco_bennys", row=1)
    async def btn_bennys(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "bennys")

    @discord.ui.button(label="✈️ Elitas Travel", style=discord.ButtonStyle.primary, custom_id="eco_elitas", row=1)
    async def btn_elitas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "elitas")

    # ── Row 2 — Red shops ──
    @discord.ui.button(label="🪖 Warstock", style=discord.ButtonStyle.danger, custom_id="eco_warstock", row=2)
    async def btn_warstock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "warstock")

    @discord.ui.button(label="🚤 DockTease", style=discord.ButtonStyle.danger, custom_id="eco_docktease", row=2)
    async def btn_docktease(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "docktease")

    # ── Row 3 — Yellow / Lilac ──
    @discord.ui.button(label="🎰 Casino Resort", style=discord.ButtonStyle.secondary, custom_id="eco_casino", row=3)
    async def btn_casino(self, interaction: discord.Interaction, button: discord.ui.Button):
        u = self.cog.data.get_user(interaction.user.id)
        view = CasinoMainView(self.cog, interaction.user.id)
        embed = view.build_embed(u)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🎵 Music Locker", style=discord.ButtonStyle.secondary, custom_id="eco_musiclocker", row=3)
    async def btn_musiclocker(self, interaction: discord.Interaction, button: discord.ui.Button):
        u = self.cog.data.get_user(interaction.user.id)
        view = MusicLockerView(self.cog, interaction.user.id)
        embed = view.build_embed(u)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏠 Dynasty8", style=discord.ButtonStyle.secondary, custom_id="eco_dynasty8", row=3)
    async def btn_dynasty8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "dynasty8")

    @discord.ui.button(label="🏦 Maze Bank", style=discord.ButtonStyle.secondary, custom_id="eco_mazebank", row=3)
    async def btn_mazebank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "foreclosures")

    @discord.ui.button(label="🏝️ Cayo Perico Heist", style=discord.ButtonStyle.primary, custom_id="eco_cayo", row=3)
    async def btn_cayo(self, interaction: discord.Interaction, button: discord.ui.Button):
        u = self.cog.data.get_user(interaction.user.id)
        if not _has_submarine(u):
            embed = discord.Embed(
                title="🚢 Submarine Required",
                description=(
                    "You need a **Kosatka Submarine** in your inventory to access Cayo Perico Heist.\n\n"
                    "Buy it at **Warstock Cache & Carry** (permanent item)."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        view = CayoMainView(self.cog, interaction.user.id)
        embed = view.build_embed(u)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── Row 4 — Missions + utility + extras ──
    @discord.ui.button(label="💼 CEO SecuroServ", style=discord.ButtonStyle.secondary, custom_id="eco_ceo", row=2)
    async def btn_ceo(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(interaction.user.id)
        now = _now_ts()
        last = float(u.get("last_ceo", 0))
        cd = settings.get("ceo_cooldown", 18000)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ CEO SecuroServ Cooldown",
                description=f"You can start another acquisition in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title="💼 CEO SecuroServ — Merchandise Acquisition",
            description=(
                "Choose your acquisition method:\n\n"
                "⚡ **Fast Route** — High risk, high reward (≈40% success)\n"
                "🛡️ **Safe Route** — Lower payout, reliable (≈80% success)\n"
                "💎 **Premium Transport** — Costs coins upfront, best odds (≈90% success)\n\n"
                "Cooldown: **5 hours** after each attempt."
            ),
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="CEO SecuroServ · Ephemeral · Only you can see this")
        view = CEOMissionView(self.cog, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏍️ MotoClub", style=discord.ButtonStyle.secondary, custom_id="eco_motoclub", row=2)
    async def btn_motoclub(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(interaction.user.id)
        now = _now_ts()
        last = float(u.get("last_motoclub", 0))
        cd = settings.get("motoclub_cooldown", 18000)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ MotoClub Cooldown",
                description=f"You can start another delivery in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title="🏍️ MotoClub — Product Delivery",
            description=(
                "Select a product to deliver. You must pass **two route stages**.\n"
                "Each stage has 4 route options — **3 correct, 1 wrong** (75% chance).\n"
                "One wrong choice fails the entire run.\n\n"
                "Products: Weed · Cocaine · Meth · LSD\n"
                "Cooldown: **5 hours** after each attempt."
            ),
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="MotoClub · Ephemeral · Only you can see this")
        view = MotoClubStartView(self.cog, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="❓ Help", style=discord.ButtonStyle.secondary, custom_id="eco_help", row=4)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❓ Bovary Economy — Help",
            description=(
                f"**Currency:** {CURRENCY_EMOJI} {CURRENCY}\n\n"
                "**Core (green):** Daily · Work · Balance · Pay\n\n"
                "**Shops:** Benny's (cars + Lost MC) · Elitas · Warstock · DockTease · Dynasty8 · Maze Bank\n\n"
                "**Lifestyle:** Casino Resort (Lucky Wheel, Membership, Podium, Penthouse) · Music Locker (events + VIP)\n\n"
                "**Missions (5h):** CEO SecuroServ · MotoClub\n"
                "**Cayo Perico Heist:** needs Kosatka Submarine\n\n"
                "**Utility:** Inventory · Garage · Ranking (private or public)\n\n"
                "Cooldowns and shops are always private."
            ),
            color=COLOR_INFO,
        )
        embed.set_footer(text="Bovary Economy")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎒 Inventory", style=discord.ButtonStyle.secondary, custom_id="eco_inv", row=4)
    async def btn_inv(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = VisibilityChoiceView(self.cog, "inventory", interaction.user.id)
        embed = discord.Embed(
            title="🎒 Inventory",
            description="Choose how you want to view your inventory:",
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🚗 Garage", style=discord.ButtonStyle.secondary, custom_id="eco_garage", row=4)
    async def btn_garage(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = VisibilityChoiceView(self.cog, "garage", interaction.user.id)
        embed = discord.Embed(
            title="🚗 Garage",
            description="Choose how you want to view your garage:",
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏆 Ranking", style=discord.ButtonStyle.secondary, custom_id="eco_lb", row=4)
    async def btn_lb(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = VisibilityChoiceView(self.cog, "leaderboard", interaction.user.id)
        embed = discord.Embed(
            title="🏆 Ranking",
            description="Choose how you want to view the ranking:",
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


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

        if action == "bennys":
            embed = discord.Embed(
                title="🏎️ Benny's Original Motor Workshop",
                description="Premium vehicles and motorcycles from Los Santos dealers.",
                color=COLOR_MAIN,
            )
            southern_lines = [
                f"{it.get('emoji','🚗')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in BENNYS_SOUTHERN
            ]
            embed.add_field(
                name="🏁 Southern San Andreas Super Autos",
                value="\n".join(southern_lines) or "—",
                inline=False,
            )
            legendary_lines = [
                f"{it.get('emoji','🚗')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in BENNYS_LEGENDARY
            ]
            embed.add_field(
                name="🏆 Legendary Motorsport",
                value="\n".join(legendary_lines) or "—",
                inline=False,
            )
            lost_lines = [
                f"{it.get('emoji','🏍️')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in BENNYS_LOST_MC
            ]
            embed.add_field(
                name="☠️ Lost MC Shop",
                value="\n".join(lost_lines) or "—",
                inline=False,
            )
            embed.set_footer(text="Select below to purchase · Private view only")
            all_cars = BENNYS_SOUTHERN + BENNYS_LEGENDARY + BENNYS_LOST_MC
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

        if action == "garage":
            inv = u.get("inventory", {})
            all_items = self.data.get_all_items()
            cars = []
            for iid, qty in inv.items():
                item = all_items.get(iid, {})
                itype = item.get("type", "")
                if itype in ("car", "motorcycle") or item.get("dealer") in ("southern", "legendary", "lost_mc"):
                    name = item.get("name", iid)
                    emoji = item.get("emoji", "🚗")
                    cars.append(f"{emoji} **{name}** ×{qty}")
            if not cars:
                embed = discord.Embed(
                    title="🚗 Empty Garage",
                    description="You don't own any vehicles yet.\nBuy cars and bikes at **Benny's Workshop**!",
                    color=COLOR_INFO,
                )
                return embed, None
            embed = discord.Embed(
                title=f"🚗 {interaction.user.display_name}'s Garage",
                description="\n".join(cars),
                color=COLOR_MAIN,
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Bovary Economy · Garage")
            return embed, None

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
                "• Daily, Work, Balance & Pay\n"
                "• Shops: Benny's, Elitas, Warstock, DockTease, Dynasty8, Maze Bank\n"
                "• Missions: CEO SecuroServ & MotoClub\n"
                "• Inventory, Garage, Help & more\n\n"
                "🔒 Cooldown messages and shops are always private."
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
