"""
GTA Economy — complete economy system for Bova's Bot.
Currency: Bovas coins
Main panel (members): Maze Bank channel (panel)
Member responses: Bovary Market channel
Admin panel [LOCKED]: Bank Admin channel
Bank deposits handled by Maze Bank (wallet + bank balance)
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
from utils.helpers import make_embed

logger = logging.getLogger("bovary_bot.economy")

# Simple lock to reduce race conditions on JSON file I/O
_economy_lock = asyncio.Lock()

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

# ── Local GIF assets (place these files in assets/ at bot root) ──────────────
# mission_passed.gif | lose_game.gif | cayo_perico_heist.gif
# musiclocker_technonight_response.gif | mainpanelmember.gif
# acid_lab.gif | music_locker.gif
GIF = {
    "mission_passed": "assets/mission_passed.gif",
    "lose_game": "assets/lose_game.gif",
    "cayo_heist": "assets/cayo_perico_heist.gif",
    "music_event": "assets/musiclocker_technonight_response.gif",
    "main_panel": "assets/mainpanelmember.gif",
    "acid_lab": "assets/acid_lab.gif",
    "music_locker": "assets/music_locker.gif",
}

# ── Embed images (ImageKit CDN — used as large bottom images via set_image) ──
IMG = {
    "casino": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/images.jpg",
    "kortz": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/6e26753573182f0b6ed9143a0123e616f4b20db3.jpg",
    "docktease": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/DockTease-GTAV-Logo.webp",
    "warstock": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/download.jpg",
    "bennys": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/GTA_Online-_Lowriders_-_Benny's_Original_Motor_Works.youtube",
    "garage": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/images%20(1).jpg",
    "maze_bank": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/maze-bank-logo.png",
    "elitas": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/Elitas_Travel_logo.png",
    "dynasty8_exec": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/Dynasty8Executive-GTAO.webp",
    "dynasty8": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/Dynasty8.webp",
    "music_locker": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/maxresdefault.jpg",
    "cayo": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/499a97fc07ffaafdd0273ed5a5991a00eacc929a.jpg",
    "lucky_wheel": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/2025-04-23_de27b53e461b7.webp",
    "penthouse": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/36a87f762155d0c603760fa047731802c05f2c3e.jpg",
    "vehicle_exports": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/artworks-000198441669-i3q9x4-t1080x1080.jpg?updatedAt=1792032853732",
    "acid_lab": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/images%20(2).jpg?updatedAt=1792032853376",
    "doomsday": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/TheHeistChallenge2024Week2-GTAOe-Header.webp?updatedAt=1792032853654",
    "cayo_success": "https://ik.imagekit.io/BassaniStudios/SYSTEM%20ECONOMY/o5eNyCNcZKmvdNZHyitmuQ.jpg",
}


def _gif_file(key: str) -> Optional["discord.File"]:
    """Return a discord.File for a local GIF asset, or None if the file is missing."""
    path = GIF.get(key)
    if not path:
        return None
    from pathlib import Path
    candidates = [
        Path(path),
        Path.cwd() / path,
        Path(__file__).resolve().parent.parent / path,
    ]
    for p in candidates:
        if p.is_file():
            return discord.File(str(p), filename=p.name)
    return None


def _apply_gif_image(embed: discord.Embed, key: str) -> Optional["discord.File"]:
    """Set embed image to a local GIF attachment. Returns File to include in send(), or None."""
    f = _gif_file(key)
    if f is None:
        return None
    embed.set_image(url=f"attachment://{f.filename}")
    return f

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
    {"id": "prop_house_mansion", "name": "🏰 The Mansion", "price": 220000, "type": "property", "desc": "Spacious luxury mansion. Permanent & unique. Required for The Kortz Center Heist.", "emoji": "🏰", "unique": True},
]

# ── Dynasty8 Executive (business / underworld properties) ──
FORECLOSURES_ITEMS: List[Dict[str, Any]] = [
    {"id": "biz_warehouse", "name": "🏭 Warehouse", "price": 50000, "type": "business", "desc": "Storage complex. Permanent & unique. Required for Car Theft Job. Holds up to 30 stolen vehicles.", "emoji": "🏭", "unique": True},
    {"id": "biz_hangar", "name": "✈️ Hangar", "price": 20000, "type": "business", "desc": "Aircraft hangar. Permanent & unique.", "emoji": "✈️", "unique": True},
    {"id": "biz_bunker", "name": "🪖 Bunker", "price": 20000, "type": "business", "desc": "Underground bunker. Permanent & unique.", "emoji": "🪖", "unique": True},
]


# ── Car Theft Job — GTA Online vehicles by class (hidden catalog) ──
# class: "low" | "medium" | "high"   price = export payout
CAR_THEFT_VEHICLES: List[Dict[str, Any]] = [
    # ── LOW CLASS (common / cheap) — ~28 cars ──
    {"id": "theft_blista", "name": "Blista", "class": "low", "price": 3200, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_issi", "name": "Issi", "class": "low", "price": 2800, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_panto", "name": "Panto", "class": "low", "price": 2500, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_prairie", "name": "Prairie", "class": "low", "price": 3100, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_asea", "name": "Asea", "class": "low", "price": 2700, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_emperor", "name": "Emperor", "class": "low", "price": 2900, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_glendale", "name": "Glendale", "class": "low", "price": 3400, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_intruder", "name": "Intruder", "class": "low", "price": 3000, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_premier", "name": "Premier", "class": "low", "price": 3300, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_primo", "name": "Primo", "class": "low", "price": 3100, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_regina", "name": "Regina", "class": "low", "price": 2600, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_romero", "name": "Romero Hearse", "class": "low", "price": 3800, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_stanier", "name": "Stanier", "class": "low", "price": 2900, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_stratum", "name": "Stratum", "class": "low", "price": 3200, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_surge", "name": "Surge", "class": "low", "price": 3500, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_tailgater", "name": "Tailgater", "class": "low", "price": 3600, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_warrener", "name": "Warrener", "class": "low", "price": 3400, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_washington", "name": "Washington", "class": "low", "price": 3100, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_asterope", "name": "Asterope", "class": "low", "price": 3000, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_fugitive", "name": "Fugitive", "class": "low", "price": 3700, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_ingot", "name": "Ingot", "class": "low", "price": 2500, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_minivan", "name": "Minivan", "class": "low", "price": 2800, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_phoenix", "name": "Phoenix", "class": "low", "price": 3900, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_picador", "name": "Picador", "class": "low", "price": 2700, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_premier_classic", "name": "Premier Classic", "class": "low", "price": 3200, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_rhapsody", "name": "Rhapsody", "class": "low", "price": 2600, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_sabregt", "name": "Sabre Turbo", "class": "low", "price": 4100, "emoji": "🚗", "type": "stolen_car"},
    {"id": "theft_voodoo", "name": "Voodoo", "class": "low", "price": 3500, "emoji": "🚗", "type": "stolen_car"},
    # ── MEDIUM CLASS (sports / muscle / suv) — ~30 cars ──
    {"id": "theft_sultan", "name": "Sultan", "class": "medium", "price": 8500, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_elegy", "name": "Elegy RH8", "class": "medium", "price": 9200, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_comet", "name": "Comet", "class": "medium", "price": 9800, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_feltzer", "name": "Feltzer", "class": "medium", "price": 8900, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_futo", "name": "Futo", "class": "medium", "price": 7200, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_khamelion", "name": "Khamelion", "class": "medium", "price": 9500, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_lynx", "name": "Lynx", "class": "medium", "price": 10500, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_massacro", "name": "Massacro", "class": "medium", "price": 11200, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_ninef", "name": "9F", "class": "medium", "price": 10800, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_rapidgt", "name": "Rapid GT", "class": "medium", "price": 10200, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_schafter", "name": "Schafter", "class": "medium", "price": 7800, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_schwarzer", "name": "Schwarzer", "class": "medium", "price": 8200, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_surano", "name": "Surano", "class": "medium", "price": 9900, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_carbonizzare", "name": "Carbonizzare", "class": "medium", "price": 11500, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_coquette", "name": "Coquette", "class": "medium", "price": 10100, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_jester", "name": "Jester", "class": "medium", "price": 10900, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_penumbra", "name": "Penumbra", "class": "medium", "price": 7600, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_alpha", "name": "Alpha", "class": "medium", "price": 8700, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_banshee", "name": "Banshee", "class": "medium", "price": 9400, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_buffalo", "name": "Buffalo", "class": "medium", "price": 8100, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_dominator", "name": "Dominator", "class": "medium", "price": 8800, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_gauntlet", "name": "Gauntlet", "class": "medium", "price": 8600, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_phoenix_m", "name": "Phoenix Muscle", "class": "medium", "price": 7900, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_ruiner", "name": "Ruiner", "class": "medium", "price": 7500, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_vigero", "name": "Vigero", "class": "medium", "price": 7700, "emoji": "🏎️", "type": "stolen_car"},
    {"id": "theft_baller", "name": "Baller", "class": "medium", "price": 9800, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_cavalcade", "name": "Cavalcade", "class": "medium", "price": 7200, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_fq2", "name": "FQ 2", "class": "medium", "price": 6900, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_granger", "name": "Granger", "class": "medium", "price": 8400, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_landstalker", "name": "Landstalker", "class": "medium", "price": 7100, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_mesa", "name": "Mesa", "class": "medium", "price": 6500, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_patriot_m", "name": "Patriot", "class": "medium", "price": 9200, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_radius", "name": "Radius", "class": "medium", "price": 6800, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_seminole", "name": "Seminole", "class": "medium", "price": 7000, "emoji": "🚙", "type": "stolen_car"},
    {"id": "theft_serrano", "name": "Serrano", "class": "medium", "price": 7300, "emoji": "🚙", "type": "stolen_car"},
    # ── HIGH CLASS (super / hyper / rare) — ~30 cars ──
    {"id": "theft_adder", "name": "Adder", "class": "high", "price": 28500, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_entityxf", "name": "Entity XF", "class": "high", "price": 31200, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_zentorno", "name": "Zentorno", "class": "high", "price": 34800, "emoji": "🔥", "type": "stolen_car"},
    {"id": "theft_t20", "name": "T20", "class": "high", "price": 36500, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_osiris", "name": "Osiris", "class": "high", "price": 33200, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_reaper", "name": "Reaper", "class": "high", "price": 29800, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_fmj", "name": "FMJ", "class": "high", "price": 35500, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_prototipo", "name": "X80 Proto", "class": "high", "price": 37800, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_tyrus", "name": "Tyrus", "class": "high", "price": 34100, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_italigtb", "name": "Itali GTB", "class": "high", "price": 32600, "emoji": "🏁", "type": "stolen_car"},
    {"id": "theft_nero", "name": "Nero", "class": "high", "price": 35900, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_tempesta", "name": "Tempesta", "class": "high", "price": 33700, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_vacca", "name": "Vacca", "class": "high", "price": 27400, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_voltic", "name": "Voltic", "class": "high", "price": 26800, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_infernus", "name": "Infernus", "class": "high", "price": 29100, "emoji": "🔥", "type": "stolen_car"},
    {"id": "theft_cheetah", "name": "Cheetah", "class": "high", "price": 28300, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_entity2", "name": "Entity XXR", "class": "high", "price": 38200, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_emerus", "name": "Emerus", "class": "high", "price": 39100, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_krieger", "name": "Krieger", "class": "high", "price": 40500, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_s80rr", "name": "S80RR", "class": "high", "price": 37200, "emoji": "🏁", "type": "stolen_car"},
    {"id": "theft_thrax", "name": "Thrax", "class": "high", "price": 39800, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_zorrusso", "name": "Zorrusso", "class": "high", "price": 38600, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_furia", "name": "Furia", "class": "high", "price": 37900, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_italirsx", "name": "Itali RSX", "class": "high", "price": 41200, "emoji": "🏁", "type": "stolen_car"},
    {"id": "theft_champion", "name": "Champion", "class": "high", "price": 36800, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_ignus", "name": "Ignus", "class": "high", "price": 42500, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_torero", "name": "Torero XO", "class": "high", "price": 40100, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_virtue", "name": "Virtue", "class": "high", "price": 35600, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_entity3", "name": "Entity MT", "class": "high", "price": 41800, "emoji": "⚡", "type": "stolen_car"},
    {"id": "theft_turismo3", "name": "Turismo Omaggio", "class": "high", "price": 39500, "emoji": "🏁", "type": "stolen_car"},
]

CAR_THEFT_BY_CLASS = {
    "low": [c for c in CAR_THEFT_VEHICLES if c["class"] == "low"],
    "medium": [c for c in CAR_THEFT_VEHICLES if c["class"] == "medium"],
    "high": [c for c in CAR_THEFT_VEHICLES if c["class"] == "high"],
}

CAR_THEFT_SUCCESS_CHANCE = {
    "low": 0.75,
    "medium": 0.50,
    "high": 0.35,
}


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

CAYO_ACHIEVEMENT = {
    "id": "ach_cayo_heist",
    "name": "🏆 Cayo Perico Heist Trophy",
    "type": "achievement",
    "desc": "Proof that you successfully robbed El Rubio's island.",
    "emoji": "🏆",
}

CAYO_PREP_IDS = [it["id"] for it in CAYO_PREP_ITEMS]

# Heist quiz questions (Cayo Perico / GTA themed) — pool; each run picks 2 at random
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
    {
        "q": "Who is the main target of the Cayo Perico Heist?",
        "options": ["Lester Crest", "El Rubio (Juan Strickler)", "Martin Madrazo", "Pavel"],
        "correct": 1,
    },
    {
        "q": "What permanent vehicle is required to start the Cayo Perico Heist?",
        "options": ["Kosatka Submarine", "Oppressor Mk II", "Buzzard", "Tug Boat"],
        "correct": 0,
    },
    {
        "q": "Which secondary target is commonly found in the compound drainage?",
        "options": ["Gold bars", "Cash stacks", "Weed packages", "Paintings"],
        "correct": 0,
    },
    {
        "q": "What tool is used to cut the glass display cases on Cayo Perico?",
        "options": ["Crowbar", "Plasma Cutter", "Bolt Cutters", "Thermal Charge"],
        "correct": 1,
    },
    {
        "q": "Who helps you coordinate the Cayo Perico Heist from the Kosatka?",
        "options": ["Lester", "Pavel", "English Dave", "Lamar"],
        "correct": 1,
    },
    {
        "q": "What is the name of El Rubio's primary guard dog?",
        "options": ["Chop", "Charlotte", "Brutus", "Rocky"],
        "correct": 1,
    },
    {
        "q": "What is the name of El Rubio's private island airstrip area?",
        "options": ["North Dock", "Main Dock", "Airstrip", "Drainage Tunnel"],
        "correct": 2,
    },
    {
        "q": "Which approach is known for using a dirt bike on Cayo Perico?",
        "options": ["Main Dock", "Velum drop / airstrip", "Kosatka periscope only", "Rhino tank"],
        "correct": 1,
    },
    {
        "q": "What does Pavel primarily use to guide you during the finale?",
        "options": ["A paper map", "Radio from the Kosatka", "Text messages only", "A second player"],
        "correct": 1,
    },
    {
        "q": "Which of these is a valid primary target on Cayo Perico?",
        "options": ["Panther statue", "Rhino tank", "Oppressor Mk II", "Galaxy Super Yacht"],
        "correct": 0,
    },
    {
        "q": "Where is the main compound gate controlled from?",
        "options": ["The tower office", "The drainage", "The airstrip hangar", "The party beach"],
        "correct": 0,
    },
    {
        "q": "What must you gather before Pavel issues a Cayo Perico Invite in this system?",
        "options": ["All 5 prep items", "Only the Longfin", "Only the Kosatka", "A mansion"],
        "correct": 0,
    },
    {
        "q": "Which secondary loot is often stacked in the airport hangar?",
        "options": ["Weed", "Cocaine", "Gold", "Tequila"],
        "correct": 1,
    },
    {
        "q": "What happens if you alert the guards during a stealth approach?",
        "options": ["Nothing", "The island goes on full alert", "You get free loot", "El Rubio leaves"],
        "correct": 1,
    },
]

# ── The Kortz Center Heist (requires The Mansion) ──
KORTZ_PREP_ITEMS: List[Dict[str, Any]] = [
    {"id": "kortz_keycard", "name": "🪪 Security Keycard Clone", "price": 1200, "type": "kortz_prep", "desc": "Cloned staff keycard for the Bell Building entrance.", "emoji": "🪪"},
    {"id": "kortz_hacker", "name": "💻 Hacking Device", "price": 1500, "type": "kortz_prep", "desc": "Bypasses fingerprint scanners and vault terminals.", "emoji": "💻"},
    {"id": "kortz_laser", "name": "🔦 Laser Bypass Kit", "price": 1100, "type": "kortz_prep", "desc": "Disables laser tripwire grids in the basement.", "emoji": "🔦"},
    {"id": "kortz_disguise", "name": "🎭 Staff Disguise", "price": 900, "type": "kortz_prep", "desc": "Museum staff uniform for stealth infiltration.", "emoji": "🎭"},
    {"id": "kortz_replica", "name": "🖼️ Counterfeit Painting Kit", "price": 1800, "type": "kortz_prep", "desc": "Replica of the primary target to swap in the vault.", "emoji": "🖼️"},
]

KORTZ_INVITE_ITEM = {
    "id": "kortz_invite",
    "name": "🎟️ Kortz Center Heist Invite",
    "type": "consumable",
    "desc": "One-time invitation to launch The Kortz Center Heist.",
    "emoji": "🎟️",
}

KORTZ_ACHIEVEMENT = {
    "id": "ach_kortz_heist",
    "name": "🏆 Kortz Center Heist Trophy",
    "type": "achievement",
    "desc": "Proof that you successfully stole the Albert Crisp Collection.",
    "emoji": "🏆",
}

KORTZ_PREP_IDS = [it["id"] for it in KORTZ_PREP_ITEMS]

KORTZ_QUIZ = [
    {
        "q": "Where is the Kortz Center located in Los Santos?",
        "options": ["Downtown", "Pacific Bluffs", "Sandy Shores", "Paleto Bay"],
        "correct": 1,
    },
    {
        "q": "What is the primary target of The Kortz Center Heist?",
        "options": ["Gold bars", "The Albert Crisp Collection (paintings)", "Diamonds", "Bearer Bonds"],
        "correct": 1,
    },
    {
        "q": "Which building inside the Kortz Center holds the vault?",
        "options": ["Low Rotunda", "Bell Building", "Moseley Building", "Biranda Building"],
        "correct": 1,
    },
    {
        "q": "What property upgrade is required to start The Kortz Center Heist?",
        "options": ["Arcade", "Art Studio in a Mansion", "Nightclub", "Facility"],
        "correct": 1,
    },
    {
        "q": "Which of these is a valid entrance to the Kortz Center during the heist?",
        "options": ["Skylight", "Rooftop Helipad", "Underground Tunnel only", "Main Gate only"],
        "correct": 0,
    },
    {
        "q": "Who is the contact that helps organize The Kortz Center Heist?",
        "options": ["Lester Crest", "Mr. Faber / Raf", "Pavel", "English Dave"],
        "correct": 1,
    },
    {
        "q": "What do you swap the original painting with inside the vault?",
        "options": ["Nothing", "A counterfeit replica", "A different painting", "Cash"],
        "correct": 1,
    },
]


# ── Doomsday Heist ──
DOOMSDAY_PREP_ITEMS: List[Dict[str, Any]] = [
    {"id": "dd_keycards", "name": "🪪 Facility Keycards", "type": "doomsday_prep", "desc": "Cloned access cards for the underground facility.", "emoji": "🪪"},
    {"id": "dd_hydra", "name": "✈️ Hydra Data", "type": "doomsday_prep", "desc": "Flight data and weapon codes for aerial approach.", "emoji": "✈️"},
    {"id": "dd_avenger", "name": "🛩️ Avenger Plans", "type": "doomsday_prep", "desc": "Schematics for the mobile command center.", "emoji": "🛩️"},
    {"id": "dd_thruster", "name": "🚀 Thruster Jets", "type": "doomsday_prep", "desc": "Personal flight systems for the finale.", "emoji": "🚀"},
    {"id": "dd_khajali", "name": "🛡️ Khanjali Intel", "type": "doomsday_prep", "desc": "Tank deployment coordinates and weak points.", "emoji": "🛡️"},
]

DOOMSDAY_PREP_IDS = [it["id"] for it in DOOMSDAY_PREP_ITEMS]

DOOMSDAY_TICKET = {
    "id": "dd_ticket",
    "name": "🎟️ Doomsday Heist Ticket",
    "type": "consumable",
    "desc": "One-time ticket to launch The Doomsday Heist. Requires a partner.",
    "emoji": "🎟️",
}

DOOMSDAY_ACHIEVEMENT = {
    "id": "ach_doomsday_heist",
    "name": "🏆 Doomsday Heist Trophy",
    "type": "achievement",
    "desc": "Proof that you survived the three-act Doomsday scenario.",
    "emoji": "🏆",
}

# Memory game symbols
DOOMSDAY_MEMORY_SYMBOLS = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "⚪", "⬛"]


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
    "standard": {"name": "Standard", "emoji": "🃏", "price_key": "casino_membership_standard"},
    "vip": {"name": "VIP", "emoji": "💎", "price_key": "casino_membership_vip"},
    "diamond": {"name": "Diamond", "emoji": "👑", "price_key": "casino_membership_diamond"},
}

CASINO_VIP_ROLE_ID = 1559725006332760064  # Casino Vip Member role given with Master Penthouse

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
    "daily_cooldown": 64800,    # 18 hours
    "min_bet": 10,
    "max_bet": 10000,
    "currency_name": CURRENCY,
    "motoclub_cooldown": 21600,  # 6 hours
    "ceo_cooldown": 21600,       # 6 hours
    "motoclub_reward_min": 320,
    "motoclub_reward_max": 850,
    "ceo_fast_reward_min": 450,
    "ceo_fast_reward_max": 1200,
    "ceo_safe_reward_min": 200,
    "ceo_safe_reward_max": 480,
    "ceo_premium_reward_min": 800,
    "ceo_premium_reward_max": 1800,
    "ceo_premium_cost": 200,
    "cayo_heist_prize_min": 8000,
    "cayo_heist_prize_max": 15000,
    "kortz_heist_prize_min": 10000,
    "kortz_heist_prize_max": 18000,
    # Casino
    "lucky_wheel_cooldown": 86400,
    "casino_membership_standard": 5000,
    "casino_membership_vip": 15000,
    "casino_membership_diamond": 40000,
    "casino_penthouse_price": 320000,
    # Music Locker
    "music_entry_fee": 50,
    "music_entry_reward": 300,
    "music_event_reward_min": 120,
    "music_event_reward_max": 280,
    "music_vip_price": 12000,
    "music_vip_bonus_mult": 1.5,
    "music_event_cooldown": 36000,   # 10 hours
    "music_entry_cooldown": 14400,   # 4 hours
    # Service bonus (admin adjustable)
    "service_bonus": 0,
    # Vehicle export mini-game reward (admin adjustable)
    "export_reward_min": 400,
    "export_reward_max": 900,
    "penthouse_party_reward": 450,  # slightly above base daily
    # Casino slots: 3 uses per 24 hours
    "slots_max_uses": 3,
    "slots_cooldown_window": 86400,  # 24 hours
    # Cayo Perico Launch Heist cooldown
    "cayo_heist_cooldown": 172800,   # 48 hours
    # Car Theft Job
    "car_theft_cooldown": 28800,     # 8 hours
    "car_theft_cost": 1000,
    "export_car_cooldown": 43200,    # 12 hours
    "warehouse_max_vehicles": 30,
    # FreakShop (Dax / Fooliganz)
    "badonkadonk_cooldown": 43200,   # 12 hours
    "badonkadonk_reward": 500,
    "call_dax_cooldown": 28800,      # 8 hours
    "call_dax_success_reward": 1000,
    "call_dax_fail_penalty": 500,
    "labrat_cooldown": 86400,        # 24 hours
    "labrat_reduce_seconds": 18000,  # reduce Call Dax cooldown by 5 hours
    # Doomsday Heist
    "doomsday_prep_cooldown": 43200,   # 12 hours between prep claims
    "doomsday_total_prize": 5000,
    "doomsday_invite_timeout": 900,    # 15 minutes
    # Casino Heist (future / admin adjustable)
    "casino_heist_prize_min": 6000,
    "casino_heist_prize_max": 12000,
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
        self._lock = asyncio.Lock()
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
        changed = False
        if uid not in users:
            users[uid] = {
                "wallet": 0,
                "bank": 0,
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
                "last_music_entry": 0,
                "casino_membership": None,
                "music_vip": False,
                "slots_uses": 0,
                "slots_window_start": 0,
                "last_cayo_heist": 0,
                "last_car_theft": 0,
                "last_export_car": 0,
                "last_badonkadonk": 0,
                "last_call_dax": 0,
                "last_labrat": 0,
                "last_doomsday_prep": 0,
                "created_at": _now_ts(),
            }
            changed = True
        u = users[uid]
        defaults = {
            "last_motoclub": 0,
            "last_ceo": 0,
            "last_lucky_wheel": 0,
            "last_music_event": 0,
            "last_music_entry": 0,
            "casino_membership": None,
            "music_vip": False,
            "wallet": 0,
            "bank": 0,
            "streak": 0,
            "inventory": {},
            "total_earned": 0,
            "total_spent": 0,
            "last_daily": 0,
            "last_work": 0,
            "last_balance": 0,
            "last_penthouse_party": 0,
            "slots_uses": 0,
            "slots_window_start": 0,
            "last_cayo_heist": 0,
            "last_car_theft": 0,
            "last_export_car": 0,
            "last_badonkadonk": 0,
            "last_call_dax": 0,
            "last_labrat": 0,
            "last_doomsday_prep": 0,
        }
        for k, v in defaults.items():
            if k not in u:
                u[k] = v
                changed = True
        if changed:
            users[uid] = u
            save_json(self.USERS_KEY, users)
        return u

    def save_user(self, user_id: int, data: Dict[str, Any]):
        users = load_json(self.USERS_KEY, {})
        users[str(user_id)] = data
        save_json(self.USERS_KEY, users)

    def add_money(self, user_id: int, amount: int, reason: str = "") -> int:
        u = self.get_user(user_id)
        # Apply service bonus on positive earnings from services
        if amount > 0 and reason in ("daily", "work", "motoclub", "ceo_securo", "cayo_heist", "kortz_heist", "music_event", "music_presence", "lucky_wheel"):
            settings = self.get_settings()
            bonus = int(settings.get("service_bonus", 0))
            if bonus > 0:
                amount += bonus
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

    def get_bank(self, user_id: int) -> int:
        u = self.get_user(user_id)
        return int(u.get("bank", 0))

    def set_bank(self, user_id: int, amount: int) -> int:
        u = self.get_user(user_id)
        u["bank"] = max(0, int(amount))
        self.save_user(user_id, u)
        return u["bank"]

    def add_bank(self, user_id: int, amount: int) -> int:
        u = self.get_user(user_id)
        u["bank"] = max(0, int(u.get("bank", 0)) + amount)
        self.save_user(user_id, u)
        return u["bank"]

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
            KORTZ_PREP_ITEMS,
            CAR_THEFT_VEHICLES,
            DOOMSDAY_PREP_ITEMS,
        ):
            for it in lst:
                items[it["id"]] = it
        items[CAYO_INVITE_ITEM["id"]] = CAYO_INVITE_ITEM
        items[CAYO_ACHIEVEMENT["id"]] = CAYO_ACHIEVEMENT
        items[KORTZ_INVITE_ITEM["id"]] = KORTZ_INVITE_ITEM
        items[KORTZ_ACHIEVEMENT["id"]] = KORTZ_ACHIEVEMENT
        items[DOOMSDAY_TICKET["id"]] = DOOMSDAY_TICKET
        items[DOOMSDAY_ACHIEVEMENT["id"]] = DOOMSDAY_ACHIEVEMENT
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
    file: Optional[discord.File] = None,
    gif_key: Optional[str] = None,
) -> Optional[discord.Message]:
    """Post result to Bovary Market and try to ping the user.
    Optionally attach a local GIF via file= or gif_key= (from GIF dict).
    """
    ch = bot.get_channel(MARKET_CHANNEL_ID)
    if ch is None:
        try:
            ch = await bot.fetch_channel(MARKET_CHANNEL_ID)
        except Exception:
            logger.exception("Cannot fetch Market channel")
            return None
    text = content or f"{user.mention}"
    attach = file
    if attach is None and gif_key:
        attach = _apply_gif_image(embed, gif_key)
    try:
        kwargs: Dict[str, Any] = {"content": text, "embed": embed}
        if view is not None:
            kwargs["view"] = view
        if attach is not None:
            kwargs["file"] = attach
        return await ch.send(**kwargs)
    except Exception:
        logger.exception("Failed to post to Market")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# VISIBILITY CHOICE VIEW (public vs ephemeral)
# ═══════════════════════════════════════════════════════════════════════════

class VisibilityChoiceView(discord.ui.View):
    """Lets the user choose to view privately or post to channel.
    No fixed custom_id — avoids conflicts with the persistent MemberPanelView.
    """

    def __init__(self, cog: "Economy", action: str, user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.action = action
        self.user_id = user_id

        btn_private = discord.ui.Button(
            label="🔒 View Privately",
            style=discord.ButtonStyle.primary,
        )
        btn_private.callback = self._private
        self.add_item(btn_private)

        btn_public = discord.ui.Button(
            label="📢 Post to Channel",
            style=discord.ButtonStyle.secondary,
        )
        btn_public.callback = self._public
        self.add_item(btn_public)

    async def _private(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        embed, view = await self.cog.handle_member_action(interaction, self.action, force_private=True)
        if embed is None:
            return await interaction.followup.send("Action cancelled or error.", ephemeral=True)
        kwargs = {"embed": embed, "ephemeral": True}
        if view is not None:
            kwargs["view"] = view
        await interaction.followup.send(**kwargs)

    async def _public(self, interaction: discord.Interaction):
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
            kwargs = {"embed": embed, "ephemeral": True}
            if view is not None:
                kwargs["view"] = view
            await interaction.followup.send(**kwargs)


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
        all_items = self.cog.data.get_all_items()
        item = all_items.get(item_id)
        if not item:
            return await interaction.response.send_message("Item not found.", ephemeral=True)

        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})

        # Unique / permanent items (Mansion, Submarine, Penthouse, etc.)
        if item.get("unique") or item_id in ("mil_submarine", "casino_penthouse", "prop_house_mansion", "biz_warehouse", "biz_hangar", "biz_bunker"):
            if inv.get(item_id, 0) >= 1:
                return await interaction.response.send_message(
                    f"You already own **{item.get('emoji', '')} {item['name']}**. It is permanent and unique.",
                    ephemeral=True,
                )

        if u["wallet"] < item["price"]:
            return await interaction.response.send_message(
                f"Insufficient balance. You need {_fmt(item['price'])} {CURRENCY}.", ephemeral=True
            )

        self.cog.data.add_money(self.user_id, -item["price"], "shop_buy")
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        inv[item_id] = inv.get(item_id, 0) + 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)

        embed = discord.Embed(
            title="🛒 Purchase Successful!",
            description=f"You bought **{item.get('emoji', '')} {item['name']}** for **{_fmt(item['price'])}** {CURRENCY}.",
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Announce ALL purchases publicly in Market channel
        public = discord.Embed(
            title="🛒 New Acquisition!",
            description=(
                f"{interaction.user.mention} just bought "
                f"**{item.get('emoji', '')} {item['name']}** "
                f"for **{_fmt(item['price'])}** {CURRENCY}!"
            ),
            color=COLOR_SUCCESS,
        )
        public.set_footer(text=f"GTA Economy · {self.shop_name}")
        await post_to_market(self.cog.bot, interaction.user, public)



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
        cd = settings.get("motoclub_cooldown", 21600)
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
            lose = _apply_gif_image(embed, "lose_game")
            kwargs = {"embed": embed, "view": None}
            if lose:
                kwargs["attachments"] = [lose]
            await interaction.response.edit_message(**kwargs)
            public = discord.Embed(
                title="💥 MotoClub Delivery Failed",
                description=f"{interaction.user.mention} failed a MotoClub delivery run.",
                color=COLOR_FAIL,
            )
            await post_to_market(self.cog.bot, interaction.user, public, gif_key="lose_game")
            return

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
        embed.set_footer(text="MotoClub · Cooldown started (6h)")
        await interaction.response.edit_message(embed=embed, view=None)
        public = discord.Embed(
            title="🏍️ MotoClub Delivery Complete",
            description=f"{interaction.user.mention} successfully delivered **{self.product['name']}** and earned **{_fmt(reward)}** {CURRENCY}!",
            color=COLOR_SUCCESS,
        )
        await post_to_market(self.cog.bot, interaction.user, public, gif_key="mission_passed")


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
        cd = settings.get("ceo_cooldown", 21600)
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
            embed.set_footer(text="CEO SecuroServ · Cooldown started (6h)")
            await interaction.response.edit_message(embed=embed, view=None)
            public = discord.Embed(
                title="💼 CEO SecuroServ — Acquisition Complete",
                description=f"{interaction.user.mention} completed a **{route_name}** acquisition and earned **{_fmt(reward)}** {CURRENCY}!",
                color=COLOR_SUCCESS,
            )
            await post_to_market(self.cog.bot, interaction.user, public, gif_key="mission_passed")
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
            embed.set_footer(text="CEO SecuroServ · Cooldown started (6h)")
            lose = _apply_gif_image(embed, "lose_game")
            kwargs = {"embed": embed, "view": None}
            if lose:
                kwargs["attachments"] = [lose]
            await interaction.response.edit_message(**kwargs)
            public = discord.Embed(
                title="💥 CEO SecuroServ — Acquisition Failed",
                description=f"{interaction.user.mention} failed a **{route_name}** acquisition.",
                color=COLOR_FAIL,
            )
            await post_to_market(self.cog.bot, interaction.user, public, gif_key="lose_game")


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
        # Prefer local cayo heist GIF; fall back to static ImageKit image
        gif = _gif_file("cayo_heist")
        if gif is not None:
            embed.set_image(url=f"attachment://{gif.filename}")
        else:
            embed.set_image(url=IMG["cayo"])
        embed.set_footer(text="Requires Kosatka Submarine · All actions private")
        return embed

    def build_files(self) -> List[discord.File]:
        f = _gif_file("cayo_heist")
        return [f] if f else []

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
        settings = self.cog.data.get_settings()
        now = _now_ts()
        last = float(u.get("last_cayo_heist", 0))
        cd = settings.get("cayo_heist_cooldown", 172800)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ Cayo Perico on Cooldown",
                description=(
                    f"**Mr. Rubio is still on alert, wait for the dust to settle. "
                    f"For now, you can gather the preparations and stockpile as well.**\n\n"
                    f"You can launch another heist in **{_fmt_time(rem)}**."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        inv = u.get("inventory", {})
        if inv.get("cayo_invite", 0) < 1:
            embed = discord.Embed(
                title="🎟️ No Invite",
                description="You need a **Cayo Perico Invite**. Deliver a full prep set first.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Consume invite and start cooldown
        inv["cayo_invite"] -= 1
        if inv["cayo_invite"] <= 0:
            inv.pop("cayo_invite", None)
        u["inventory"] = inv
        u["last_cayo_heist"] = now
        self.cog.data.save_user(self.user_id, u)

        # Pick 2 random questions from the pool (no repeats within this run)
        q_indices = random.sample(range(len(CAYO_QUIZ)), k=min(2, len(CAYO_QUIZ)))
        view = CayoQuizView(self.cog, self.user_id, stage=0, question_indices=q_indices)
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
    """Stages 0 and 1: multiple-choice quiz (2 random from pool). Stage 2: reward choice."""

    def __init__(
        self,
        cog: "Economy",
        user_id: int,
        stage: int,
        question_indices: Optional[List[int]] = None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.stage = stage  # 0, 1, or 2
        if question_indices is None:
            question_indices = random.sample(range(len(CAYO_QUIZ)), k=min(2, len(CAYO_QUIZ)))
        self.question_indices = question_indices

        if stage < 2:
            qdata = CAYO_QUIZ[self.question_indices[stage]]
            options = [
                discord.SelectOption(label=opt[:100], value=str(i))
                for i, opt in enumerate(qdata["options"])
            ]
            select = discord.ui.Select(placeholder="Choose your answer…", options=options)
            select.callback = self._answer
            self.add_item(select)
        else:
            pcts = [0.60, 0.70, 0.85, 1.00]
            random.shuffle(pcts)
            for label, pct in zip("ABCD", pcts):
                self.add_item(CayoRewardButton(self.cog, self.user_id, label, pct))

    def build_embed(self) -> discord.Embed:
        if self.stage < 2:
            qdata = CAYO_QUIZ[self.question_indices[self.stage]]
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
                "• Bags contain **60% / 70% / 85% / 100%** of the total prize\n"
                "• Total heist value is high — you will cover prep costs and profit\n\n"
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
        qdata = CAYO_QUIZ[self.question_indices[self.stage]]
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
        next_view = CayoQuizView(
            self.cog, self.user_id, stage=next_stage, question_indices=self.question_indices
        )
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
            settings.get("cayo_heist_prize_min", 8000),
            settings.get("cayo_heist_prize_max", 15000),
        )
        reward = int(total * self.pct)
        self.cog.data.add_money(self.user_id, reward, "cayo_heist")
        # Achievement item (once)
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        if inv.get("ach_cayo_heist", 0) < 1:
            inv["ach_cayo_heist"] = 1
            u["inventory"] = inv
            self.cog.data.save_user(self.user_id, u)
        embed = discord.Embed(
            title="🏆 Heist Complete!",
            description=(
                f"You grabbed **Loot Bag** and escaped Cayo Perico!\n\n"
                f"Total heist value: **{_fmt(total)}** {CURRENCY}\n"
                f"Your share (**{int(self.pct*100)}%**): **{_fmt(reward)}** {CURRENCY}\n\n"
                f"Achievement unlocked: **{CAYO_ACHIEVEMENT['emoji']} {CAYO_ACHIEVEMENT['name']}**"
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
        await post_to_market(self.cog.bot, interaction.user, public, gif_key="mission_passed")



# ═══════════════════════════════════════════════════════════════════════════
# THE KORTZ CENTER HEIST
# ═══════════════════════════════════════════════════════════════════════════

def _has_mansion(u: Dict) -> bool:
    inv = u.get("inventory", {})
    return inv.get("prop_house_mansion", 0) >= 1


def _kortz_prep_progress(u: Dict) -> Tuple[int, List[str]]:
    inv = u.get("inventory", {})
    owned = []
    missing = []
    for it in KORTZ_PREP_ITEMS:
        if inv.get(it["id"], 0) >= 1:
            owned.append(it["id"])
        else:
            missing.append(it["id"])
    return len(owned), missing


class KortzMainView(discord.ui.View):
    """Main Kortz Center Heist panel (ephemeral). Requires The Mansion."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self, u: Dict) -> discord.Embed:
        inv = u.get("inventory", {})
        lines = []
        for it in KORTZ_PREP_ITEMS:
            qty = inv.get(it["id"], 0)
            status = "✅" if qty >= 1 else "❌"
            lines.append(
                f"{status} {it.get('emoji', '')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                + (f" (owned ×{qty})" if qty else "")
            )
        owned_count, _ = _kortz_prep_progress(u)
        invite_qty = inv.get("kortz_invite", 0)
        embed = discord.Embed(
            title="🖼️ The Kortz Center Heist",
            description=(
                "Infiltrate the Bell Building at the Kortz Center and steal the "
                "**Albert Crisp Collection**.\n\n"
                "Prepare your gear, deliver the full set for an **Invite**, "
                "then launch the Heist for a big payout + trophy.\n\n"
                f"**Prep progress:** {owned_count}/5 items\n"
                f"**Invites owned:** {invite_qty}\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_ORANGE,
        )
        embed.set_image(url=IMG["kortz"])
        embed.set_footer(text="Requires The Mansion · All actions private")
        return embed

    @discord.ui.button(label="🛒 Buy Prep Items", style=discord.ButtonStyle.primary, row=0)
    async def buy_prep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your panel.", ephemeral=True)
        view = KortzBuyView(self.cog, self.user_id)
        embed = discord.Embed(
            title="🛒 Kortz Center — Prep Shop",
            description="Select an item to purchase. You need **all 5** to deliver for an Invite.",
            color=COLOR_ORANGE,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📦 Deliver Prep Set", style=discord.ButtonStyle.success, row=0)
    async def deliver(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your panel.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        owned_count, missing = _kortz_prep_progress(u)
        if owned_count < 5:
            names = [it["name"] for it in KORTZ_PREP_ITEMS if it["id"] in missing]
            embed = discord.Embed(
                title="📦 Incomplete Set",
                description=f"You still need:\n• " + "\n• ".join(names) + "\n\nBuy the missing items first.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        inv = u.get("inventory", {})
        for iid in KORTZ_PREP_IDS:
            inv[iid] = max(0, inv.get(iid, 0) - 1)
            if inv[iid] == 0:
                inv.pop(iid, None)
        inv["kortz_invite"] = inv.get("kortz_invite", 0) + 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)

        embed = discord.Embed(
            title="✅ Prep Set Delivered!",
            description=(
                "You handed over the full preparation kit to the Art Studio.\n\n"
                f"Received: **🎟️ Kortz Center Heist Invite** ×1\n"
                f"Invites now: **{inv['kortz_invite']}**\n\n"
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
        if inv.get("kortz_invite", 0) < 1:
            embed = discord.Embed(
                title="🎟️ No Invite",
                description="You need a **Kortz Center Heist Invite**. Deliver a full prep set first.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        inv["kortz_invite"] -= 1
        if inv["kortz_invite"] <= 0:
            inv.pop("kortz_invite", None)
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)

        view = KortzQuizView(self.cog, self.user_id, stage=0)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class KortzBuyView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        options = [
            discord.SelectOption(
                label=f"{it.get('emoji', '')} {it['name']}"[:100],
                value=it["id"],
                description=f"{_fmt(it['price'])} {CURRENCY}"[:100],
            )
            for it in KORTZ_PREP_ITEMS
        ]
        select = discord.ui.Select(placeholder="Choose prep item to buy…", options=options)
        select.callback = self._buy
        self.add_item(select)

    async def _buy(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your shop.", ephemeral=True)
        item_id = interaction.data["values"][0]
        item = next((it for it in KORTZ_PREP_ITEMS if it["id"] == item_id), None)
        if not item:
            return await interaction.response.send_message("Item not found.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        if u["wallet"] < item["price"]:
            return await interaction.response.send_message(
                f"Insufficient balance. You need {_fmt(item['price'])} {CURRENCY}.",
                ephemeral=True,
            )
        self.cog.data.add_money(self.user_id, -item["price"], "kortz_prep_buy")
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        inv[item_id] = inv.get(item_id, 0) + 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)
        owned, _ = _kortz_prep_progress(u)
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


class KortzQuizView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int, stage: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.stage = stage

        if stage < 2:
            qdata = KORTZ_QUIZ[stage % len(KORTZ_QUIZ)]
            options = [
                discord.SelectOption(label=opt[:100], value=str(i))
                for i, opt in enumerate(qdata["options"])
            ]
            select = discord.ui.Select(placeholder="Choose your answer…", options=options)
            select.callback = self._answer
            self.add_item(select)
        else:
            pcts = [0.60, 0.70, 0.85, 1.00]
            random.shuffle(pcts)
            for label, pct in zip("ABCD", pcts):
                self.add_item(KortzRewardButton(self.cog, self.user_id, label, pct))

    def build_embed(self) -> discord.Embed:
        if self.stage < 2:
            qdata = KORTZ_QUIZ[self.stage % len(KORTZ_QUIZ)]
            embed = discord.Embed(
                title=f"🖼️ Kortz Center Heist — Question {self.stage + 1}/2",
                description=f"**{qdata['q']}**\n\nSelect the correct answer below.",
                color=COLOR_ORANGE,
            )
            embed.set_footer(text="Wrong answer ends the heist with no payout")
            return embed
        embed = discord.Embed(
            title="🖼️ Kortz Center Heist — Vault!",
            description=(
                "You reached the basement vault of the Bell Building.\n\n"
                "Choose one of the **4 art cases**. All are wins:\n"
                "• Cases contain **60% / 70% / 85% / 100%** of the total prize\n"
                "• Primary target: Albert Crisp Collection painting\n\n"
                "Pick wisely — the values are hidden."
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="All choices succeed — higher % is better")
        return embed

    async def _answer(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your heist.", ephemeral=True)
        choice = int(interaction.data["values"][0])
        qdata = KORTZ_QUIZ[self.stage % len(KORTZ_QUIZ)]
        if choice != qdata["correct"]:
            embed = discord.Embed(
                title="💥 Heist Failed",
                description=(
                    f"Wrong answer.\n"
                    f"Correct was: **{qdata['options'][qdata['correct']]}**\n\n"
                    "Security was alerted. No payout this run."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.edit_message(embed=embed, view=None)

        next_stage = self.stage + 1
        next_view = KortzQuizView(self.cog, self.user_id, stage=next_stage)
        embed = next_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=next_view)


class KortzRewardButton(discord.ui.Button):
    def __init__(self, cog: "Economy", user_id: int, label: str, pct: float):
        super().__init__(label=f"Art Case {label}", style=discord.ButtonStyle.primary)
        self.cog = cog
        self.user_id = user_id
        self.pct = pct

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your heist.", ephemeral=True)
        settings = self.cog.data.get_settings()
        total = random.randint(
            settings.get("kortz_heist_prize_min", 10000),
            settings.get("kortz_heist_prize_max", 18000),
        )
        reward = int(total * self.pct)
        self.cog.data.add_money(self.user_id, reward, "kortz_heist")
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        if inv.get("ach_kortz_heist", 0) < 1:
            inv["ach_kortz_heist"] = 1
            u["inventory"] = inv
            self.cog.data.save_user(self.user_id, u)
        embed = discord.Embed(
            title="🏆 Heist Complete!",
            description=(
                f"You swapped the painting and escaped the Kortz Center!\n\n"
                f"Total heist value: **{_fmt(total)}** {CURRENCY}\n"
                f"Your share (**{int(self.pct*100)}%**): **{_fmt(reward)}** {CURRENCY}\n\n"
                f"Achievement unlocked: **{KORTZ_ACHIEVEMENT['emoji']} {KORTZ_ACHIEVEMENT['name']}**"
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Kortz Center Heist · Invite consumed")
        await interaction.response.edit_message(embed=embed, view=None)
        public = discord.Embed(
            title="🖼️ Kortz Center Heist Successful",
            description=f"{interaction.user.mention} completed The Kortz Center Heist and earned **{_fmt(reward)}** {CURRENCY}!",
            color=COLOR_ORANGE,
        )
        await post_to_market(self.cog.bot, interaction.user, public)


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
                "• **Podium Collection** — exclusive vehicles (Penthouse)\n"
                "• **Slot Machines** — high rollers (Penthouse)\n"
                "• **Master Penthouse** — premium residence"
            ),
            color=COLOR_CASINO,
        )
        embed.set_image(url=IMG["casino"])
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
        embed.set_image(url=IMG["lucky_wheel"])
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
                f"{tier['emoji']} **{tier['name']}** — {_fmt(price)} {CURRENCY} {owned}"
            )
        embed = discord.Embed(
            title="🃏 Casino Membership",
            description=(
                "Higher tiers unlock prestige status at the Diamond Casino.\n"
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
        u = self.cog.data.get_user(self.user_id)
        if u.get("inventory", {}).get("casino_penthouse", 0) < 1:
            embed = discord.Embed(
                title="🏨 Master Penthouse Required",
                description=(
                    "Only owners of the **Master Penthouse** can access the Podium Collection.\n"
                    "Purchase the Master Penthouse first."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        lines = [
            f"{it.get('emoji','🏎️')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
            for it in CASINO_PODIUM
        ]
        embed = discord.Embed(
            title="🏎️ Podium Collection",
            description=(
                "Exclusive vehicles displayed on the casino podium.\n"
                "Available only to **Master Penthouse** owners.\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_CASINO,
        )
        embed.set_footer(text="Select below to purchase · Private")
        view = ShopBuyView(self.cog, self.user_id, CASINO_PODIUM, "Podium Collection")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🎰 Slot Machines", style=discord.ButtonStyle.danger, row=1)
    async def slots(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        if u.get("inventory", {}).get("casino_penthouse", 0) < 1:
            embed = discord.Embed(
                title="🏨 Master Penthouse Required",
                description=(
                    "The high-roller **Slot Machines** are exclusive to **Master Penthouse** owners.\n"
                    "Purchase the Master Penthouse to unlock jackpot games."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        view = CasinoSlotsView(self.cog, self.user_id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏨 Master Penthouse", style=discord.ButtonStyle.success, row=2)
    async def penthouse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        view = MasterPenthouseView(self.cog, self.user_id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class MasterPenthouseView(discord.ui.View):
    """Master Penthouse suite — buy, party, and future features."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self) -> discord.Embed:
        settings = self.cog.data.get_settings()
        price = settings.get("casino_penthouse_price", CASINO_PENTHOUSE["price"])
        u = self.cog.data.get_user(self.user_id)
        owned = u.get("inventory", {}).get("casino_penthouse", 0) >= 1
        party_reward = settings.get("penthouse_party_reward", 450)
        embed = discord.Embed(
            title="🏨 Master Penthouse",
            description=(
                "The most exclusive residence on the Strip.\n"
                "Private elevators, VIP lounges and the best view in Los Santos.\n\n"
                f"**Status:** {'✅ Owned' if owned else '❌ Not owned'}\n"
                f"**Purchase price:** {_fmt(price)} {CURRENCY}\n"
                f"**Throw a Party reward:** ~{_fmt(party_reward)} {CURRENCY} (owners only)\n\n"
                "Owning the penthouse unlocks Podium vehicles, Slot Machines and the Casino Vip Member role."
            ),
            color=COLOR_CASINO,
        )
        embed.set_image(url=IMG["penthouse"])
        embed.set_footer(text="Master Penthouse · Diamond Casino & Resort")
        return embed

    @discord.ui.button(label="🛒 Buy Penthouse", style=discord.ButtonStyle.success, row=0)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        price = settings.get("casino_penthouse_price", CASINO_PENTHOUSE["price"])
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        if inv.get("casino_penthouse", 0) >= 1:
            return await interaction.response.send_message(
                "You already own the **Master Penthouse**.", ephemeral=True
            )
        if u["wallet"] < price:
            return await interaction.response.send_message(
                f"Need **{_fmt(price)}** {CURRENCY}. You have **{_fmt(u['wallet'])}**.",
                ephemeral=True,
            )
        self.cog.data.add_money(self.user_id, -price, "casino_penthouse")
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        inv["casino_penthouse"] = 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)
        try:
            if interaction.guild:
                role = interaction.guild.get_role(CASINO_VIP_ROLE_ID)
                member = interaction.guild.get_member(self.user_id)
                if role and member and role not in member.roles:
                    await member.add_roles(role, reason="Master Penthouse purchase")
        except Exception:
            logger.exception("Failed to assign Casino Vip Member role")
        embed = discord.Embed(
            title="🏨 Welcome Home!",
            description=(
                f"You purchased the **Master Penthouse** for **{_fmt(price)}** {CURRENCY}.\n\n"
                "Private elevators, exclusive lounges and the best view of the Strip are yours.\n"
                "You received the **Casino Vip Member** role."
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_image(url=IMG["penthouse"])
        await interaction.response.send_message(embed=embed, ephemeral=True)
        public = discord.Embed(
            title="🏨 Master Penthouse Acquired!",
            description=f"{interaction.user.mention} just purchased the **Master Penthouse**!",
            color=COLOR_CASINO,
        )
        await post_to_market(self.cog.bot, interaction.user, public)

    @discord.ui.button(label="🎉 Throw a Party", style=discord.ButtonStyle.primary, row=0)
    async def party(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        if u.get("inventory", {}).get("casino_penthouse", 0) < 1:
            return await interaction.response.send_message(
                "You need to own the **Master Penthouse** to throw a party.", ephemeral=True
            )
        settings = self.cog.data.get_settings()
        # Party reward slightly above base daily
        base = settings.get("penthouse_party_reward", 450)
        daily = settings.get("daily_amount", 300)
        reward = max(base, daily + 100)
        # Simple daily party cooldown using last_music_event style — use a dedicated key
        now = _now_ts()
        last = float(u.get("last_penthouse_party", 0))
        if now - last < 86400:
            rem = int(86400 - (now - last))
            return await interaction.response.send_message(
                f"You already threw a party recently. Try again in **{_fmt_time(rem)}**.",
                ephemeral=True,
            )
        u["last_penthouse_party"] = now
        self.cog.data.save_user(self.user_id, u)
        self.cog.data.add_money(self.user_id, reward, "penthouse_party")
        embed = discord.Embed(
            title="🎉 Party Night!",
            description=(
                f"Your penthouse was packed all night.\n"
                f"Guests tipped **{_fmt(reward)}** {CURRENCY}."
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_image(url=IMG["penthouse"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🛋️ Interior — Soon", style=discord.ButtonStyle.secondary, row=1)
    async def soon_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        await interaction.response.send_message("**Soon** — this feature is under construction.", ephemeral=True)

    @discord.ui.button(label="🚁 Helipad — Soon", style=discord.ButtonStyle.secondary, row=1)
    async def soon_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        await interaction.response.send_message("**Soon** — this feature is under construction.", ephemeral=True)


class CasinoMembershipView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        options = [
            discord.SelectOption(
                label=f"{t['emoji']} {t['name']}",
                value=key,
                description="Casino prestige tier",
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
                f"Paid: **{_fmt(price)}** {CURRENCY}"
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CasinoSlotsView(discord.ui.View):
    """High-roller slot machines — Master Penthouse only."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎰 High-Roller Slot Machines",
            description=(
                "Exclusive to **Master Penthouse** owners.\n\n"
                "Choose your bet and spin the reels.\n"
                "• 🍒🍒🍒 Small win\n"
                "• 🍋🍋🍋 Medium win\n"
                "• 💎💎💎 Big win\n"
                "• 7️⃣7️⃣7️⃣ **JACKPOT**\n\n"
                "**Limit:** 3 spins every 24 hours.\n"
                "House edge applies — gamble responsibly."
            ),
            color=COLOR_CASINO,
        )
        embed.set_footer(text="Casino · High Roller · Private · 3 spins / 24h")
        return embed

    @discord.ui.button(label="Bet 100", style=discord.ButtonStyle.secondary, row=0)
    async def bet_100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._spin(interaction, 100)

    @discord.ui.button(label="Bet 500", style=discord.ButtonStyle.primary, row=0)
    async def bet_500(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._spin(interaction, 500)

    @discord.ui.button(label="Bet 2000", style=discord.ButtonStyle.danger, row=0)
    async def bet_2000(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._spin(interaction, 2000)

    async def _spin(self, interaction: discord.Interaction, bet: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your machine.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        settings = self.cog.data.get_settings()
        now = _now_ts()
        window = settings.get("slots_cooldown_window", 86400)
        max_uses = settings.get("slots_max_uses", 3)
        window_start = float(u.get("slots_window_start", 0))
        uses = int(u.get("slots_uses", 0))
        if now - window_start >= window:
            uses = 0
            window_start = now
            u["slots_uses"] = 0
            u["slots_window_start"] = now
            self.cog.data.save_user(self.user_id, u)
        if uses >= max_uses:
            rem = int(window - (now - window_start))
            return await interaction.response.send_message(
                f"⏳ Slot Machines limit reached (**{max_uses}** spins per 24h).\n"
                f"Try again in **{_fmt_time(rem)}**.",
                ephemeral=True,
            )
        if u["wallet"] < bet:
            return await interaction.response.send_message(
                f"Need **{_fmt(bet)}** {CURRENCY}. You have **{_fmt(u['wallet'])}**.",
                ephemeral=True,
            )
        u["slots_uses"] = uses + 1
        u["slots_window_start"] = window_start if window_start else now
        self.cog.data.save_user(self.user_id, u)
        self.cog.data.add_money(self.user_id, -bet, "slots_bet")

        # Weighted outcomes — reduced payouts (house edge stronger)
        roll = random.random()
        symbols = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
        if roll < 0.015:  # Jackpot ~1.5%
            mult = 8
            result = "7️⃣ 7️⃣ 7️⃣"
            title = "🎰 JACKPOT!!!"
            color = COLOR_SUCCESS
        elif roll < 0.06:  # Big ~4.5%
            mult = 3.5
            result = "💎 💎 💎"
            title = "🎰 Big Win!"
            color = COLOR_SUCCESS
        elif roll < 0.15:  # Medium ~9%
            mult = 2
            result = "🍋 🍋 🍋"
            title = "🎰 Nice Win"
            color = COLOR_INFO
        elif roll < 0.30:  # Small ~15%
            mult = 1.2
            result = "🍒 🍒 🍒"
            title = "🎰 Small Win"
            color = COLOR_INFO
        else:
            mult = 0
            result = f"{random.choice(symbols)} {random.choice(symbols)} {random.choice(symbols)}"
            title = "🎰 No Win"
            color = COLOR_FAIL

        payout = int(bet * mult)
        if payout > 0:
            self.cog.data.add_money(self.user_id, payout, "slots_win")
        net = payout - bet
        embed = discord.Embed(
            title=title,
            description=(
                f"**Reels:** {result}\n\n"
                f"Bet: **{_fmt(bet)}**\n"
                f"Payout: **{_fmt(payout)}**\n"
                f"Net: **{_fmt(net)}** {CURRENCY}"
            ),
            color=color,
        )
        embed.set_footer(text="High-Roller Slots · Master Penthouse")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if payout >= bet * 3.5:
            public = discord.Embed(
                title="🎰 Casino Jackpot!",
                description=f"{interaction.user.mention} hit a big win on the slots and took home **{_fmt(payout)}** {CURRENCY}!",
                color=COLOR_CASINO,
            )
            await post_to_market(self.cog.bot, interaction.user, public, gif_key="mission_passed")


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
                f"(free for VIP) · small presence bonus · **4h cooldown**\n"
                f"• **Join Event** — event reward · **10h cooldown**\n"
                f"• **Unlock VIP** — permanent VIP for {_fmt(settings.get('music_vip_price', 12000))} {CURRENCY}"
            ),
            color=COLOR_PURPLE,
        )
        gif = _gif_file("music_locker")
        if gif is not None:
            embed.set_image(url=f"attachment://{gif.filename}")
        else:
            embed.set_image(url=IMG["music_locker"])
        embed.set_footer(text="Music Locker · Underground · Private")
        return embed

    def build_files(self) -> List[discord.File]:
        f = _gif_file("music_locker")
        return [f] if f else []

    @discord.ui.button(label="🚪 Enter Club", style=discord.ButtonStyle.primary, row=0)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last_entry = float(u.get("last_music_entry", 0))
        entry_cd = settings.get("music_entry_cooldown", 14400)
        if now - last_entry < entry_cd:
            rem = int(entry_cd - (now - last_entry))
            embed = discord.Embed(
                title="⏳ Enter Club Cooldown",
                description=f"You can enter the club again in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        fee = settings.get("music_entry_fee", 50)
        reward = settings.get("music_entry_reward", 300)
        is_vip = bool(u.get("music_vip"))
        if not is_vip:
            if u["wallet"] < fee:
                return await interaction.response.send_message(
                    f"Entry costs **{_fmt(fee)}** {CURRENCY}.", ephemeral=True
                )
            self.cog.data.add_money(self.user_id, -fee, "music_entry")
        u = self.cog.data.get_user(self.user_id)
        u["last_music_entry"] = now
        self.cog.data.save_user(self.user_id, u)
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
        embed.set_footer(text="Music Locker · Enter Club cooldown: 4h")
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
        embed.set_footer(text="Music Locker · Event cooldown: 10h")
        event_gif = _apply_gif_image(embed, "music_event")
        kwargs = {"embed": embed, "ephemeral": True}
        if event_gif:
            kwargs["file"] = event_gif
        await interaction.response.send_message(**kwargs)
        public = discord.Embed(
            title="🎵 Music Locker",
            description=f"{interaction.user.mention} hit **{event_name}** and earned **{_fmt(reward)}** {CURRENCY}!",
            color=COLOR_PURPLE,
        )
        await post_to_market(self.cog.bot, interaction.user, public, gif_key="music_event")

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
# MAZE BANK (wallet + bank deposit)
# ═══════════════════════════════════════════════════════════════════════════

class MazeBankMainView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self, u: Dict) -> discord.Embed:
        wallet = int(u.get("wallet", 0))
        bank = int(u.get("bank", 0))
        total = wallet + bank
        embed = discord.Embed(
            title="🏦 Maze Bank",
            description=(
                "Secure banking services in Los Santos.\n\n"
                f"**Wallet:** {_fmt(wallet)} {CURRENCY}\n"
                f"**Bank Deposit:** {_fmt(bank)} {CURRENCY}\n"
                f"**Total Assets:** {_fmt(total)} {CURRENCY}\n\n"
                "Deposit or withdraw funds. View your statement privately or post it publicly."
            ),
            color=COLOR_MAIN,
        )
        embed.set_image(url=IMG["maze_bank"])
        embed.set_footer(text="Maze Bank · Private by default")
        return embed

    @discord.ui.button(label="📥 Deposit", style=discord.ButtonStyle.success, row=0)
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your bank menu.", ephemeral=True)
        await interaction.response.send_modal(MazeBankTransferModal(self.cog, "deposit"))

    @discord.ui.button(label="📤 Withdraw", style=discord.ButtonStyle.danger, row=0)
    async def withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your bank menu.", ephemeral=True)
        await interaction.response.send_modal(MazeBankTransferModal(self.cog, "withdraw"))

    @discord.ui.button(label="📋 View Statement", style=discord.ButtonStyle.primary, row=0)
    async def statement(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your bank menu.", ephemeral=True)
        view = VisibilityChoiceView(self.cog, "maze_statement", interaction.user.id)
        embed = discord.Embed(
            title="📋 Maze Bank Statement",
            description="Choose how you want to view your statement:",
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class MazeBankTransferModal(discord.ui.Modal):
    def __init__(self, cog: "Economy", mode: str):
        title = "Deposit to Maze Bank" if mode == "deposit" else "Withdraw from Maze Bank"
        super().__init__(title=title)
        self.cog = cog
        self.mode = mode
        self.amount = discord.ui.TextInput(
            label="Amount",
            placeholder="1000",
            required=True,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Invalid amount.", ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message("Amount must be positive.", ephemeral=True)

        uid = interaction.user.id
        u = self.cog.data.get_user(uid)
        wallet = int(u.get("wallet", 0))
        bank = int(u.get("bank", 0))

        if self.mode == "deposit":
            if wallet < amount:
                return await interaction.response.send_message(
                    f"Insufficient wallet funds. You have **{_fmt(wallet)}** {CURRENCY}.",
                    ephemeral=True,
                )
            self.cog.data.add_money(uid, -amount, "bank_deposit")
            self.cog.data.add_bank(uid, amount)
            embed = discord.Embed(
                title="📥 Deposit Successful",
                description=(
                    f"You deposited **{_fmt(amount)}** {CURRENCY} into your Maze Bank account.\n\n"
                    f"**Wallet:** {_fmt(wallet - amount)} {CURRENCY}\n"
                    f"**Bank Deposit:** {_fmt(bank + amount)} {CURRENCY}"
                ),
                color=COLOR_SUCCESS,
            )
        else:
            if bank < amount:
                return await interaction.response.send_message(
                    f"Insufficient bank funds. You have **{_fmt(bank)}** {CURRENCY} deposited.",
                    ephemeral=True,
                )
            self.cog.data.add_bank(uid, -amount)
            self.cog.data.add_money(uid, amount, "bank_withdraw")
            embed = discord.Embed(
                title="📤 Withdrawal Successful",
                description=(
                    f"You withdrew **{_fmt(amount)}** {CURRENCY} from your Maze Bank account.\n\n"
                    f"**Wallet:** {_fmt(wallet + amount)} {CURRENCY}\n"
                    f"**Bank Deposit:** {_fmt(bank - amount)} {CURRENCY}"
                ),
                color=COLOR_SUCCESS,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
# CAR THEFT JOB
# ═══════════════════════════════════════════════════════════════════════════

def _has_warehouse(u: Dict) -> bool:
    inv = u.get("inventory", {})
    return inv.get("biz_warehouse", 0) >= 1


def _count_stolen_vehicles(u: Dict) -> int:
    inv = u.get("inventory", {})
    return sum(1 for iid in inv if iid.startswith("theft_"))


def _get_stolen_vehicles(u: Dict) -> List[Dict[str, Any]]:
    inv = u.get("inventory", {})
    result = []
    for car in CAR_THEFT_VEHICLES:
        qty = inv.get(car["id"], 0)
        if qty > 0:
            for _ in range(qty):
                result.append(car)
    return result


class CarTheftJobView(discord.ui.View):
    """Main Car Theft Job panel — requires Warehouse."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self, u: Dict) -> discord.Embed:
        settings = self.cog.data.get_settings()
        stolen_count = _count_stolen_vehicles(u)
        max_veh = settings.get("warehouse_max_vehicles", 30)
        cost = settings.get("car_theft_cost", 1000)
        embed = discord.Embed(
            title="🚗 Car Theft Job",
            description=(
                "Steal high-value vehicles across Los Santos and store them in your Warehouse.\n"
                "Export them later for a clean payout.\n\n"
                f"**Warehouse storage:** {stolen_count}/{max_veh} vehicles\n"
                f"**Car Theft fee:** {_fmt(cost)} {CURRENCY}\n"
                f"**Car Theft cooldown:** 8 hours\n"
                f"**Export cooldown:** 12 hours\n\n"
                "• **Car Theft** — pay the fee, pick a class (Low / Medium / High), risk the steal\n"
                "• **Export a Car** — sell one stored vehicle (100% success)\n"
                "• **Warehouse** — view all stolen vehicles currently stored"
            ),
            color=COLOR_ORANGE,
        )
        embed.set_image(url=IMG["vehicle_exports"])
        embed.set_footer(text="Car Theft Job · Requires Warehouse · Private")
        return embed

    @discord.ui.button(label="🚗 Car Theft", style=discord.ButtonStyle.danger, row=0)
    async def car_theft(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_car_theft", 0))
        cd = settings.get("car_theft_cooldown", 28800)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ Car Theft Cooldown",
                description=f"You can attempt another theft in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        max_veh = settings.get("warehouse_max_vehicles", 30)
        if _count_stolen_vehicles(u) >= max_veh:
            embed = discord.Embed(
                title="🏭 Warehouse Full",
                description=f"Your Warehouse is full (**{max_veh}/{max_veh}**). Export some cars first.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        cost = settings.get("car_theft_cost", 1000)
        if u["wallet"] < cost:
            embed = discord.Embed(
                title="💸 Insufficient Funds",
                description=f"Car Theft costs **{_fmt(cost)}** {CURRENCY}. You have **{_fmt(u['wallet'])}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Confirmation view
        view = CarTheftConfirmView(self.cog, self.user_id, cost)
        embed = discord.Embed(
            title="🚗 Confirm Car Theft",
            description=(
                f"You are about to pay **{_fmt(cost)}** {CURRENCY} to start a Car Theft run.\n\n"
                "After confirming you will choose a vehicle class:\n"
                "• **Low** — 75% success · lower payout\n"
                "• **Medium** — 50% success · medium payout\n"
                "• **High** — 35% success · high payout\n\n"
                "Do you accept the fee and start?"
            ),
            color=COLOR_ORANGE,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📦 Export a Car", style=discord.ButtonStyle.success, row=0)
    async def export_car(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_export_car", 0))
        cd = settings.get("export_car_cooldown", 43200)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ Export Cooldown",
                description=f"You can export another car in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        stolen = _get_stolen_vehicles(u)
        if not stolen:
            embed = discord.Embed(
                title="📦 Empty Warehouse",
                description="You have no stolen vehicles to export. Go steal some first!",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Build select options (unique by id, show qty)
        inv = u.get("inventory", {})
        seen = {}
        options = []
        for car in CAR_THEFT_VEHICLES:
            qty = inv.get(car["id"], 0)
            if qty > 0 and car["id"] not in seen:
                seen[car["id"]] = True
                options.append(discord.SelectOption(
                    label=f"{car.get('emoji', '🚗')} {car['name']}"[:100],
                    value=car["id"],
                    description=f"Export for {_fmt(car['price'])} {CURRENCY} · ×{qty}"[:100],
                ))
        if not options:
            return await interaction.response.send_message("No vehicles available.", ephemeral=True)

        view = CarExportSelectView(self.cog, self.user_id, options[:25])
        embed = discord.Embed(
            title="📦 Export a Car",
            description=(
                "Select a vehicle from your Warehouse to export.\n"
                "Success rate: **100%**. Payout is the estimated value of the car.\n"
                "Cooldown: **12 hours** after export."
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏭 Warehouse", style=discord.ButtonStyle.primary, row=0)
    async def warehouse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        settings = self.cog.data.get_settings()
        max_veh = settings.get("warehouse_max_vehicles", 30)
        stolen = _get_stolen_vehicles(u)
        if not stolen:
            embed = discord.Embed(
                title="🏭 Warehouse",
                description=(
                    f"**Storage:** 0/{max_veh} vehicles\n\n"
                    "Your Warehouse is empty.\n"
                    "Use **Car Theft** or claim a **Spawn Export Event** to fill it."
                ),
                color=COLOR_INFO,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Group by id
        inv = u.get("inventory", {})
        lines = []
        total = 0
        for car in CAR_THEFT_VEHICLES:
            qty = inv.get(car["id"], 0)
            if qty > 0:
                lines.append(
                    f"{car.get('emoji', '🚗')} **{car['name']}** ×{qty} "
                    f"— {_fmt(car['price'])} {CURRENCY} each · class **{car['class'].upper()}**"
                )
                total += qty
        embed = discord.Embed(
            title="🏭 Warehouse — Stolen Vehicles",
            description=(
                f"**Storage:** {total}/{max_veh} vehicles\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_ORANGE,
        )
        embed.set_footer(text="Car Theft Job · Warehouse")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CarTheftConfirmView(discord.ui.View):
    """Confirm fee payment then choose class."""

    def __init__(self, cog: "Economy", user_id: int, cost: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.cost = cost

    @discord.ui.button(label="✅ Accept & Start", style=discord.ButtonStyle.success, row=0)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        if u["wallet"] < self.cost:
            return await interaction.response.send_message(
                f"Insufficient funds. Need **{_fmt(self.cost)}** {CURRENCY}.", ephemeral=True
            )
        # Charge fee now
        self.cog.data.add_money(self.user_id, -self.cost, "car_theft_fee")
        view = CarTheftClassView(self.cog, self.user_id)
        embed = discord.Embed(
            title="🚗 Choose Vehicle Class",
            description=(
                f"Fee of **{_fmt(self.cost)}** {CURRENCY} paid.\n\n"
                "Select the class of vehicle you want to steal:\n\n"
                "🟢 **Low** — 75% success chance · lower value cars\n"
                "🟡 **Medium** — 50% success chance · sports / muscle\n"
                "🔴 **High** — 35% success chance · super / hypercars"
            ),
            color=COLOR_ORANGE,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        embed = discord.Embed(
            title="Cancelled",
            description="Car Theft cancelled. No fee was charged.",
            color=COLOR_INFO,
        )
        await interaction.response.edit_message(embed=embed, view=None)


class CarTheftClassView(discord.ui.View):
    """Pick Low / Medium / High class."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="🟢 Low Class", style=discord.ButtonStyle.success, row=0)
    async def low(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "low")

    @discord.ui.button(label="🟡 Medium Class", style=discord.ButtonStyle.primary, row=0)
    async def medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "medium")

    @discord.ui.button(label="🔴 High Class", style=discord.ButtonStyle.danger, row=0)
    async def high(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "high")

    async def _resolve(self, interaction: discord.Interaction, car_class: str):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        pool = CAR_THEFT_BY_CLASS.get(car_class, [])
        if not pool:
            return await interaction.response.send_message("No vehicles in this class.", ephemeral=True)

        car = random.choice(pool)
        chance = CAR_THEFT_SUCCESS_CHANCE.get(car_class, 0.5)
        success = random.random() < chance

        # Start cooldown
        u = self.cog.data.get_user(self.user_id)
        u["last_car_theft"] = _now_ts()
        self.cog.data.save_user(self.user_id, u)

        if success:
            # Check capacity again (race safety)
            settings = self.cog.data.get_settings()
            max_veh = settings.get("warehouse_max_vehicles", 30)
            if _count_stolen_vehicles(u) >= max_veh:
                embed = discord.Embed(
                    title="🏭 Warehouse Full",
                    description="You stole the car but your Warehouse is full. The vehicle was lost.",
                    color=COLOR_FAIL,
                )
                await interaction.response.edit_message(embed=embed, view=None)
                return

            inv = u.get("inventory", {})
            inv[car["id"]] = inv.get(car["id"], 0) + 1
            u["inventory"] = inv
            self.cog.data.save_user(self.user_id, u)

            embed = discord.Embed(
                title="✅ Car Theft Successful!",
                description=(
                    f"You stole a **{car.get('emoji', '🚗')} {car['name']}** "
                    f"(**{car_class.upper()}** class)!\n\n"
                    f"Estimated export value: **{_fmt(car['price'])}** {CURRENCY}\n"
                    f"The vehicle has been stored in your **Warehouse**."
                ),
                color=COLOR_SUCCESS,
            )
            embed.set_footer(text="Car Theft Job · Cooldown started (8h)")
            await interaction.response.edit_message(embed=embed, view=None)

            public = discord.Embed(
                title="🚗 Car Theft Successful",
                description=(
                    f"{interaction.user.mention} stole a **{car.get('emoji', '🚗')} {car['name']}** "
                    f"({car_class.upper()} class) and stored it in their Warehouse!"
                ),
                color=COLOR_SUCCESS,
            )
            await post_to_market(self.cog.bot, interaction.user, public, gif_key="mission_passed")
        else:
            embed = discord.Embed(
                title="💥 Car Theft Failed",
                description=(
                    f"You tried to steal a **{car.get('emoji', '🚗')} {car['name']}** "
                    f"({car_class.upper()} class) but got spotted / the alarm went off.\n\n"
                    "No vehicle acquired. Fee already paid."
                ),
                color=COLOR_FAIL,
            )
            embed.set_footer(text="Car Theft Job · Cooldown started (8h)")
            lose = _apply_gif_image(embed, "lose_game")
            kwargs = {"embed": embed, "view": None}
            if lose:
                kwargs["attachments"] = [lose]
            await interaction.response.edit_message(**kwargs)

            public = discord.Embed(
                title="💥 Car Theft Failed",
                description=f"{interaction.user.mention} failed a **{car_class.upper()}** class Car Theft attempt.",
                color=COLOR_FAIL,
            )
            await post_to_market(self.cog.bot, interaction.user, public, gif_key="lose_game")


class CarExportSelectView(discord.ui.View):
    """Select a stolen car to export (100% success)."""

    def __init__(self, cog: "Economy", user_id: int, options: List[discord.SelectOption]):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        select = discord.ui.Select(placeholder="Choose a vehicle to export…", options=options)
        select.callback = self._export
        self.add_item(select)

    async def _export(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        car_id = interaction.data["values"][0]
        car = next((c for c in CAR_THEFT_VEHICLES if c["id"] == car_id), None)
        if not car:
            return await interaction.response.send_message("Vehicle not found.", ephemeral=True)

        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        if inv.get(car_id, 0) < 1:
            return await interaction.response.send_message("You no longer own this vehicle.", ephemeral=True)

        # Remove one
        inv[car_id] = inv.get(car_id, 0) - 1
        if inv[car_id] <= 0:
            inv.pop(car_id, None)
        u["inventory"] = inv
        u["last_export_car"] = _now_ts()
        self.cog.data.save_user(self.user_id, u)

        reward = car["price"]
        self.cog.data.add_money(self.user_id, reward, "car_export")

        embed = discord.Embed(
            title="✅ Export Successful!",
            description=(
                f"You exported **{car.get('emoji', '🚗')} {car['name']}**.\n\n"
                f"Payout: **{_fmt(reward)}** {CURRENCY}\n"
                f"The vehicle has been removed from your Warehouse."
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Car Theft Job · Export cooldown started (12h)")
        await interaction.response.edit_message(embed=embed, view=None)

        public = discord.Embed(
            title="📦 Vehicle Exported",
            description=(
                f"{interaction.user.mention} exported a **{car.get('emoji', '🚗')} {car['name']}** "
                f"and received **{_fmt(reward)}** {CURRENCY}!"
            ),
            color=COLOR_SUCCESS,
        )
        await post_to_market(self.cog.bot, interaction.user, public, gif_key="mission_passed")


# ═══════════════════════════════════════════════════════════════════════════
# FREAKSHOP — Dax & the Fooliganz
# ═══════════════════════════════════════════════════════════════════════════

DAX_BADONKADONK_LINES = [
    (
        "**BADONKADONK!**\n\n"
        "Freshmeat… you just swallowed something Labrat mixed in the dark. "
        "Colors are melting, the walls are breathing, and a UFO just parked on your roof. "
        "Deep down, you've always been a Fooligan. Just like cousin Wade.\n\n"
        "Know what a Fooligan is? Folks are gonna tell you it's all about a band, "
        "or getting fucked up, or walking around with your junk out. "
        "And yeah, that's a big part of it. But it's also about **not giving a fuck**.\n\n"
        "Here's **{reward}** {currency}. Don't spend it all on more of the good stuff… or do. "
        "We're here to stay, baby!"
    ),
    (
        "**BADONKADONK!**\n\n"
        "Yo Freshmeat! Labrat says that batch was *extra*. "
        "You're currently communicating with three different versions of yourself "
        "and one of them is a rabbit wearing sunglasses.\n\n"
        "The Fooligan life ain't for everyone, but if you're into easy money and hard partying, "
        "there's nothing better. Take this **{reward}** {currency} and go stare at a wall for a while. "
        "It's a beautiful wall."
    ),
    (
        "**BADONKADONK!**\n\n"
        "Freshmeat… I can see the music. Can you see the music? "
        "The bassline is shaped like a pyramid and it's telling me secrets about Mount Chiliad.\n\n"
        "Deep down, you've always been a Fooligan. "
        "Here's **{reward}** {currency} from the troupe. "
        "Spend it wisely. Or don't. Wisdom is a construct of the squares."
    ),
    (
        "**BADONKADONK!**\n\n"
        "Freshmeat, you just opened a door in your mind that Labrat didn't know existed. "
        "There's a little green man in there selling bootleg concert tickets.\n\n"
        "We're here to stay, baby! Take **{reward}** {currency}. "
        "The Fooliganz take care of their own… even the ones currently talking to furniture."
    ),
    (
        "**BADONKADONK!**\n\n"
        "Freshmeat! That hit harder than a Lost MC slamvan. "
        "Your third eye is wide open and it's judging my outfit.\n\n"
        "Deep down, you've always been a Fooligan. Just like cousin Wade. "
        "Here's **{reward}** {currency}. Go buy something shiny. Or a bigger third eye."
    ),
    (
        "**BADONKADONK!**\n\n"
        "Yo Freshmeat… the walls just told me a joke and I can't stop laughing. "
        "Labrat says that's normal. Labrat also says he's a professional.\n\n"
        "The Fooligan life ain't for everyone… but you? You're one of us. "
        "Pocket this **{reward}** {currency} and keep the vibes high."
    ),
    (
        "**BADONKADONK!**\n\n"
        "Freshmeat, you just became one with the universe for approximately forty-seven seconds. "
        "The universe said hi and asked for a cigarette.\n\n"
        "We're here to stay, baby! Take **{reward}** {currency} from Dax and the troupe. "
        "Don't tell the squares what you saw."
    ),
    (
        "**BADONKADONK!**\n\n"
        "Freshmeat… I think I'm in your head. Wait, am I in your head? "
        "This is deep water, my friend. Classic tunnel phase.\n\n"
        "Deep down, you've always been a Fooligan. "
        "Here's **{reward}** {currency}. Consider it initiation money. "
        "Welcome to the clinical trial."
    ),
]

FREAKSHOP_JOBS = [
    {
        "id": "crop_dustin",
        "label": "🌿 Crop Dustin'",
        "desc": "Sabotage a rival weed farm. Nuke their mild high.",
        "success": (
            "**Crop Dustin' — SUCCESS**\n\n"
            "Freshmeat! You dusted that corporate weed farm like a true Fooligan. "
            "Their 'mild high' is now a mild pile of ash.\n\n"
            "Dax wired you **{reward}** {currency}. BADONKADONK!"
        ),
        "fail": (
            "**Crop Dustin' — FAILED**\n\n"
            "Freshmeat… the sprinklers got you before you got the crops. "
            "Labrat is laughing. Dax is disappointed. Mostly laughing.\n\n"
            "You lost **{penalty}** {currency}. Try not to inhale the failure next time."
        ),
    },
    {
        "id": "heavy_metal",
        "label": "🔧 Heavy Metal",
        "desc": "Recover a suspicious shipment before the wrong people do.",
        "success": (
            "**Heavy Metal — SUCCESS**\n\n"
            "Freshmeat! You recovered the load. Heavy, metal, and extremely illegal. "
            "Exactly how we like it.\n\n"
            "Dax sent **{reward}** {currency} your way. The troupe is proud. Mostly high."
        ),
        "fail": (
            "**Heavy Metal — FAILED**\n\n"
            "Freshmeat… the shipment walked away. Or got walked away. "
            "Either way, it's gone and so is some of your cash.\n\n"
            "You lost **{penalty}** {currency}. Dax says dig deeper next time. Literally."
        ),
    },
    {
        "id": "bad_trip",
        "label": "🌀 Bad Trip",
        "desc": "Survive a fully unhinged psychedelic experience.",
        "success": (
            "**Bad Trip — SUCCESS**\n\n"
            "Freshmeat! You rode the wave and came out the other side. "
            "The rabbits were real. The Bigfoot was real. Your dignity is negotiable.\n\n"
            "Dax hands you **{reward}** {currency}. You're officially harder than the trip."
        ),
        "fail": (
            "**Bad Trip — FAILED**\n\n"
            "Freshmeat… the trip ate you alive. Labrat found you talking to a traffic cone "
            "about government eggs on Mount Chiliad.\n\n"
            "You lost **{penalty}** {currency}. The cone kept the rest."
        ),
    },
    {
        "id": "delivery_gone_wrong",
        "label": "🚚 Delivery Gone Wrong",
        "desc": "Make a delivery for Dax. What could possibly go wrong?",
        "success": (
            "**Delivery Gone Wrong — SUCCESS**\n\n"
            "Freshmeat! You delivered the package. Nobody died. "
            "Well… nobody *important* died. That's a win in this business.\n\n"
            "Dax drops **{reward}** {currency} on you. We're here to stay, baby!"
        ),
        "fail": (
            "**Delivery Gone Wrong — FAILED**\n\n"
            "Freshmeat… the delivery went exactly as the name suggested. "
            "Wrong. Very wrong. Cops, rivals, and one very angry raccoon.\n\n"
            "You lost **{penalty}** {currency}. Dax says next time bring snacks for the raccoon."
        ),
    },
]


class FreakShopView(discord.ui.View):
    """The Freakshop — Dax, Labrat, and the Fooliganz. Fully anonymous / ephemeral."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🌀 The Freakshop",
            description=(
                "**Los Santos Drug Wars · Fooliganz HQ**\n\n"
                "Welcome to the Freakshop, Freshmeat.\n"
                "Dax is in the back. Labrat is mixing something. "
                "The walls might be breathing.\n\n"
                "• **Badonkadonk** — take the dose, hear from Dax, get paid *(12h cooldown)*\n"
                "• **Call Dax** — request Fooligan work *(8h cooldown)*\n"
                "• **Labrat** — accelerate production, shave time off Call Dax *(24h cooldown)*\n\n"
                "*Deep down, you've always been a Fooligan.*"
            ),
            color=COLOR_PURPLE,
        )
        gif = _gif_file("acid_lab")
        if gif is not None:
            embed.set_image(url=f"attachment://{gif.filename}")
        else:
            embed.set_image(url=IMG["acid_lab"])
        embed.set_footer(text="Freakshop · Fooliganz · Anonymous · Dax is watching")
        return embed

    def build_files(self) -> List[discord.File]:
        f = _gif_file("acid_lab")
        return [f] if f else []

    @discord.ui.button(label="💊 Badonkadonk", style=discord.ButtonStyle.danger, row=0)
    async def badonkadonk(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your trip.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_badonkadonk", 0))
        cd = settings.get("badonkadonk_cooldown", 43200)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ Still Tripping",
                description=(
                    f"Freshmeat, the last dose hasn't worn off yet.\n"
                    f"Come back in **{_fmt_time(rem)}**.\n\n"
                    "Labrat's orders."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        reward = settings.get("badonkadonk_reward", 500)
        u["last_badonkadonk"] = now
        self.cog.data.save_user(self.user_id, u)
        self.cog.data.add_money(self.user_id, reward, "badonkadonk")

        template = random.choice(DAX_BADONKADONK_LINES)
        text = template.format(reward=_fmt(reward), currency=CURRENCY)
        embed = discord.Embed(
            title="💊 BADONKADONK!",
            description=text,
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="Dax · The Freakshop · 12h cooldown")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📞 Call Dax", style=discord.ButtonStyle.primary, row=0)
    async def call_dax(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your call.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_call_dax", 0))
        cd = settings.get("call_dax_cooldown", 28800)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="📞 Dax is Busy",
                description=(
                    f"Freshmeat, Dax isn't answering right now.\n"
                    f"Try again in **{_fmt_time(rem)}**.\n\n"
                    "He's probably mid-trip or arguing with Labrat."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        view = CallDaxJobView(self.cog, self.user_id)
        embed = discord.Embed(
            title="📞 Dax is calling...",
            description=(
                "**Incoming call from Dax**\n\n"
                "\"Yo Freshmeat! I got work for you. "
                "Could make you a lot of money… could go very wrong… "
                "probably both. That's the Fooligan way.\"\n\n"
                "Pick a job. 50/50 odds.\n"
                f"• Success → **{_fmt(settings.get('call_dax_success_reward', 1000))}** {CURRENCY}\n"
                f"• Failure → lose **{_fmt(settings.get('call_dax_fail_penalty', 500))}** {CURRENCY}"
            ),
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="Fooligan Jobs · Call Dax · 8h cooldown after attempt")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🐀 Labrat", style=discord.ButtonStyle.secondary, row=0)
    async def labrat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your lab.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_labrat", 0))
        cd = settings.get("labrat_cooldown", 86400)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="🐀 Labrat is Busy",
                description=(
                    f"Labrat is still cooking the last batch.\n"
                    f"Come back in **{_fmt_time(rem)}**.\n\n"
                    "\"Science takes time, Freshmeat.\""
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        reduce_sec = settings.get("labrat_reduce_seconds", 18000)  # 5 hours
        last_dax = float(u.get("last_call_dax", 0))
        if last_dax > 0:
            # Pull Call Dax cooldown forward by 5 hours
            u["last_call_dax"] = max(0.0, last_dax - reduce_sec)
        u["last_labrat"] = now
        self.cog.data.save_user(self.user_id, u)

        embed = discord.Embed(
            title="🐀 Labrat",
            description=(
                "You accelerated production, and the recharge time decreased.\n\n"
                "**Try calling Dax again.**\n\n"
                "Labrat nods from behind a cloud of purple smoke.\n"
                "\"Five hours shaved off. Don't thank me — thank the formula.\""
            ),
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Labrat · Production boost · 24h cooldown")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CallDaxJobView(discord.ui.View):
    """Choose one of the four Fooligan-style jobs after calling Dax."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        for job in FREAKSHOP_JOBS:
            btn = discord.ui.Button(
                label=job["label"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"freak_job_{job['id']}",
            )
            btn.callback = self._make_callback(job)
            self.add_item(btn)

    def _make_callback(self, job: Dict):
        async def _cb(interaction: discord.Interaction):
            await self._resolve(interaction, job)
        return _cb

    async def _resolve(self, interaction: discord.Interaction, job: Dict):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your job.", ephemeral=True)

        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()

        # Apply Call Dax cooldown now
        u["last_call_dax"] = now
        self.cog.data.save_user(self.user_id, u)

        success = random.random() < 0.50
        if success:
            reward = settings.get("call_dax_success_reward", 1000)
            self.cog.data.add_money(self.user_id, reward, "call_dax")
            text = job["success"].format(reward=_fmt(reward), currency=CURRENCY)
            color = COLOR_SUCCESS
            title = f"✅ {job['label']}"
        else:
            penalty = settings.get("call_dax_fail_penalty", 500)
            # Only deduct if they have the money
            wallet = int(u.get("wallet", 0))
            actual = min(penalty, wallet)
            if actual > 0:
                self.cog.data.add_money(self.user_id, -actual, "call_dax_fail")
            text = job["fail"].format(penalty=_fmt(actual), currency=CURRENCY)
            color = COLOR_FAIL
            title = f"💥 {job['label']}"

        embed = discord.Embed(
            title=title,
            description=text,
            color=color,
        )
        embed.set_footer(text="Fooligan Job · Call Dax · 8h cooldown started")
        await interaction.response.edit_message(embed=embed, view=None)


# ═══════════════════════════════════════════════════════════════════════════
# DOOMSDAY HEIST
# ═══════════════════════════════════════════════════════════════════════════

def _doomsday_prep_progress(u: Dict) -> Tuple[int, List[str]]:
    inv = u.get("inventory", {})
    owned, missing = [], []
    for it in DOOMSDAY_PREP_ITEMS:
        if inv.get(it["id"], 0) >= 1:
            owned.append(it["id"])
        else:
            missing.append(it["id"])
    return len(owned), missing


# Active invite / heist sessions: invite_id -> state dict
_doomsday_sessions: Dict[str, Dict[str, Any]] = {}


class DoomsdayMainView(discord.ui.View):
    """Main Doomsday Heist panel (ephemeral). Free prep items, 1 every 12h."""

    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    def build_embed(self, u: Dict) -> discord.Embed:
        inv = u.get("inventory", {})
        lines = []
        for it in DOOMSDAY_PREP_ITEMS:
            qty = inv.get(it["id"], 0)
            status = "✅" if qty >= 1 else "❌"
            lines.append(f"{status} {it.get('emoji', '')} **{it['name']}**" + (f" (owned)" if qty else " — free claim"))
        owned_count, _ = _doomsday_prep_progress(u)
        ticket_qty = inv.get("dd_ticket", 0)
        embed = discord.Embed(
            title="☢️ The Doomsday Heist",
            description=(
                "Three acts. One facility. Global threat.\n"
                "Claim free prep items (1 every **12 hours**), deliver the full set for a **Ticket**, "
                "then invite a partner and launch.\n\n"
                f"**Prep progress:** {owned_count}/5 items\n"
                f"**Tickets owned:** {ticket_qty}\n\n"
                + "\n".join(lines)
                + "\n\n"
                "**Launch requires a partner** (friend or employee Gustavo Mota).\n"
                "Total prize pool: **5.000** Bovas coins (split 70% / 30%).\n"
                "With Gustavo you receive **50%** of the pool."
            ),
            color=COLOR_FAIL,
        )
        embed.set_image(url=IMG["doomsday"])
        embed.set_footer(text="Doomsday Heist · Free prep · Partner required · Private")
        return embed

    @discord.ui.button(label="📥 Claim Prep Item", style=discord.ButtonStyle.primary, row=0)
    async def claim_prep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your panel.", ephemeral=True)
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(self.user_id)
        now = _now_ts()
        last = float(u.get("last_doomsday_prep", 0))
        cd = settings.get("doomsday_prep_cooldown", 43200)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="⏳ Prep Cooldown",
                description=f"You can claim another prep item in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        owned_count, missing = _doomsday_prep_progress(u)
        if not missing:
            embed = discord.Embed(
                title="✅ All Prep Owned",
                description="You already have all 5 prep items. Deliver the set for a Ticket.",
                color=COLOR_INFO,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Claim the next missing item (in list order)
        next_id = missing[0]
        item = next(it for it in DOOMSDAY_PREP_ITEMS if it["id"] == next_id)
        inv = u.get("inventory", {})
        inv[next_id] = inv.get(next_id, 0) + 1
        u["inventory"] = inv
        u["last_doomsday_prep"] = now
        self.cog.data.save_user(self.user_id, u)
        owned_count, _ = _doomsday_prep_progress(u)

        embed = discord.Embed(
            title="📥 Prep Item Claimed",
            description=(
                f"You claimed **{item.get('emoji', '')} {item['name']}** (free).\n\n"
                f"Prep progress: **{owned_count}/5**\n"
                f"Next claim available in **12 hours**."
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📦 Deliver Prep Set", style=discord.ButtonStyle.success, row=0)
    async def deliver(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your panel.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        owned_count, missing = _doomsday_prep_progress(u)
        if owned_count < 5:
            names = [it["name"] for it in DOOMSDAY_PREP_ITEMS if it["id"] in missing]
            embed = discord.Embed(
                title="📦 Incomplete Set",
                description="You still need:\n• " + "\n• ".join(names) + "\n\nClaim the missing items first.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        inv = u.get("inventory", {})
        for iid in DOOMSDAY_PREP_IDS:
            inv[iid] = max(0, inv.get(iid, 0) - 1)
            if inv[iid] == 0:
                inv.pop(iid, None)
        inv["dd_ticket"] = inv.get("dd_ticket", 0) + 1
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)

        embed = discord.Embed(
            title="✅ Prep Set Delivered!",
            description=(
                "You handed over the full preparation kit.\n\n"
                f"Received: **🎟️ Doomsday Heist Ticket** ×1\n"
                f"Tickets now: **{inv['dd_ticket']}**\n\n"
                "Use **Launch Heist** and invite a partner when ready."
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
        if inv.get("dd_ticket", 0) < 1:
            embed = discord.Embed(
                title="🎟️ No Ticket",
                description="You need a **Doomsday Heist Ticket**. Deliver a full prep set first.",
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        view = DoomsdayInviteChoiceView(self.cog, self.user_id)
        embed = discord.Embed(
            title="🚀 Launch Doomsday Heist",
            description=(
                "You cannot run this heist alone.\n\n"
                "**Invite a friend** from the server — they get **30%**, you keep **70%** of the final payout.\n"
                "**Or hire employee Gustavo Mota** — you receive only **50%** of the total prize pool "
                "(no real partner share).\n\n"
                f"Base prize pool: **{_fmt(self.cog.data.get_settings().get('doomsday_total_prize', 5000))}** {CURRENCY}\n"
                "4 memory stages × 25% each. Fail a stage = lose that 25%."
            ),
            color=COLOR_FAIL,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DoomsdayInviteChoiceView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="👥 Invite Friend", style=discord.ButtonStyle.primary, row=0)
    async def invite_friend(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        await interaction.response.send_modal(DoomsdayInviteModal(self.cog, self.user_id))

    @discord.ui.button(label="👷 Hire Gustavo Mota", style=discord.ButtonStyle.secondary, row=0)
    async def hire_gustavo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        # Consume ticket and start solo-with-NPC heist (50% pool)
        u = self.cog.data.get_user(self.user_id)
        inv = u.get("inventory", {})
        if inv.get("dd_ticket", 0) < 1:
            return await interaction.response.send_message("No ticket left.", ephemeral=True)
        inv["dd_ticket"] -= 1
        if inv["dd_ticket"] <= 0:
            inv.pop("dd_ticket", None)
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)

        session_id = f"dd_{self.user_id}_{int(_now_ts())}"
        _doomsday_sessions[session_id] = {
            "leader_id": self.user_id,
            "partner_id": None,  # Gustavo
            "is_npc": True,
            "stages_done": 0,
            "stages_ok": 0,
            "current_player": "leader",  # leader does all 4 stages when NPC
            "prize_pool": int(self.cog.data.get_settings().get("doomsday_total_prize", 5000) * 0.50),
        }
        view = DoomsdayMemoryView(self.cog, session_id, self.user_id)
        embed = view.build_show_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class DoomsdayInviteModal(discord.ui.Modal, title="Invite Partner to Doomsday Heist"):
    def __init__(self, cog: "Economy", leader_id: int):
        super().__init__()
        self.cog = cog
        self.leader_id = leader_id
        self.target = discord.ui.TextInput(
            label="User ID or @mention",
            placeholder="123456789 or @username",
            required=True,
        )
        self.add_item(self.target)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.target.value.strip().replace("<@", "").replace("!", "").replace(">", "")
        try:
            partner_id = int(raw)
        except ValueError:
            return await interaction.response.send_message("Invalid user ID.", ephemeral=True)
        if partner_id == self.leader_id:
            return await interaction.response.send_message("You cannot invite yourself.", ephemeral=True)

        # Consume ticket now
        u = self.cog.data.get_user(self.leader_id)
        inv = u.get("inventory", {})
        if inv.get("dd_ticket", 0) < 1:
            return await interaction.response.send_message("No ticket left.", ephemeral=True)
        inv["dd_ticket"] -= 1
        if inv["dd_ticket"] <= 0:
            inv.pop("dd_ticket", None)
        u["inventory"] = inv
        self.cog.data.save_user(self.leader_id, u)

        settings = self.cog.data.get_settings()
        timeout = settings.get("doomsday_invite_timeout", 900)
        session_id = f"dd_{self.leader_id}_{partner_id}_{int(_now_ts())}"
        _doomsday_sessions[session_id] = {
            "leader_id": self.leader_id,
            "partner_id": partner_id,
            "is_npc": False,
            "stages_done": 0,
            "stages_ok": 0,
            "current_player": "leader",
            "prize_pool": settings.get("doomsday_total_prize", 5000),
            "accepted": False,
            "expires": _now_ts() + timeout,
        }

        # Post invite to Market channel
        partner = interaction.guild.get_member(partner_id) if interaction.guild else None
        mention = partner.mention if partner else f"<@{partner_id}>"
        leader = interaction.user

        embed = discord.Embed(
            title="☢️ Doomsday Heist Invitation",
            description=(
                f"{mention}, you have been invited by {leader.mention} to the **Doomsday Heist**!\n\n"
                f"• Prize pool: **{_fmt(settings.get('doomsday_total_prize', 5000))}** {CURRENCY}\n"
                f"• Your share on success: **30%**\n"
                f"• 4 memory stages (you each complete 2)\n\n"
                f"You have **15 minutes** to accept or decline."
            ),
            color=COLOR_FAIL,
        )
        view = DoomsdayInviteResponseView(self.cog, session_id)
        await post_to_market(self.cog.bot, leader, embed, view=view, content=mention)
        await interaction.response.send_message(
            f"✅ Invitation sent to {mention} in <#{MARKET_CHANNEL_ID}>. Waiting up to 15 minutes…",
            ephemeral=True,
        )


class DoomsdayInviteResponseView(discord.ui.View):
    def __init__(self, cog: "Economy", session_id: str):
        super().__init__(timeout=900)
        self.cog = cog
        self.session_id = session_id

    @discord.ui.button(label="✅ Accept Heist", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = _doomsday_sessions.get(self.session_id)
        if not session:
            return await interaction.response.send_message("This invitation has expired.", ephemeral=True)
        if interaction.user.id != session["partner_id"]:
            return await interaction.response.send_message("This invitation is not for you.", ephemeral=True)
        if _now_ts() > session.get("expires", 0):
            _doomsday_sessions.pop(self.session_id, None)
            return await interaction.response.send_message("Invitation timed out (15 min).", ephemeral=True)
        if session.get("accepted"):
            return await interaction.response.send_message("Already accepted.", ephemeral=True)

        session["accepted"] = True
        # Notify both and start memory game for leader first
        await interaction.response.edit_message(view=None)
        public = discord.Embed(
            title="☢️ Doomsday Heist — Partner Joined!",
            description=(
                f"<@{session['partner_id']}> accepted the invitation from <@{session['leader_id']}>!\n"
                "The memory challenge begins. Leader plays first."
            ),
            color=COLOR_SUCCESS,
        )
        await post_to_market(self.cog.bot, interaction.user, public)

        # Send ephemeral start to leader
        leader = self.cog.bot.get_user(session["leader_id"])
        if leader:
            try:
                view = DoomsdayMemoryView(self.cog, self.session_id, session["leader_id"])
                embed = view.build_show_embed()
                await leader.send(embed=embed, view=view)
            except Exception:
                logger.exception("Could not DM leader for Doomsday start")

        await interaction.followup.send(
            "You joined the Doomsday Heist! Wait for the leader to complete their stages, then it will be your turn.",
            ephemeral=True,
        )

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = _doomsday_sessions.get(self.session_id)
        if not session:
            return await interaction.response.send_message("Invitation expired.", ephemeral=True)
        if interaction.user.id != session["partner_id"]:
            return await interaction.response.send_message("This invitation is not for you.", ephemeral=True)
        _doomsday_sessions.pop(self.session_id, None)
        # Refund ticket to leader
        u = self.cog.data.get_user(session["leader_id"])
        inv = u.get("inventory", {})
        inv["dd_ticket"] = inv.get("dd_ticket", 0) + 1
        u["inventory"] = inv
        self.cog.data.save_user(session["leader_id"], u)
        await interaction.response.edit_message(view=None)
        public = discord.Embed(
            title="☢️ Doomsday Heist — Declined",
            description=f"<@{session['partner_id']}> declined. Ticket refunded to <@{session['leader_id']}>.",
            color=COLOR_FAIL,
        )
        await post_to_market(self.cog.bot, interaction.user, public)


class DoomsdayMemoryView(discord.ui.View):
    """
    Memory sequence mini-game.
    Shows a sequence of 4 symbols, then player must click them in order.
    4 stages total. With friend: leader does stages 0,1 — partner does 2,3.
    With Gustavo (NPC): leader does all 4.
    """

    def __init__(self, cog: "Economy", session_id: str, player_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.session_id = session_id
        self.player_id = player_id
        session = _doomsday_sessions.get(session_id, {})
        self.sequence = random.sample(DOOMSDAY_MEMORY_SYMBOLS, 4)
        self.clicked: List[str] = []
        self.phase = "show"  # show -> input

        # Input buttons (shuffled symbols including the sequence)
        options = list(self.sequence)
        extras = [s for s in DOOMSDAY_MEMORY_SYMBOLS if s not in options]
        options += random.sample(extras, min(2, len(extras)))
        random.shuffle(options)
        for sym in options:
            btn = discord.ui.Button(label=sym, style=discord.ButtonStyle.secondary)
            btn.callback = self._make_click(sym)
            self.add_item(btn)

    def build_show_embed(self) -> discord.Embed:
        session = _doomsday_sessions.get(self.session_id, {})
        stage = session.get("stages_done", 0) + 1
        seq_str = "  ".join(self.sequence)
        embed = discord.Embed(
            title=f"☢️ Doomsday — Memory Stage {stage}/4",
            description=(
                f"**Memorize this sequence:**\n\n"
                f"# {seq_str}\n\n"
                "Click the symbols **in the same order** below.\n"
                "You have one attempt."
            ),
            color=COLOR_FAIL,
        )
        embed.set_footer(text="Doomsday Heist · Memory Challenge")
        return embed

    def _make_click(self, symbol: str):
        async def _cb(interaction: discord.Interaction):
            if interaction.user.id != self.player_id:
                return await interaction.response.send_message("Not your turn.", ephemeral=True)
            self.clicked.append(symbol)
            needed = len(self.sequence)
            if len(self.clicked) < needed:
                await interaction.response.defer()
                return

            # Evaluate
            session = _doomsday_sessions.get(self.session_id)
            if not session:
                return await interaction.response.edit_message(
                    embed=discord.Embed(title="Session expired", color=COLOR_FAIL), view=None
                )

            correct = self.clicked == self.sequence
            session["stages_done"] = session.get("stages_done", 0) + 1
            if correct:
                session["stages_ok"] = session.get("stages_ok", 0) + 1

            stage_num = session["stages_done"]
            result_txt = "✅ Correct!" if correct else f"❌ Wrong. Sequence was: {' '.join(self.sequence)}"
            embed = discord.Embed(
                title=f"Stage {stage_num}/4 — {result_txt}",
                description=f"Stages cleared so far: **{session['stages_ok']}/4** (each = 25%)",
                color=COLOR_SUCCESS if correct else COLOR_FAIL,
            )

            # Decide next
            is_npc = session.get("is_npc", False)
            if stage_num >= 4:
                await self._finish_heist(interaction, session, embed)
                return

            if is_npc:
                # Leader continues
                next_view = DoomsdayMemoryView(self.cog, self.session_id, self.player_id)
                embed.description += "\n\nNext stage loading…"
                await interaction.response.edit_message(embed=embed, view=None)
                await interaction.followup.send(embed=next_view.build_show_embed(), view=next_view, ephemeral=True)
            else:
                # Alternate: leader does 1-2, partner 3-4
                if stage_num < 2:
                    next_view = DoomsdayMemoryView(self.cog, self.session_id, session["leader_id"])
                    embed.description += "\n\nNext stage for the **leader**…"
                    await interaction.response.edit_message(embed=embed, view=None)
                    try:
                        leader = self.cog.bot.get_user(session["leader_id"])
                        if leader:
                            await leader.send(embed=next_view.build_show_embed(), view=next_view)
                    except Exception:
                        pass
                    if interaction.user.id == session["leader_id"]:
                        await interaction.followup.send("Stage recorded. Check DMs / next prompt.", ephemeral=True)
                else:
                    # Partner's turn (stages 3-4)
                    next_view = DoomsdayMemoryView(self.cog, self.session_id, session["partner_id"])
                    embed.description += "\n\nNext stage for the **partner**…"
                    await interaction.response.edit_message(embed=embed, view=None)
                    try:
                        partner = self.cog.bot.get_user(session["partner_id"])
                        if partner:
                            await partner.send(embed=next_view.build_show_embed(), view=next_view)
                    except Exception:
                        pass
                    await interaction.followup.send("Stage recorded. Partner's turn.", ephemeral=True)
        return _cb

    async def _finish_heist(self, interaction: discord.Interaction, session: Dict, last_embed: discord.Embed):
        pool = int(session.get("prize_pool", 5000))
        ok = int(session.get("stages_ok", 0))
        earned_total = int(pool * (ok / 4.0))
        is_npc = session.get("is_npc", False)
        leader_id = session["leader_id"]
        partner_id = session.get("partner_id")

        if is_npc:
            leader_share = earned_total
            partner_share = 0
        else:
            leader_share = int(earned_total * 0.70)
            partner_share = earned_total - leader_share

        if leader_share > 0:
            self.cog.data.add_money(leader_id, leader_share, "doomsday_heist")
        if partner_share > 0 and partner_id:
            self.cog.data.add_money(partner_id, partner_share, "doomsday_heist")

        # Achievement for leader
        u = self.cog.data.get_user(leader_id)
        inv = u.get("inventory", {})
        if inv.get("ach_doomsday_heist", 0) < 1:
            inv["ach_doomsday_heist"] = 1
            u["inventory"] = inv
            self.cog.data.save_user(leader_id, u)

        _doomsday_sessions.pop(self.session_id, None)

        desc = (
            f"**Stages cleared:** {ok}/4\n"
            f"**Prize pool used:** {_fmt(pool)} {CURRENCY}\n"
            f"**Total earned:** {_fmt(earned_total)} {CURRENCY}\n\n"
            f"**Leader share (70%{' / 100% with Gustavo' if is_npc else ''}):** {_fmt(leader_share)} {CURRENCY}\n"
        )
        if not is_npc and partner_id:
            desc += f"**Partner share (30%):** {_fmt(partner_share)} {CURRENCY}\n"
        desc += f"\nAchievement: **{DOOMSDAY_ACHIEVEMENT['emoji']} {DOOMSDAY_ACHIEVEMENT['name']}**"

        final = discord.Embed(
            title="🏆 Doomsday Heist Complete!",
            description=desc,
            color=COLOR_SUCCESS if ok > 0 else COLOR_FAIL,
        )
        await interaction.response.edit_message(embed=final, view=None)

        public = discord.Embed(
            title="☢️ Doomsday Heist Successful" if ok > 0 else "☢️ Doomsday Heist Finished",
            description=(
                f"<@{leader_id}> completed the Doomsday Heist "
                f"({ok}/4 stages) and earned **{_fmt(leader_share)}** {CURRENCY}!"
                + (f"\nPartner <@{partner_id}> received **{_fmt(partner_share)}** {CURRENCY}." if partner_share else "")
            ),
            color=COLOR_SUCCESS if ok > 0 else COLOR_FAIL,
        )
        await post_to_market(self.cog.bot, interaction.user, public, gif_key="mission_passed" if ok > 0 else "lose_game")


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
        embed.set_footer(text=f"GTA Economy · {title} · Coming Soon")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _coming_soon(
        self,
        interaction: discord.Interaction,
        title: str,
        image_url: str,
        blurb: str,
        gif_key: Optional[str] = None,
    ):
        embed = discord.Embed(
            title=title,
            description=(
                f"{blurb}\n\n"
                "**Coming soon.** This mission line is under construction.\n"
                "Stay tuned for the full experience."
            ),
            color=COLOR_CONSTRUCTION,
        )
        gif = _apply_gif_image(embed, gif_key) if gif_key else None
        if gif is None:
            embed.set_image(url=image_url)
        embed.set_footer(text=f"GTA Economy · {title} · Coming Soon")
        kwargs = {"embed": embed, "ephemeral": True}
        if gif is not None:
            kwargs["file"] = gif
        await interaction.response.send_message(**kwargs)

    # ── Row 0 — Core actions (green) ──
    @discord.ui.button(label="📅 Daily", style=discord.ButtonStyle.success, custom_id="eco_daily", row=0)
    async def btn_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Daily is always ephemeral — only visible to the member who claimed it."""
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        u = self.cog.data.get_user(uid)
        settings = self.cog.data.get_settings()
        now = _now_ts()
        last = float(u.get("last_daily", 0))
        cd = settings.get("daily_cooldown", 64800)
        if now - last < cd:
            rem = int(cd - (now - last))
            embed = discord.Embed(
                title="📅 Daily already claimed",
                description=f"Come back in **{_fmt_time(rem)}**.",
                color=COLOR_FAIL,
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        embed, _ = await self.cog.handle_member_action(interaction, "daily", force_private=True)
        if embed:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="💼 Work", style=discord.ButtonStyle.success, custom_id="eco_work", row=0)
    async def btn_work(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Work is always ephemeral — only visible to the member who worked."""
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

        embed, _ = await self.cog.handle_member_action(interaction, "work", force_private=True)
        if embed:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="💸 Pay", style=discord.ButtonStyle.success, custom_id="eco_pay", row=0)
    async def btn_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PayModal(self.cog))

    @discord.ui.button(label="🏦 Maze Bank", style=discord.ButtonStyle.success, custom_id="eco_maze_bank", row=0)
    async def btn_maze_bank(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MazeBankMainView(self.cog, interaction.user.id)
        embed = view.build_embed(self.cog.data.get_user(interaction.user.id))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="⏳ Cooldown List", style=discord.ButtonStyle.secondary, custom_id="eco_cooldown_list", row=0)
    async def btn_cooldown_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        u = self.cog.data.get_user(uid)
        settings = self.cog.data.get_settings()
        now = _now_ts()

        def _status(last_key: str, cd_key: str, default_cd: int) -> str:
            last = float(u.get(last_key, 0))
            cd = int(settings.get(cd_key, default_cd))
            if cd <= 0:
                return "✅ Available"
            remaining = int(cd - (now - last))
            if remaining <= 0:
                return "✅ Available"
            return f"⏳ {_fmt_time(remaining)}"

        lines = [
            f"**📅 Daily** — {_status('last_daily', 'daily_cooldown', 64800)}",
            f"**💼 Work** — {_status('last_work', 'work_cooldown', 21600)}",
            f"**🏍️ MotoClub** — {_status('last_motoclub', 'motoclub_cooldown', 21600)}",
            f"**💼 CEO SecuroServ** — {_status('last_ceo', 'ceo_cooldown', 21600)}",
            f"**🎡 Lucky Wheel** — {_status('last_lucky_wheel', 'lucky_wheel_cooldown', 86400)}",
            f"**🎵 Music Entry** — {_status('last_music_entry', 'music_entry_cooldown', 14400)}",
            f"**🎧 Music Event** — {_status('last_music_event', 'music_event_cooldown', 36000)}",
            f"**🎉 Penthouse Party** — {_status('last_penthouse_party', 'penthouse_party_cd', 86400)}",
            f"**🏝️ Cayo Launch** — {_status('last_cayo_heist', 'cayo_heist_cooldown', 172800)}",
            f"**🚗 Car Theft** — {_status('last_car_theft', 'car_theft_cooldown', 28800)}",
            f"**📦 Export Car** — {_status('last_export_car', 'export_car_cooldown', 43200)}",
            f"**💊 Badonkadonk** — {_status('last_badonkadonk', 'badonkadonk_cooldown', 43200)}",
            f"**📞 Call Dax** — {_status('last_call_dax', 'call_dax_cooldown', 28800)}",
            f"**🐀 Labrat** — {_status('last_labrat', 'labrat_cooldown', 86400)}",
            f"**☢️ Doomsday Prep** — {_status('last_doomsday_prep', 'doomsday_prep_cooldown', 43200)}",
        ]

        # Slots
        window = settings.get("slots_cooldown_window", 86400)
        max_uses = settings.get("slots_max_uses", 3)
        window_start = float(u.get("slots_window_start", 0))
        uses = int(u.get("slots_uses", 0))
        if now - window_start >= window:
            uses = 0
        if uses >= max_uses:
            rem = int(window - (now - window_start))
            lines.append(f"**🎰 Slots** — ⏳ {_fmt_time(rem)} ({uses}/{max_uses} used)")
        else:
            lines.append(f"**🎰 Slots** — ✅ Available ({uses}/{max_uses} used)")

        available = [ln for ln in lines if "✅ Available" in ln]
        on_cd = [ln for ln in lines if "⏳" in ln]

        embed = discord.Embed(
            title="⏳ Your Cooldown List",
            description=(
                f"**Available now ({len(available)}):**\n"
                + ("\n".join(available) if available else "_None_")
                + f"\n\n**On cooldown ({len(on_cd)}):**\n"
                + ("\n".join(on_cd) if on_cd else "_None_")
            ),
            color=COLOR_INFO,
        )
        embed.set_footer(text="GTA Economy · Private · Cooldown List")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Row 1 — Blue shops ──
    @discord.ui.button(label="🏎️ Benny's Workshop", style=discord.ButtonStyle.primary, custom_id="eco_bennys", row=1)
    async def btn_bennys(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "bennys")

    @discord.ui.button(label="✈️ Elitas Travel", style=discord.ButtonStyle.primary, custom_id="eco_elitas", row=1)
    async def btn_elitas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "elitas")

    @discord.ui.button(label="🚗 Car Theft Job", style=discord.ButtonStyle.secondary, custom_id="eco_car_theft_job", row=1)
    async def btn_car_theft_job(self, interaction: discord.Interaction, button: discord.ui.Button):
        u = self.cog.data.get_user(interaction.user.id)
        if u.get("inventory", {}).get("biz_warehouse", 0) < 1:
            embed = discord.Embed(
                title="🏭 Warehouse Required",
                description=(
                    "You need a **Warehouse** to access the Car Theft Job.\n\n"
                    "Buy it at **Dynasty8 Executive** (permanent & unique).\n"
                    "It can store up to **30** stolen vehicles."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        view = CarTheftJobView(self.cog, interaction.user.id)
        embed = view.build_embed(u)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🌀 FreakShop", style=discord.ButtonStyle.secondary, custom_id="eco_freakshop", row=1)
    async def btn_freakshop(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = FreakShopView(self.cog, interaction.user.id)
        embed = view.build_embed()
        files = view.build_files()
        kwargs = {"embed": embed, "view": view, "ephemeral": True}
        if files:
            kwargs["file"] = files[0]
        await interaction.response.send_message(**kwargs)

    @discord.ui.button(label="🦄 Vanilla Unicorn", style=discord.ButtonStyle.secondary, custom_id="eco_vanilla_unicorn", row=1)
    async def btn_vanilla_unicorn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🦄 Vanilla Unicorn",
            description=(
                "The most famous strip club in Los Santos.\n\n"
                "**Coming soon.**\n"
                "Private dances, VIP rooms and special services will open here later.\n"
                "Stay tuned, Freshmeat."
            ),
            color=COLOR_CONSTRUCTION,
        )
        embed.set_footer(text="GTA Economy · Vanilla Unicorn · Coming Soon")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="☢️ Doomsday Heist", style=discord.ButtonStyle.secondary, custom_id="eco_doomsday", row=2)
    async def btn_doomsday(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = DoomsdayMainView(self.cog, interaction.user.id)
        embed = view.build_embed(self.cog.data.get_user(interaction.user.id))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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
        files = view.build_files()
        kwargs = {"embed": embed, "view": view, "ephemeral": True}
        if files:
            kwargs["file"] = files[0]
        await interaction.response.send_message(**kwargs)

    @discord.ui.button(label="🏠 Dynasty8", style=discord.ButtonStyle.secondary, custom_id="eco_dynasty8", row=3)
    async def btn_dynasty8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_ephemeral_result(interaction, "dynasty8")

    @discord.ui.button(label="🏢 Dynasty8 Executive", style=discord.ButtonStyle.secondary, custom_id="eco_dynasty8_exec", row=3)
    async def btn_dynasty8_exec(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        files = view.build_files()
        kwargs = {"embed": embed, "view": view, "ephemeral": True}
        if files:
            kwargs["file"] = files[0]
        await interaction.response.send_message(**kwargs)

    @discord.ui.button(label="🏰 The Mansion", style=discord.ButtonStyle.primary, custom_id="eco_mansion", row=4)
    async def btn_mansion(self, interaction: discord.Interaction, button: discord.ui.Button):
        u = self.cog.data.get_user(interaction.user.id)
        if not _has_mansion(u):
            embed = discord.Embed(
                title="🏰 The Mansion Required",
                description=(
                    "You need **The Mansion** to access The Kortz Center Heist.\n\n"
                    "Buy it at **Dynasty8** (permanent & unique property)."
                ),
                color=COLOR_FAIL,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        view = KortzMainView(self.cog, interaction.user.id)
        embed = view.build_embed(u)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── Row 2/4 — Missions + utility ──
    @discord.ui.button(label="💼 CEO SecuroServ", style=discord.ButtonStyle.secondary, custom_id="eco_ceo", row=2)
    async def btn_ceo(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.data.get_settings()
        u = self.cog.data.get_user(interaction.user.id)
        now = _now_ts()
        last = float(u.get("last_ceo", 0))
        cd = settings.get("ceo_cooldown", 21600)
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
                "Cooldown: **6 hours** after each attempt."
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
        cd = settings.get("motoclub_cooldown", 21600)
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
                "Cooldown: **6 hours** after each attempt."
            ),
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="MotoClub · Ephemeral · Only you can see this")
        view = MotoClubStartView(self.cog, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="❓ Help", style=discord.ButtonStyle.secondary, custom_id="eco_help", row=4)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❓ GTA Economy — Help",
            description=(
                f"**Currency:** {CURRENCY_EMOJI} {CURRENCY}\n\n"
                "**Core (green):** Daily (18h, private) · Work (6h, private) · Pay · Maze Bank\n\n"
                "**Shops:** Benny's · Elitas · Warstock · DockTease · Dynasty8 · Dynasty8 Executive\n\n"
                "**Lifestyle:** Casino Resort (Slots: 3/24h) · Music Locker (Enter 4h · Event 10h · presence +300) · Master Penthouse\n\n"
                "**Missions (6h):** CEO SecuroServ · MotoClub\n"
                "**Car Theft Job** (requires Warehouse): Car Theft 8h · Export 12h · max 30 vehicles\n"
                "**FreakShop** (Dax): Badonkadonk 12h · Call Dax 8h · Labrat 24h\n"
                "**Heists:** Cayo Perico · Kortz Center · Doomsday (free prep 12h, partner required, memory game)\n"
                "**Utility:** Cooldown List · Inventory · Garage · Ranking · Vanilla Unicorn (soon)\n\n"
                "**Utility:** Inventory · Garage (by class) · Ranking\n\n"
                "Daily, Work, cooldowns and shops are always private (ephemeral)."
            ),
            color=COLOR_INFO,
        )
        embed.set_footer(text="GTA Economy")
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
        embed.set_footer(text="GTA Economy")
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

    # ── Row 0 — Money management ──
    @discord.ui.button(label="➕ Add Money", style=discord.ButtonStyle.success, custom_id="adm_add_money", row=0)
    async def add_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminMoneyModal(self.cog, "add"))

    @discord.ui.button(label="➖ Remove Money", style=discord.ButtonStyle.danger, custom_id="adm_rem_money", row=0)
    async def rem_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminMoneyModal(self.cog, "remove"))

    @discord.ui.button(label="✏️ Set Money", style=discord.ButtonStyle.primary, custom_id="adm_set_money", row=0)
    async def set_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminMoneyModal(self.cog, "set"))

    @discord.ui.button(label="🔍 View User", style=discord.ButtonStyle.secondary, custom_id="adm_view_user", row=0)
    async def view_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminViewUserModal(self.cog))

    # ── Row 1 — Bulk + user reset ──
    @discord.ui.button(label="🌐 All +", style=discord.ButtonStyle.success, custom_id="adm_all_add", row=1)
    async def all_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminAllModal(self.cog, "add"))

    @discord.ui.button(label="🌐 All −", style=discord.ButtonStyle.danger, custom_id="adm_all_rem", row=1)
    async def all_rem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminAllModal(self.cog, "remove"))

    @discord.ui.button(label="🔄 Reset User", style=discord.ButtonStyle.danger, custom_id="adm_reset_user", row=1)
    async def reset_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminResetUserModal(self.cog))

    @discord.ui.button(label="🎁 Give Item", style=discord.ButtonStyle.success, custom_id="adm_give_item", row=1)
    async def give_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminGiveItemModal(self.cog))

    # ── Row 2 — Dangerous + settings ──
    @discord.ui.button(label="💥 Reset Server", style=discord.ButtonStyle.danger, custom_id="adm_reset_server", row=2)
    async def reset_server(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminResetServerModal(self.cog))

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

    @discord.ui.button(label="💼 Set Work", style=discord.ButtonStyle.secondary, custom_id="adm_set_work", row=2)
    async def set_work(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminWorkModal(self.cog))

    # ── Row 3 — Cooldowns + backup ──
    @discord.ui.button(label="⏳ Set Cooldowns", style=discord.ButtonStyle.secondary, custom_id="adm_set_cd", row=3)
    async def set_cooldowns(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminCooldownModal(self.cog))

    @discord.ui.button(label="🗑️ Remove Item", style=discord.ButtonStyle.danger, custom_id="adm_rem_item", row=3)
    async def remove_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminRemoveItemModal(self.cog))

    @discord.ui.button(label="🔄 Reset All Cooldowns", style=discord.ButtonStyle.danger, custom_id="adm_reset_all_cd", row=4)
    async def reset_all_cooldowns(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Clear all cooldown timestamps for every member."""
        await interaction.response.defer(ephemeral=True)
        users = self.cog.data.get_all_users()
        cooldown_keys = (
            "last_daily",
            "last_work",
            "last_balance",
            "last_motoclub",
            "last_ceo",
            "last_lucky_wheel",
            "last_music_event",
            "last_music_entry",
            "last_cayo_heist",
            "slots_uses",
            "slots_window_start",
            "last_penthouse_party",
            "last_car_theft",
            "last_export_car",
            "last_badonkadonk",
            "last_call_dax",
            "last_labrat",
            "last_doomsday_prep",
        )
        count = 0
        for uid, data in users.items():
            changed = False
            for key in cooldown_keys:
                if data.get(key, 0):
                    data[key] = 0
                    changed = True
            if changed:
                self.cog.data.save_user(int(uid), data)
                count += 1
        await interaction.followup.send(
            f"✅ Cooldowns reset for **{count}** member(s).\n"
            "Daily · Work · Balance · MotoClub · CEO · Lucky Wheel · Music Entry/Event · "
            "Cayo Heist · slots · Penthouse Party · Car Theft · Export Car · "
            "Badonkadonk · Call Dax · Labrat are available again.",
            ephemeral=True,
        )

    @discord.ui.button(label="🚗 Clear Vehicles", style=discord.ButtonStyle.danger, custom_id="adm_clear_veh", row=1)
    async def clear_vehicles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminClearVehiclesModal(self.cog))

    @discord.ui.button(label="🏠 Clear Permanents", style=discord.ButtonStyle.danger, custom_id="adm_clear_perm", row=2)
    async def clear_permanents(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminClearPermanentsModal(self.cog))

    @discord.ui.button(label="📈 Set Service Bonus", style=discord.ButtonStyle.primary, custom_id="adm_service_bonus", row=3)
    async def service_bonus(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminServiceBonusModal(self.cog))

    @discord.ui.button(label="📊 All Balances", style=discord.ButtonStyle.secondary, custom_id="adm_all_balances", row=4)
    async def all_balances(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        users = self.cog.data.get_all_users()
        ranked = sorted(
            users.items(),
            key=lambda x: int(x[1].get("wallet", 0)) + int(x[1].get("bank", 0)),
            reverse=True,
        )
        lines = ["user_id,wallet,bank,total"]
        desc_lines = []
        for i, (uid, d) in enumerate(ranked[:50]):
            w = int(d.get("wallet", 0))
            b = int(d.get("bank", 0))
            total = w + b
            lines.append(f"{uid},{w},{b},{total}")
            member = interaction.guild.get_member(int(uid)) if interaction.guild else None
            name = member.display_name if member else f"User {uid}"
            desc_lines.append(f"`{i+1}.` **{name}** — W {_fmt(w)} · B {_fmt(b)} · Σ {_fmt(total)}")
        content = "\n".join(lines)
        file = discord.File(
            fp=__import__("io").BytesIO(content.encode("utf-8")),
            filename=f"balances_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        )
        embed = discord.Embed(
            title="📊 All Member Balances (Top 50)",
            description="\n".join(desc_lines) if desc_lines else "No users yet.",
            color=COLOR_ADMIN,
        )
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    @discord.ui.button(label="👑 Richest Member", style=discord.ButtonStyle.primary, custom_id="adm_richest", row=4)
    async def richest(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        users = self.cog.data.get_all_users()
        if not users:
            return await interaction.followup.send("No users yet.", ephemeral=True)
        ranked = sorted(
            users.items(),
            key=lambda x: int(x[1].get("wallet", 0)) + int(x[1].get("bank", 0)),
            reverse=True,
        )
        uid, d = ranked[0]
        w = int(d.get("wallet", 0))
        b = int(d.get("bank", 0))
        total = w + b
        member = interaction.guild.get_member(int(uid)) if interaction.guild else None
        name = member.display_name if member else f"User {uid}"
        mention = member.mention if member else f"`{uid}`"
        embed = discord.Embed(
            title="👑 THE RICHEST IN LOS SANTOS",
            description=(
                f"💰💰💰 **WE HAVE A WINNER** 💰💰💰\n\n"
                f"🏆 {mention}\n"
                f"**{name}**\n\n"
                f"💵 Wallet: **{_fmt(w)}** {CURRENCY}\n"
                f"🏦 Bank: **{_fmt(b)}** {CURRENCY}\n"
                f"✨ **Total Assets: {_fmt(total)} {CURRENCY}** ✨\n\n"
                f"🔥🔥🔥 Respect the empire 🔥🔥🔥"
            ),
            color=COLOR_MAIN,
        )
        if member:
            embed.set_image(url=member.display_avatar.url)
        embed.set_footer(text="Maze Bank · Official Ranking · Top 1")
        await post_to_market(self.cog.bot, interaction.user, embed)
        await interaction.followup.send("✅ Richest member posted in the Market channel.", ephemeral=True)

    @discord.ui.button(label="💹 Bank Yield Deposit", style=discord.ButtonStyle.success, custom_id="adm_bank_yield", row=3)
    async def bank_yield(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminBankYieldModal(self.cog))

    @discord.ui.button(label="🚚 Spawn Export Event", style=discord.ButtonStyle.primary, custom_id="adm_export_event", row=4)
    async def export_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        panels = self.cog.data.get_panels()
        panels["export_claimed"] = False
        self.cog.data.save_panels(panels)
        embed = discord.Embed(
            title="🚚 Vehicle Export Sighted",
            description=(
                "**An export vehicle was spotted, and the owner left it in a nearby parking lot.**\n\n"
                "First agent to claim it can attempt the delivery.\n"
                "Success is not guaranteed — watch for griefers."
            ),
            color=COLOR_ORANGE,
        )
        embed.set_image(url=IMG["vehicle_exports"])
        embed.set_footer(text="GTA Economy · Vehicle Export · First claim only")
        view = ExportClaimView(self.cog)
        ch = self.cog.bot.get_channel(MARKET_CHANNEL_ID)
        if ch is None:
            try:
                ch = await self.cog.bot.fetch_channel(MARKET_CHANNEL_ID)
            except Exception:
                return await interaction.followup.send("Could not reach Market channel.", ephemeral=True)
        await ch.send(embed=embed, view=view)
        await interaction.followup.send("✅ Export event posted in the Market channel.", ephemeral=True)

    @discord.ui.button(label="💵 Set Export Reward", style=discord.ButtonStyle.secondary, custom_id="adm_export_reward", row=0)
    async def export_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminExportRewardModal(self.cog))

    @discord.ui.button(label="💰 Heist Prizes", style=discord.ButtonStyle.secondary, custom_id="adm_heist_prizes", row=4)
    async def heist_prizes(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AdminHeistPrizeSelectView(self.cog)
        embed = discord.Embed(
            title="💰 Adjust Heist Final Values",
            description=(
                "Select which heist prize to edit:\n\n"
                "🏝️ **Cayo Perico** — min/max prize range\n"
                "🖼️ **Kortz Center** — min/max prize range\n"
                "☢️ **Doomsday** — total prize pool\n"
                "🎰 **Casino Heist** — min/max prize range (reserved)"
            ),
            color=COLOR_ADMIN,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📈 Stock Exchange", style=discord.ButtonStyle.primary, custom_id="adm_stock_exchange", row=3)
    async def stock_exchange(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        s = self.cog.data.get_settings()

        def mid(a, b):
            return (int(a) + int(b)) // 2

        lines = [
            f"**📅 Daily** (base + streak): ~{_fmt(s.get('daily_amount', 300))} – {_fmt(s.get('daily_amount', 300) + s.get('max_streak_bonus', 600))}",
            f"**💼 Work**: {_fmt(s.get('work_min', 80))} – {_fmt(s.get('work_max', 220))} (avg ~{_fmt(mid(s.get('work_min', 80), s.get('work_max', 220)))})",
            f"**🏍️ MotoClub**: {_fmt(s.get('motoclub_reward_min', 320))} – {_fmt(s.get('motoclub_reward_max', 850))} (avg ~{_fmt(mid(s.get('motoclub_reward_min', 320), s.get('motoclub_reward_max', 850)))})",
            f"**💼 CEO Fast**: {_fmt(s.get('ceo_fast_reward_min', 450))} – {_fmt(s.get('ceo_fast_reward_max', 1200))}",
            f"**💼 CEO Safe**: {_fmt(s.get('ceo_safe_reward_min', 200))} – {_fmt(s.get('ceo_safe_reward_max', 480))}",
            f"**💼 CEO Premium**: {_fmt(s.get('ceo_premium_reward_min', 800))} – {_fmt(s.get('ceo_premium_reward_max', 1800))} (cost {_fmt(s.get('ceo_premium_cost', 200))})",
            f"**🏝️ Cayo Heist**: {_fmt(s.get('cayo_heist_prize_min', 8000))} – {_fmt(s.get('cayo_heist_prize_max', 15000))} (avg ~{_fmt(mid(s.get('cayo_heist_prize_min', 8000), s.get('cayo_heist_prize_max', 15000)))})",
            f"**🖼️ Kortz Heist**: {_fmt(s.get('kortz_heist_prize_min', 10000))} – {_fmt(s.get('kortz_heist_prize_max', 18000))} (avg ~{_fmt(mid(s.get('kortz_heist_prize_min', 10000), s.get('kortz_heist_prize_max', 18000)))})",
            f"**☢️ Doomsday Heist**: {_fmt(s.get('doomsday_total_prize', 5000))} total pool (70/30 split)",
            f"**🎰 Casino Heist** (setting): {_fmt(s.get('casino_heist_prize_min', 6000))} – {_fmt(s.get('casino_heist_prize_max', 12000))}",
            f"**💊 Badonkadonk**: {_fmt(s.get('badonkadonk_reward', 500))}",
            f"**📞 Call Dax** (success): {_fmt(s.get('call_dax_success_reward', 1000))} · fail −{_fmt(s.get('call_dax_fail_penalty', 500))}",
            f"**🚗 Car Theft fee**: {_fmt(s.get('car_theft_cost', 1000))} · Export = car value",
            f"**🚚 Export Event**: {_fmt(s.get('export_reward_min', 400))} – {_fmt(s.get('export_reward_max', 900))}",
            f"**🎵 Music Entry**: +{_fmt(s.get('music_entry_reward', 300))} (fee {_fmt(s.get('music_entry_fee', 50))})",
            f"**🎧 Music Event**: {_fmt(s.get('music_event_reward_min', 120))} – {_fmt(s.get('music_event_reward_max', 280))}",
            f"**🎉 Penthouse Party**: ~{_fmt(s.get('penthouse_party_reward', 450))}",
            f"**📈 Service Bonus** (extra on services): {_fmt(s.get('service_bonus', 0))}",
        ]
        embed = discord.Embed(
            title="📈 Stock Exchange — Economy Payout Rates",
            description=(
                "Average / base values currently paid by each system function.\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_ADMIN,
        )
        embed.set_footer(text="Bank Admin · Stock Exchange · Live settings")
        await interaction.followup.send(embed=embed, ephemeral=True)


class ExportClaimView(discord.ui.View):
    """Public one-shot claim for the admin-spawned vehicle export event."""

    def __init__(self, cog: "Economy"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="🚗 Claim Export",
        style=discord.ButtonStyle.success,
        custom_id="eco_export_claim",
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        panels = self.cog.data.get_panels()
        if panels.get("export_claimed"):
            return await interaction.response.send_message(
                "This export was already claimed by another agent.",
                ephemeral=True,
            )
        panels["export_claimed"] = True
        self.cog.data.save_panels(panels)

        settings = self.cog.data.get_settings()
        success = random.random() < 0.50
        u = self.cog.data.get_user(interaction.user.id)
        if success:
            # Prefer storing a random stolen car in Warehouse if player owns one and has space
            max_veh = settings.get("warehouse_max_vehicles", 30)
            has_wh = _has_warehouse(u)
            space = _count_stolen_vehicles(u) < max_veh
            if has_wh and space and CAR_THEFT_VEHICLES:
                car = random.choice(CAR_THEFT_VEHICLES)
                inv = u.get("inventory", {})
                inv[car["id"]] = inv.get(car["id"], 0) + 1
                u["inventory"] = inv
                self.cog.data.save_user(interaction.user.id, u)
                result = discord.Embed(
                    title="✅ Export Delivered — Vehicle Secured",
                    description=(
                        f"{interaction.user.mention} claimed the vehicle.\n\n"
                        f"**Congratulations, you successfully secured a "
                        f"{car.get('emoji', '🚗')} {car['name']}!**\n"
                        f"It has been stored in your **Warehouse**.\n"
                        f"Estimated value: **{_fmt(car['price'])}** {CURRENCY}"
                    ),
                    color=COLOR_SUCCESS,
                )
            else:
                rmin = settings.get("export_reward_min", 400)
                rmax = settings.get("export_reward_max", 900)
                reward = random.randint(rmin, rmax)
                self.cog.data.add_money(interaction.user.id, reward, "vehicle_export")
                extra = ""
                if not has_wh:
                    extra = "\n*(No Warehouse owned — cash reward instead of vehicle storage.)*"
                elif not space:
                    extra = "\n*(Warehouse full — cash reward instead.)*"
                result = discord.Embed(
                    title="✅ Export Delivered",
                    description=(
                        f"{interaction.user.mention} claimed the vehicle.\n\n"
                        f"**Congratulations, you successfully delivered the vehicle.**\n"
                        f"Reward: **{_fmt(reward)}** {CURRENCY}{extra}"
                    ),
                    color=COLOR_SUCCESS,
                )
            gif_key = "mission_passed"
        else:
            result = discord.Embed(
                title="💥 Export Failed",
                description=(
                    f"{interaction.user.mention} claimed the vehicle.\n\n"
                    "**Mission failed; a griefer got you with the Oppressor Mk II.**"
                ),
                color=COLOR_FAIL,
            )
            gif_key = "lose_game"
        result.set_footer(text="GTA Economy · Car Theft Job / Export Event")
        await interaction.response.edit_message(view=None)
        await post_to_market(self.cog.bot, interaction.user, result, gif_key=gif_key)


class AdminExportRewardModal(discord.ui.Modal, title="Set Export Reward Range"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.min_amt = discord.ui.TextInput(label="Min reward", required=True, placeholder="400")
        self.max_amt = discord.ui.TextInput(label="Max reward", required=True, placeholder="900")
        self.add_item(self.min_amt)
        self.add_item(self.max_amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            vmin = int(self.min_amt.value.replace(".", "").replace(",", ""))
            vmax = int(self.max_amt.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Invalid values.", ephemeral=True)
        if vmin > vmax or vmin < 0:
            return await interaction.response.send_message("Min must be ≤ max and ≥ 0.", ephemeral=True)
        s = self.cog.data.get_settings()
        s["export_reward_min"] = vmin
        s["export_reward_max"] = vmax
        self.cog.data.save_settings(s)
        await interaction.response.send_message(
            f"✅ Export reward range: **{_fmt(vmin)}** – **{_fmt(vmax)}** {CURRENCY}.",
            ephemeral=True,
        )


class AdminHeistPrizeSelectView(discord.ui.View):
    def __init__(self, cog: "Economy"):
        super().__init__(timeout=60)
        self.cog = cog
        options = [
            discord.SelectOption(label="🏝️ Cayo Perico", value="cayo", description="Min/max heist prize"),
            discord.SelectOption(label="🖼️ Kortz Center", value="kortz", description="Min/max heist prize"),
            discord.SelectOption(label="☢️ Doomsday", value="doomsday", description="Total prize pool"),
            discord.SelectOption(label="🎰 Casino Heist", value="casino", description="Min/max prize (reserved)"),
        ]
        select = discord.ui.Select(placeholder="Choose heist…", options=options)
        select.callback = self._pick
        self.add_item(select)

    async def _pick(self, interaction: discord.Interaction):
        heist = interaction.data["values"][0]
        await interaction.response.send_modal(AdminHeistPrizeModal(self.cog, heist))


class AdminHeistPrizeModal(discord.ui.Modal):
    """Set final prize values for Cayo / Kortz / Doomsday / Casino Heist."""

    HEIST_CONFIG = {
        "cayo": {
            "title": "Set Cayo Perico Prize Range",
            "min_key": "cayo_heist_prize_min",
            "max_key": "cayo_heist_prize_max",
            "single": False,
        },
        "kortz": {
            "title": "Set Kortz Center Prize Range",
            "min_key": "kortz_heist_prize_min",
            "max_key": "kortz_heist_prize_max",
            "single": False,
        },
        "doomsday": {
            "title": "Set Doomsday Total Prize Pool",
            "min_key": "doomsday_total_prize",
            "max_key": None,
            "single": True,
        },
        "casino": {
            "title": "Set Casino Heist Prize Range",
            "min_key": "casino_heist_prize_min",
            "max_key": "casino_heist_prize_max",
            "single": False,
        },
    }

    def __init__(self, cog: "Economy", heist: str):
        cfg = self.HEIST_CONFIG.get(heist, self.HEIST_CONFIG["cayo"])
        super().__init__(title=cfg["title"][:45])
        self.cog = cog
        self.heist = heist
        self.cfg = cfg
        if cfg["single"]:
            self.amount = discord.ui.TextInput(
                label="Total prize pool",
                required=True,
                placeholder="5000",
            )
            self.add_item(self.amount)
        else:
            self.min_amt = discord.ui.TextInput(label="Min prize", required=True, placeholder="8000")
            self.max_amt = discord.ui.TextInput(label="Max prize", required=True, placeholder="15000")
            self.add_item(self.min_amt)
            self.add_item(self.max_amt)

    async def on_submit(self, interaction: discord.Interaction):
        s = self.cog.data.get_settings()
        try:
            if self.cfg["single"]:
                val = int(self.amount.value.replace(".", "").replace(",", ""))
                if val < 0:
                    return await interaction.response.send_message("Value must be ≥ 0.", ephemeral=True)
                s[self.cfg["min_key"]] = val
                self.cog.data.save_settings(s)
                await interaction.response.send_message(
                    f"✅ Doomsday total prize pool set to **{_fmt(val)}** {CURRENCY}.",
                    ephemeral=True,
                )
            else:
                vmin = int(self.min_amt.value.replace(".", "").replace(",", ""))
                vmax = int(self.max_amt.value.replace(".", "").replace(",", ""))
                if vmin > vmax or vmin < 0:
                    return await interaction.response.send_message("Min must be ≤ max and ≥ 0.", ephemeral=True)
                s[self.cfg["min_key"]] = vmin
                s[self.cfg["max_key"]] = vmax
                self.cog.data.save_settings(s)
                name = self.heist.title()
                await interaction.response.send_message(
                    f"✅ {name} prize range: **{_fmt(vmin)}** – **{_fmt(vmax)}** {CURRENCY}.",
                    ephemeral=True,
                )
        except ValueError:
            await interaction.response.send_message("Invalid number.", ephemeral=True)


class AdminClearVehiclesModal(discord.ui.Modal, title="Clear All Vehicles"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.uid = discord.ui.TextInput(label="User ID (or ALL)", required=True, placeholder="123456 or ALL")
        self.add_item(self.uid)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.uid.value.strip().upper()
        vehicle_types = {"car", "motorcycle", "aircraft", "boat", "military", "stolen_car"}
        vehicle_dealers = {"southern", "legendary", "lost_mc", "podium"}
        all_items = self.cog.data.get_all_items()

        def _strip_vehicles(u: Dict) -> int:
            inv = u.get("inventory", {})
            removed = 0
            for iid in list(inv.keys()):
                item = all_items.get(iid, {})
                if item.get("type") in vehicle_types or item.get("dealer") in vehicle_dealers:
                    removed += inv.pop(iid, 0)
            u["inventory"] = inv
            return removed

        if raw == "ALL":
            users = self.cog.data.get_all_users()
            total = 0
            for uid, data in users.items():
                total += _strip_vehicles(data)
                self.cog.data.save_user(int(uid), data)
            await interaction.response.send_message(f"✅ Removed vehicles from all users (total items: {total}).", ephemeral=True)
        else:
            try:
                uid = int(raw)
            except ValueError:
                return await interaction.response.send_message("Invalid ID.", ephemeral=True)
            u = self.cog.data.get_user(uid)
            removed = _strip_vehicles(u)
            self.cog.data.save_user(uid, u)
            await interaction.response.send_message(f"✅ Removed **{removed}** vehicle(s) from user `{uid}`.", ephemeral=True)


class AdminClearPermanentsModal(discord.ui.Modal, title="Clear Permanent Items"):
    PERMANENT_IDS = (
        "casino_penthouse", "mil_submarine", "prop_house_mansion",
        "biz_warehouse", "biz_hangar", "biz_bunker",
        "ach_cayo_heist", "ach_kortz_heist", "music_vip",
    )

    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.uid = discord.ui.TextInput(label="User ID (or ALL)", required=True, placeholder="123456 or ALL")
        self.add_item(self.uid)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.uid.value.strip().upper()

        def _strip(u: Dict) -> int:
            inv = u.get("inventory", {})
            removed = 0
            for iid in self.PERMANENT_IDS:
                if iid in inv:
                    removed += inv.pop(iid, 0)
            if u.get("music_vip"):
                u["music_vip"] = False
                removed += 1
            if u.get("casino_membership"):
                u["casino_membership"] = None
                removed += 1
            u["inventory"] = inv
            return removed

        if raw == "ALL":
            users = self.cog.data.get_all_users()
            total = 0
            for uid, data in users.items():
                total += _strip(data)
                self.cog.data.save_user(int(uid), data)
            await interaction.response.send_message(f"✅ Cleared permanent items from all users (total: {total}).", ephemeral=True)
        else:
            try:
                uid = int(raw)
            except ValueError:
                return await interaction.response.send_message("Invalid ID.", ephemeral=True)
            u = self.cog.data.get_user(uid)
            removed = _strip(u)
            self.cog.data.save_user(uid, u)
            await interaction.response.send_message(f"✅ Cleared **{removed}** permanent item(s) from user `{uid}`.", ephemeral=True)


class AdminServiceBonusModal(discord.ui.Modal, title="Set Service Bonus"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.amt = discord.ui.TextInput(
            label="Bonus amount (added to Daily/Work/Missions/etc.)",
            required=True,
            placeholder="0 to disable, e.g. 50",
        )
        self.add_item(self.amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            v = int(self.amt.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Invalid number.", ephemeral=True)
        if v < 0:
            return await interaction.response.send_message("Bonus must be ≥ 0.", ephemeral=True)
        s = self.cog.data.get_settings()
        s["service_bonus"] = v
        self.cog.data.save_settings(s)
        await interaction.response.send_message(
            f"✅ Service bonus set to **{_fmt(v)}** {CURRENCY}.\n"
            "Applied to: Daily · Work · MotoClub · CEO · Cayo · Kortz · Music · Lucky Wheel.",
            ephemeral=True,
        )


class AdminBankYieldModal(discord.ui.Modal, title="Maze Bank Investment Yield"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.target = discord.ui.TextInput(
            label="User ID or ALL",
            placeholder="123456789 or ALL",
            required=True,
        )
        self.amt = discord.ui.TextInput(
            label="Amount to credit to bank deposit",
            placeholder="5000",
            required=True,
        )
        self.pct = discord.ui.TextInput(
            label="Yield % to display (cosmetic)",
            placeholder="e.g. 4.5",
            required=True,
            default="3.5",
        )
        self.add_item(self.target)
        self.add_item(self.amt)
        self.add_item(self.pct)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amt.value.replace(".", "").replace(",", ""))
            yield_pct = float(self.pct.value.replace(",", "."))
        except ValueError:
            return await interaction.response.send_message("Invalid amount or yield %.", ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message("Amount must be positive.", ephemeral=True)

        raw = self.target.value.strip().upper()
        await interaction.response.defer(ephemeral=True)

        if raw == "ALL":
            users = self.cog.data.get_all_users()
            count = 0
            for uid in list(users.keys()):
                self.cog.data.add_bank(int(uid), amount)
                count += 1
            public = discord.Embed(
                title="💹 Maze Bank — Investment Yield",
                description=(
                    f"All account holders received a **{yield_pct:g}%** quarterly investment return.\n\n"
                    f"**Yield credited per account:** {_fmt(amount)} {CURRENCY}\n"
                    f"**Accounts updated:** {count}\n\n"
                    "Your funds are working hard in Los Santos markets."
                ),
                color=COLOR_SUCCESS,
            )
            public.set_footer(text="Maze Bank · Official Investment Notice")
            await post_to_market(self.cog.bot, interaction.user, public)
            await interaction.followup.send(f"✅ Credited **{_fmt(amount)}** bank deposit to **{count}** members.", ephemeral=True)
        else:
            try:
                uid = int(raw)
            except ValueError:
                return await interaction.followup.send("Invalid User ID.", ephemeral=True)
            self.cog.data.add_bank(uid, amount)
            member = interaction.guild.get_member(uid) if interaction.guild else None
            if member is None:
                try:
                    member = await self.cog.bot.fetch_user(uid)
                except Exception:
                    member = None
            mention = member.mention if member and hasattr(member, "mention") else f"`{uid}`"
            name = member.display_name if member and hasattr(member, "display_name") else str(uid)
            public = discord.Embed(
                title="💹 Maze Bank — Investment Yield",
                description=(
                    f"{mention} received a **{yield_pct:g}%** return on their Maze Bank portfolio.\n\n"
                    f"**Yield credited:** {_fmt(amount)} {CURRENCY}\n"
                    f"**Account:** {name}\n\n"
                    "Smart investments pay off in Los Santos."
                ),
                color=COLOR_SUCCESS,
            )
            public.set_footer(text="Maze Bank · Official Investment Notice")
            await post_to_market(self.cog.bot, interaction.user, public)
            await interaction.followup.send(
                f"✅ Credited **{_fmt(amount)}** bank deposit to user `{uid}` (displayed as {yield_pct:g}% yield).",
                ephemeral=True,
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


class AdminResetServerModal(discord.ui.Modal, title="💥 Reset Server Economy"):
    """Requires password to confirm full economy wipe."""

    RESET_PASSWORD = "xoxolated"

    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.password = discord.ui.TextInput(
            label="Password",
            placeholder="Enter reset password",
            required=True,
            style=discord.TextStyle.short,
        )
        self.add_item(self.password)

    async def on_submit(self, interaction: discord.Interaction):
        if self.password.value.strip() != self.RESET_PASSWORD:
            return await interaction.response.send_message(
                "❌ Incorrect password. Server reset cancelled.", ephemeral=True
            )
        self.cog.data.reset_all()
        await interaction.response.send_message(
            "💥 **Server economy fully reset.** All balances wiped.", ephemeral=True
        )


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


class AdminWorkModal(discord.ui.Modal, title="Set Work Rewards"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.min_amt = discord.ui.TextInput(label="Work min reward", required=True, placeholder="80")
        self.max_amt = discord.ui.TextInput(label="Work max reward", required=True, placeholder="220")
        self.add_item(self.min_amt)
        self.add_item(self.max_amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            vmin = int(self.min_amt.value.replace(".", "").replace(",", ""))
            vmax = int(self.max_amt.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Invalid values.", ephemeral=True)
        if vmin > vmax or vmin < 0:
            return await interaction.response.send_message("Min must be ≤ max and ≥ 0.", ephemeral=True)
        s = self.cog.data.get_settings()
        s["work_min"] = vmin
        s["work_max"] = vmax
        self.cog.data.save_settings(s)
        await interaction.response.send_message(
            f"✅ Work range set to **{_fmt(vmin)}** – **{_fmt(vmax)}** {CURRENCY}.", ephemeral=True
        )


class AdminCooldownModal(discord.ui.Modal, title="Set Cooldowns (seconds)"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.daily_cd = discord.ui.TextInput(label="Daily cooldown (seconds)", required=True, placeholder="64800 = 18h")
        self.work_cd = discord.ui.TextInput(label="Work cooldown (seconds)", required=True, placeholder="21600 = 6h")
        self.add_item(self.daily_cd)
        self.add_item(self.work_cd)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            d = int(self.daily_cd.value)
            w = int(self.work_cd.value)
        except ValueError:
            return await interaction.response.send_message("Invalid values.", ephemeral=True)
        if d < 0 or w < 0:
            return await interaction.response.send_message("Cooldowns must be ≥ 0.", ephemeral=True)
        s = self.cog.data.get_settings()
        s["daily_cooldown"] = d
        s["work_cooldown"] = w
        self.cog.data.save_settings(s)
        await interaction.response.send_message(
            f"✅ Daily CD = **{_fmt_time(d)}** · Work CD = **{_fmt_time(w)}**.", ephemeral=True
        )


class AdminViewUserModal(discord.ui.Modal, title="View User"):
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
        u = self.cog.data.get_user(uid)
        inv = u.get("inventory", {})
        inv_lines = []
        all_items = self.cog.data.get_all_items()
        for iid, qty in list(inv.items())[:40]:
            item = all_items.get(iid, {})
            name = item.get("name", iid)
            emoji = item.get("emoji", "•")
            inv_lines.append(f"{emoji} {name} ×{qty}")
        wallet = int(u.get("wallet", 0))
        bank = int(u.get("bank", 0))
        embed = discord.Embed(
            title=f"🔍 User {uid}",
            description=(
                f"**Wallet:** {_fmt(wallet)} {CURRENCY}\n"
                f"**Bank Deposit:** {_fmt(bank)} {CURRENCY}\n"
                f"**Total Assets:** {_fmt(wallet + bank)} {CURRENCY}\n"
                f"**Streak:** {u.get('streak', 0)}\n"
                f"**Total earned:** {_fmt(u.get('total_earned', 0))}\n"
                f"**Total spent:** {_fmt(u.get('total_spent', 0))}\n"
                f"**Casino membership:** {u.get('casino_membership') or 'None'}\n"
                f"**Music VIP:** {'Yes' if u.get('music_vip') else 'No'}\n\n"
                f"**Inventory ({len(inv)} items):**\n"
                + ("\n".join(inv_lines) if inv_lines else "Empty")
            ),
            color=COLOR_ADMIN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AdminGiveItemModal(discord.ui.Modal, title="Give Item"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.uid = discord.ui.TextInput(label="User ID", required=True)
        self.item_id = discord.ui.TextInput(label="Item ID (e.g. car_sultan)", required=True)
        self.qty = discord.ui.TextInput(label="Quantity", required=True, default="1")
        self.add_item(self.uid)
        self.add_item(self.item_id)
        self.add_item(self.qty)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.uid.value.strip())
            quantity = int(self.qty.value.strip())
        except ValueError:
            return await interaction.response.send_message("Invalid ID or quantity.", ephemeral=True)
        if quantity <= 0:
            return await interaction.response.send_message("Quantity must be positive.", ephemeral=True)
        iid = self.item_id.value.strip()
        all_items = self.cog.data.get_all_items()
        if iid not in all_items:
            return await interaction.response.send_message(
                f"Unknown item id `{iid}`. Check catalogs.", ephemeral=True
            )
        u = self.cog.data.get_user(uid)
        inv = u.get("inventory", {})
        inv[iid] = inv.get(iid, 0) + quantity
        u["inventory"] = inv
        self.cog.data.save_user(uid, u)
        name = all_items[iid].get("name", iid)
        await interaction.response.send_message(
            f"✅ Gave **{name}** ×{quantity} to user `{uid}`.", ephemeral=True
        )


class AdminRemoveItemModal(discord.ui.Modal, title="Remove Item"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.uid = discord.ui.TextInput(label="User ID", required=True)
        self.item_id = discord.ui.TextInput(label="Item ID (e.g. car_sultan)", required=True)
        self.qty = discord.ui.TextInput(label="Quantity (or 0 to remove all)", required=True, default="1")
        self.add_item(self.uid)
        self.add_item(self.item_id)
        self.add_item(self.qty)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.uid.value.strip())
            quantity = int(self.qty.value.strip())
        except ValueError:
            return await interaction.response.send_message("Invalid ID or quantity.", ephemeral=True)
        iid = self.item_id.value.strip()
        u = self.cog.data.get_user(uid)
        inv = u.get("inventory", {})
        current = inv.get(iid, 0)
        if current <= 0:
            return await interaction.response.send_message(
                f"User `{uid}` does not own `{iid}`.", ephemeral=True
            )
        if quantity <= 0 or quantity >= current:
            inv.pop(iid, None)
            removed = current
        else:
            inv[iid] = current - quantity
            removed = quantity
        u["inventory"] = inv
        self.cog.data.save_user(uid, u)
        all_items = self.cog.data.get_all_items()
        name = all_items.get(iid, {}).get("name", iid)
        await interaction.response.send_message(
            f"✅ Removed **{name}** ×{removed} from user `{uid}`.", ephemeral=True
        )


class Economy(commands.Cog):
    """GTA Economy system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = EconomyData()
        self.bot.add_view(MemberPanelView(self))
        self.bot.add_view(AdminPanelView(self))
        self.bot.add_view(ExportClaimView(self))

    async def cog_load(self):
        logger.info("GTA Economy loaded")

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
            embed.set_image(url=interaction.user.display_avatar.url)
            embed.set_footer(text="GTA Economy")
            return embed, None

        if action == "maze_statement":
            wallet = int(u.get("wallet", 0))
            bank = int(u.get("bank", 0))
            total = wallet + bank
            embed = discord.Embed(
                title="🏦 Maze Bank Statement",
                description=(
                    f"**Account holder:** {interaction.user.display_name}\n\n"
                    f"**Wallet:** {_fmt(wallet)} {CURRENCY}\n"
                    f"**Bank Deposit:** {_fmt(bank)} {CURRENCY}\n"
                    f"**Total Assets:** {_fmt(total)} {CURRENCY}"
                ),
                color=COLOR_MAIN,
            )
            embed.set_image(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Maze Bank · Official Statement")
            return embed, None

        if action == "daily":
            now = _now_ts()
            last = float(u.get("last_daily", 0))
            cd = settings.get("daily_cooldown", 64800)
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
            embed.set_footer(text="GTA Economy")
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
            embed.set_image(url=IMG["bennys"])
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
            embed.set_image(url=IMG["warstock"])
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
            embed.set_image(url=IMG["elitas"])
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
            embed.set_image(url=IMG["docktease"])
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
            embed.set_image(url=IMG["dynasty8"])
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, DYNASTY8_ITEMS, "Dynasty8")
            return embed, view

        if action == "foreclosures":
            lines = [
                f"{it.get('emoji','🏢')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY}"
                for it in FORECLOSURES_ITEMS
            ]
            embed = discord.Embed(
                title="🏢 Dynasty8 Executive",
                description=(
                    "Nightclubs, complexes, warehouses, bunkers,\n"
                    "MC clubhouses, agencies and underworld properties.\n\n"
                    + "\n".join(lines)
                ),
                color=COLOR_ADMIN,
            )
            embed.set_image(url=IMG["dynasty8_exec"])
            embed.set_footer(text="Select below to purchase · Private view only")
            view = ShopBuyView(self, uid, FORECLOSURES_ITEMS, "Dynasty8 Executive")
            return embed, view

        if action == "garage":
            inv = u.get("inventory", {})
            all_items = self.data.get_all_items()
            categories = {
                "🚗 Cars (Sports / Muscle / Sedan)": [],
                "🏍️ Motorcycles": [],
                "✈️ Aircraft": [],
                "🚤 Boats": [],
                "🪖 Military": [],
                "🏎️ Special / Podium": [],
            }
            for iid, qty in inv.items():
                item = all_items.get(iid, {})
                itype = item.get("type", "")
                dealer = item.get("dealer", "")
                name = item.get("name", iid)
                emoji = item.get("emoji", "🚗")
                line = f"{emoji} **{name}** ×{qty}"
                if itype == "motorcycle" or dealer == "lost_mc":
                    categories["🏍️ Motorcycles"].append(line)
                elif itype == "aircraft":
                    categories["✈️ Aircraft"].append(line)
                elif itype == "boat":
                    categories["🚤 Boats"].append(line)
                elif itype == "military":
                    categories["🪖 Military"].append(line)
                elif dealer == "podium" or itype == "car":
                    if dealer == "podium":
                        categories["🏎️ Special / Podium"].append(line)
                    else:
                        categories["🚗 Cars (Sports / Muscle / Sedan)"].append(line)
            total = sum(len(v) for v in categories.values())
            if total == 0:
                embed = discord.Embed(
                    title="🚗 Empty Garage",
                    description=(
                        "You don't own any vehicles yet.\n"
                        "Buy cars & bikes at **Benny's**, planes at **Elitas**, "
                        "boats at **DockTease**, military at **Warstock**!"
                    ),
                    color=COLOR_INFO,
                )
                return embed, None
            embed = discord.Embed(
                title=f"🚗 {interaction.user.display_name}'s Garage",
                description=f"Total vehicles: **{total}**",
                color=COLOR_MAIN,
            )
            for cat_name, lines in categories.items():
                if lines:
                    embed.add_field(
                        name=cat_name,
                        value="\n".join(lines),
                        inline=False,
                    )
            embed.set_image(url=IMG["garage"])
            embed.set_footer(text="GTA Economy · Personal Garage")
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

    eco = app_commands.Group(name="economy", description="GTA Economy (staff + utility)")

    @eco.command(name="panel", description="[LOCKED] Post member panel in Maze Bank")
    async def panel_cmd(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user, self.bot):
            return await interaction.response.send_message("🔒 Staff only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ch = self.bot.get_channel(BANK_CHANNEL_ID) or await self.bot.fetch_channel(BANK_CHANNEL_ID)
        embed = discord.Embed(
            title=f"{CURRENCY_EMOJI} GTA Economy",
            description=(
                f"**Welcome to the GTA Economy system!**\n\n"
                f"Currency: **{CURRENCY}**\n\n"
                "Use the buttons below to:\n"
                "• Daily & Work (always private) · Pay · Maze Bank\n"
                "• Shops: Benny's, Elitas, Warstock, DockTease, Dynasty8, Dynasty8 Executive\n"
                "• Lifestyle: Casino Resort, Music Locker & Master Penthouse\n"
                "• Missions: CEO SecuroServ & MotoClub\n"
                "• Car Theft Job (requires Warehouse from Dynasty8 Executive)\n"
                "• FreakShop (Dax & the Fooliganz)\n"
                "• Heists: Cayo Perico · Kortz Center · Doomsday Heist\n"
                "• Inventory, Garage (by class), Ranking & Help\n\n"
                "🔒 Daily, Work, cooldowns and shops are always private.\n"
                "Inventory / Garage / Ranking: choose private or public view."
            ),
            color=COLOR_MAIN,
        )
        embed.set_footer(text="GTA Economy · Maze Bank · Click the buttons")
        view = MemberPanelView(self)
        panel_gif = _apply_gif_image(embed, "main_panel")
        send_kwargs: Dict[str, Any] = {"embed": embed, "view": view}
        if panel_gif is not None:
            send_kwargs["file"] = panel_gif
        msg = await ch.send(**send_kwargs)
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
            title="🛡️ BANK ADMIN — GTA Economy Control",
            description=(
                "**Staff-only panel.**\n\n"
                "• Money: Add / Remove / Set / View User (full inventory + bank)\n"
                "• Bulk: All + / All − / Reset User / Give Item\n"
                "• Settings: Daily · Work · Cooldowns · Service Bonus · Export Reward\n"
                "• **Heist prizes:** Cayo · Kortz · Doomsday · Casino Heist\n"
                "• **Stock Exchange** — live average payouts of every system\n"
                "• Items: Give / Remove · Clear Vehicles · Clear Permanents\n"
                "• **All Balances** · **Richest Member** · **Bank Yield Deposit**\n"
                "• **Spawn Export Event** (Market mini-game, first claim only)\n"
                "• Backup Wallets · Post Ranking · Reset All Cooldowns\n"
                "• **Reset Server** requires password `xoxolated`\n"
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
