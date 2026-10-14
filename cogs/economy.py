"""
Bovary Economy — sistema completo de economia do Bova's Bot.
Moeda: Bovas coins
Painel principal (membros): canal Maze Bank
Respostas dos membros: canal Bovary Market
Painel admin [LOCKED]: canal Bank Admin
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
BANK_CHANNEL_ID = 1559720971437350933       # Maze Bank — painel membros
MARKET_CHANNEL_ID = 1559721230591066182     # Bovary Market — respostas
ADMIN_CHANNEL_ID = 1426755523797057536      # Bank Admin — painel staff

CURRENCY = "Bovas coins"
CURRENCY_EMOJI = "🪙"
COLOR_MAIN = discord.Color.from_rgb(255, 193, 7)      # gold
COLOR_SUCCESS = discord.Color.from_rgb(46, 204, 113)
COLOR_FAIL = discord.Color.from_rgb(231, 76, 60)
COLOR_INFO = discord.Color.from_rgb(52, 152, 219)
COLOR_ADMIN = discord.Color.from_rgb(155, 89, 182)

# Default shop items (pets, carros, brasões + básicos)
DEFAULT_SHOP: List[Dict[str, Any]] = [
    {"id": "pet_gato", "name": "🐱 Gato de Estimação", "price": 500, "type": "pet", "desc": "Um gato fofo que te acompanha.", "emoji": "🐱"},
    {"id": "pet_cachorro", "name": "🐶 Cachorro Fiel", "price": 800, "type": "pet", "desc": "O melhor amigo do homem (e do Bova).", "emoji": "🐶"},
    {"id": "pet_dragao", "name": "🐉 Dragão Mini", "price": 5000, "type": "pet", "desc": "Um dragão de bolso lendário.", "emoji": "🐉"},
    {"id": "pet_fenrir", "name": "🐺 Fenrir Pup", "price": 3500, "type": "pet", "desc": "Filhote do lobo de Fenrir Yakuza.", "emoji": "🐺"},
    {"id": "car_civic", "name": "🚗 Honda Civic 2008", "price": 2500, "type": "car", "desc": "Clássico de rua.", "emoji": "🚗"},
    {"id": "car_supra", "name": "🏎️ Toyota Supra", "price": 12000, "type": "car", "desc": "Rápido demais pro radar.", "emoji": "🏎️"},
    {"id": "car_lambo", "name": "🚙 Lamborghini Aventador", "price": 50000, "type": "car", "desc": "Flex no Bovary Club.", "emoji": "🚙"},
    {"id": "car_fusca", "name": "🪲 Fusca Tunado", "price": 1500, "type": "car", "desc": "Não subestime o fusca.", "emoji": "🪲"},
    {"id": "brasao_ouro", "name": "⚜️ Brasão de Ouro", "price": 3000, "type": "brasao", "desc": "Símbolo de prestígio.", "emoji": "⚜️"},
    {"id": "brasao_yakuza", "name": "🩸 Brasão Yakuza", "price": 8000, "type": "brasao", "desc": "Respeito da família Fenrir.", "emoji": "🩸"},
    {"id": "brasao_bova", "name": "👑 Brasão Bova", "price": 15000, "type": "brasao", "desc": "O brasão oficial do clube.", "emoji": "👑"},
    {"id": "item_cafe", "name": "☕ Café do Bova", "price": 50, "type": "consumable", "desc": "Recupera a energia (cosmético).", "emoji": "☕"},
    {"id": "item_roleta", "name": "🎰 Ficha de Cassino", "price": 200, "type": "consumable", "desc": "Item colecionável.", "emoji": "🎰"},
]

DEFAULT_SETTINGS = {
    "daily_amount": 250,
    "daily_streak_bonus": 25,   # por dia de streak
    "max_streak_bonus": 500,
    "work_min": 40,
    "work_max": 180,
    "work_cooldown": 3600,      # 1h
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
# MINI-GAMES VIEWS
# ═══════════════════════════════════════════════════════════════════════════

class MinesView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int, bet: int, mines: int, grid_size: int = 5):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.mines = mines
        self.grid_size = grid_size
        self.revealed: set[int] = set()
        self.mine_positions = set(random.sample(range(grid_size * grid_size), mines))
        self.alive = True
        self.cashout_mult = 1.0
        self._build_buttons()

    def _mult_for(self, revealed_count: int) -> float:
        # Simple progressive multiplier
        safe = self.grid_size * self.grid_size - self.mines
        if revealed_count == 0:
            return 1.0
        base = 1.0 + (self.mines / max(1, safe)) * 0.85
        return round(base ** revealed_count, 2)

    def _build_buttons(self):
        self.clear_items()
        for i in range(self.grid_size * self.grid_size):
            row = i // self.grid_size
            if i in self.revealed:
                label = "💥" if i in self.mine_positions else "✅"
                style = discord.ButtonStyle.danger if i in self.mine_positions else discord.ButtonStyle.success
                disabled = True
            else:
                label = "⬛"
                style = discord.ButtonStyle.secondary
                disabled = not self.alive
            btn = discord.ui.Button(label=label, style=style, disabled=disabled, row=row, custom_id=f"mines_{i}")
            btn.callback = self._make_callback(i)
            self.add_item(btn)
        if self.alive and self.revealed:
            cash = discord.ui.Button(label=f"💰 Cash Out x{self.cashout_mult}", style=discord.ButtonStyle.primary, row=4, custom_id="mines_cash")
            cash.callback = self._cashout
            self.add_item(cash)

    def _make_callback(self, idx: int):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("Esse jogo não é seu!", ephemeral=True)
            if not self.alive or idx in self.revealed:
                return await interaction.response.defer()
            self.revealed.add(idx)
            if idx in self.mine_positions:
                self.alive = False
                self.cashout_mult = 0
                embed = discord.Embed(
                    title="💥 MINES — BOOM!",
                    description=f"Você pisou numa mina!\nPerdeu **{_fmt(self.bet)}** {CURRENCY}",
                    color=COLOR_FAIL,
                )
                embed.set_footer(text="Bovary Economy · Mines")
                self._build_buttons()
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return
            self.cashout_mult = self._mult_for(len(self.revealed))
            embed = discord.Embed(
                title="⛏️ MINES",
                description=(
                    f"Células seguras: **{len(self.revealed)}**\n"
                    f"Multiplicador atual: **x{self.cashout_mult}**\n"
                    f"Potencial: **{_fmt(int(self.bet * self.cashout_mult))}** {CURRENCY}\n\n"
                    f"Continue ou faça **Cash Out**!"
                ),
                color=COLOR_MAIN,
            )
            embed.set_footer(text="Bovary Economy · Mines")
            self._build_buttons()
            await interaction.response.edit_message(embed=embed, view=self)
        return cb

    async def _cashout(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Esse jogo não é seu!", ephemeral=True)
        if not self.alive:
            return await interaction.response.defer()
        win = int(self.bet * self.cashout_mult)
        self.cog.data.add_money(self.user_id, win, "mines_win")
        self.alive = False
        embed = discord.Embed(
            title="💰 MINES — CASH OUT!",
            description=f"Você saiu com **x{self.cashout_mult}**\nGanhou **{_fmt(win)}** {CURRENCY}!",
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Bovary Economy · Mines")
        self._build_buttons()
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


class HackView(discord.ui.View):
    SEQUENCE_LEN = 5
    EMOJIS = ["🔴", "🟢", "🔵", "🟡", "🟣"]

    def __init__(self, cog: "Economy", user_id: int, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.sequence = [random.choice(self.EMOJIS) for _ in range(self.SEQUENCE_LEN)]
        self.player: List[str] = []
        self.phase = "show"  # show → input → done
        for e in self.EMOJIS:
            btn = discord.ui.Button(label=e, style=discord.ButtonStyle.secondary, custom_id=f"hack_{e}")
            btn.callback = self._make_input(e)
            self.add_item(btn)

    def _make_input(self, emoji: str):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("Esse hack não é seu!", ephemeral=True)
            if self.phase != "input":
                return await interaction.response.send_message("Aguarde a sequência!", ephemeral=True)
            self.player.append(emoji)
            if len(self.player) < self.SEQUENCE_LEN:
                await interaction.response.defer()
                return
            # check
            self.phase = "done"
            if self.player == self.sequence:
                mult = round(random.uniform(1.6, 2.8), 2)
                win = int(self.bet * mult)
                self.cog.data.add_money(self.user_id, win, "hack_win")
                embed = discord.Embed(
                    title="💻 HACK — SUCESSO!",
                    description=f"Sistema invadido!\nMultiplicador **x{mult}**\nVocê ganhou **{_fmt(win)}** {CURRENCY}",
                    color=COLOR_SUCCESS,
                )
            else:
                embed = discord.Embed(
                    title="💻 HACK — FALHA",
                    description=f"Firewall ativado.\nVocê perdeu **{_fmt(self.bet)}** {CURRENCY}",
                    color=COLOR_FAIL,
                )
            embed.set_footer(text="Bovary Economy · Hack")
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        return cb


class CoinflipView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int, bet: int):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet

    @discord.ui.button(label="🪙 CARA", style=discord.ButtonStyle.primary, custom_id="cf_heads")
    async def heads(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "cara")

    @discord.ui.button(label="👑 COROA", style=discord.ButtonStyle.secondary, custom_id="cf_tails")
    async def tails(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "coroa")

    async def _play(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Essa aposta não é sua!", ephemeral=True)
        result = random.choice(["cara", "coroa"])
        for item in self.children:
            item.disabled = True
        if result == choice:
            win = self.bet * 2
            self.cog.data.add_money(self.user_id, win, "coinflip_win")
            embed = discord.Embed(
                title="🪙 COINFLIP — VITÓRIA!",
                description=f"Saiu **{result.upper()}**!\nVocê ganhou **{_fmt(win)}** {CURRENCY}",
                color=COLOR_SUCCESS,
            )
        else:
            embed = discord.Embed(
                title="🪙 COINFLIP — DERROTA",
                description=f"Saiu **{result.upper()}**.\nVocê perdeu **{_fmt(self.bet)}** {CURRENCY}",
                color=COLOR_FAIL,
            )
        embed.set_footer(text="Bovary Economy · Coinflip")
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ═══════════════════════════════════════════════════════════════════════════
# MEMBER PANEL VIEW (persistent)
# ═══════════════════════════════════════════════════════════════════════════

class MemberPanelView(discord.ui.View):
    def __init__(self, cog: "Economy"):
        super().__init__(timeout=None)
        self.cog = cog

    async def _route(self, interaction: discord.Interaction, action: str):
        """Defer ephemeral, post real result to Market."""
        await interaction.response.defer(ephemeral=True)
        # Build response in Market
        result_embed, result_view = await self.cog.handle_member_action(interaction, action)
        if result_embed is None:
            await interaction.followup.send("Ação cancelada ou erro.", ephemeral=True)
            return
        msg = await post_to_market(self.cog.bot, interaction.user, result_embed, result_view)
        if msg:
            await interaction.followup.send(
                f"✅ Resultado enviado em <#{MARKET_CHANNEL_ID}> — vá até o canal para ver!",
                ephemeral=True,
            )
        else:
            # fallback: show here
            await interaction.followup.send(embed=result_embed, view=result_view, ephemeral=True)

    @discord.ui.button(label="💰 Saldo", style=discord.ButtonStyle.primary, custom_id="eco_balance", row=0)
    async def btn_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._route(interaction, "balance")

    @discord.ui.button(label="📅 Daily", style=discord.ButtonStyle.success, custom_id="eco_daily", row=0)
    async def btn_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._route(interaction, "daily")

    @discord.ui.button(label="💸 Pagar", style=discord.ButtonStyle.secondary, custom_id="eco_pay", row=0)
    async def btn_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Pay needs modal
        await interaction.response.send_modal(PayModal(self.cog))

    @discord.ui.button(label="🛒 Shop", style=discord.ButtonStyle.primary, custom_id="eco_shop", row=1)
    async def btn_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._route(interaction, "shop")

    @discord.ui.button(label="💼 Trabalhar", style=discord.ButtonStyle.secondary, custom_id="eco_work", row=1)
    async def btn_work(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._route(interaction, "work")

    @discord.ui.button(label="🎒 Inventário", style=discord.ButtonStyle.secondary, custom_id="eco_inv", row=1)
    async def btn_inv(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._route(interaction, "inventory")

    @discord.ui.button(label="⛏️ Mines", style=discord.ButtonStyle.danger, custom_id="eco_mines", row=2)
    async def btn_mines(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BetModal(self.cog, "mines"))

    @discord.ui.button(label="💻 Hack", style=discord.ButtonStyle.danger, custom_id="eco_hack", row=2)
    async def btn_hack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BetModal(self.cog, "hack"))

    @discord.ui.button(label="🪙 Coinflip", style=discord.ButtonStyle.danger, custom_id="eco_coinflip", row=2)
    async def btn_cf(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BetModal(self.cog, "coinflip"))

    @discord.ui.button(label="🏆 Ranking", style=discord.ButtonStyle.primary, custom_id="eco_lb", row=3)
    async def btn_lb(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._route(interaction, "leaderboard")

    @discord.ui.button(label="❓ Help", style=discord.ButtonStyle.secondary, custom_id="eco_help", row=3)
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❓ Bovary Economy — Ajuda",
            description=(
                f"**Moeda:** {CURRENCY_EMOJI} {CURRENCY}\n\n"
                "**Botões do painel:**\n"
                "💰 **Saldo** — ver sua carteira\n"
                "📅 **Daily** — recompensa diária (+ streak)\n"
                "💸 **Pagar** — transferir para outro membro\n"
                "🛒 **Shop** — ver e comprar itens (pets, carros, brasões)\n"
                "💼 **Trabalhar** — ganhar coins (cooldown)\n"
                "🎒 **Inventário** — seus itens\n"
                "⛏️ **Mines** / 💻 **Hack** / 🪙 **Coinflip** — mini-games de aposta\n"
                "🏆 **Ranking** — top mais ricos\n\n"
                f"Todas as respostas aparecem em <#{MARKET_CHANNEL_ID}>."
            ),
            color=COLOR_INFO,
        )
        embed.set_footer(text="Bovary Economy")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PayModal(discord.ui.Modal, title="💸 Pagar membro"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.user_input = discord.ui.TextInput(label="ID ou @ do usuário", placeholder="123456789 ou mencione", required=True)
        self.amount_input = discord.ui.TextInput(label="Quantia", placeholder="100", required=True)
        self.add_item(self.user_input)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = self.user_input.value.strip().replace("<@", "").replace("!", "").replace(">", "")
        try:
            target_id = int(raw)
        except ValueError:
            return await interaction.followup.send("ID inválido.", ephemeral=True)
        try:
            amount = int(self.amount_input.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.followup.send("Quantia inválida.", ephemeral=True)
        if amount <= 0:
            return await interaction.followup.send("Quantia deve ser positiva.", ephemeral=True)
        if target_id == interaction.user.id:
            return await interaction.followup.send("Não pode pagar a si mesmo.", ephemeral=True)

        payer = self.cog.data.get_user(interaction.user.id)
        if payer["wallet"] < amount:
            return await interaction.followup.send(f"Saldo insuficiente. Você tem {_fmt(payer['wallet'])}.", ephemeral=True)

        self.cog.data.add_money(interaction.user.id, -amount, "pay")
        self.cog.data.add_money(target_id, amount, "pay_received")
        target = interaction.guild.get_member(target_id) or await self.cog.bot.fetch_user(target_id)
        name = target.display_name if hasattr(target, "display_name") else str(target_id)

        embed = discord.Embed(
            title="💸 Transferência realizada",
            description=f"{interaction.user.mention} enviou **{_fmt(amount)}** {CURRENCY} para **{name}**.",
            color=COLOR_SUCCESS,
        )
        embed.set_footer(text="Bovary Economy")
        await post_to_market(self.cog.bot, interaction.user, embed)
        await interaction.followup.send(f"✅ Enviado {_fmt(amount)} para {name}. Veja em <#{MARKET_CHANNEL_ID}>", ephemeral=True)


class BetModal(discord.ui.Modal, title="Apostar"):
    def __init__(self, cog: "Economy", game: str):
        super().__init__()
        self.cog = cog
        self.game = game
        self.amount_input = discord.ui.TextInput(label="Quantia da aposta", placeholder="100", required=True)
        self.add_item(self.amount_input)
        if game == "mines":
            self.mines_input = discord.ui.TextInput(label="Número de minas (1-10)", placeholder="3", required=True, default="3")
            self.add_item(self.mines_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = self.cog.data.get_settings()
        try:
            bet = int(self.amount_input.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.followup.send("Quantia inválida.", ephemeral=True)
        if bet < settings["min_bet"] or bet > settings["max_bet"]:
            return await interaction.followup.send(
                f"Aposta deve ser entre {_fmt(settings['min_bet'])} e {_fmt(settings['max_bet'])}.",
                ephemeral=True,
            )
        u = self.cog.data.get_user(interaction.user.id)
        if u["wallet"] < bet:
            return await interaction.followup.send(f"Saldo insuficiente ({_fmt(u['wallet'])}).", ephemeral=True)

        # debit
        self.cog.data.add_money(interaction.user.id, -bet, f"{self.game}_bet")

        if self.game == "mines":
            try:
                mines = int(self.mines_input.value)
                mines = max(1, min(10, mines))
            except Exception:
                mines = 3
            view = MinesView(self.cog, interaction.user.id, bet, mines)
            embed = discord.Embed(
                title="⛏️ MINES",
                description=f"Aposta: **{_fmt(bet)}** | Minas: **{mines}**\nClique nas células. Evite as minas!\nQuanto mais células, maior o multiplicador.",
                color=COLOR_MAIN,
            )
            embed.set_footer(text="Bovary Economy · Mines")
            await post_to_market(self.cog.bot, interaction.user, embed, view)
            await interaction.followup.send(f"⛏️ Mines iniciado em <#{MARKET_CHANNEL_ID}>", ephemeral=True)

        elif self.game == "hack":
            view = HackView(self.cog, interaction.user.id, bet)
            seq_str = " ".join(view.sequence)
            embed = discord.Embed(
                title="💻 HACK EM ANDAMENTO",
                description=(
                    f"Aposta: **{_fmt(bet)}**\n\n"
                    f"**Memorize a sequência:**\n# {seq_str}\n\n"
                    f"Você tem 8 segundos… depois clique na ordem certa!"
                ),
                color=COLOR_INFO,
            )
            embed.set_footer(text="Bovary Economy · Hack")
            msg = await post_to_market(self.cog.bot, interaction.user, embed, view)
            await interaction.followup.send(f"💻 Hack iniciado em <#{MARKET_CHANNEL_ID}>", ephemeral=True)
            await asyncio.sleep(8)
            if view.phase == "show":
                view.phase = "input"
                embed.description = (
                    f"Aposta: **{_fmt(bet)}**\n\n"
                    f"**Digite a sequência** clicando nos botões na ordem correta!"
                )
                if msg:
                    try:
                        await msg.edit(embed=embed, view=view)
                    except Exception:
                        pass

        elif self.game == "coinflip":
            view = CoinflipView(self.cog, interaction.user.id, bet)
            embed = discord.Embed(
                title="🪙 COINFLIP",
                description=f"Aposta: **{_fmt(bet)}**\nEscolha **Cara** ou **Coroa**!",
                color=COLOR_MAIN,
            )
            embed.set_footer(text="Bovary Economy · Coinflip")
            await post_to_market(self.cog.bot, interaction.user, embed, view)
            await interaction.followup.send(f"🪙 Coinflip em <#{MARKET_CHANNEL_ID}>", ephemeral=True)


class ShopBuyView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int, items: List[Dict]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        # limit to 25 options
        options = []
        for it in items[:25]:
            options.append(discord.SelectOption(
                label=f"{it.get('emoji', '')} {it['name']}"[:100],
                value=it["id"],
                description=f"{_fmt(it['price'])} {CURRENCY}"[:100],
            ))
        if options:
            select = discord.ui.Select(placeholder="Escolha um item para comprar…", options=options)
            select.callback = self._buy
            self.add_item(select)

    async def _buy(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Não é sua loja!", ephemeral=True)
        item_id = interaction.data["values"][0]
        shop = self.cog.data.get_shop()
        item = next((i for i in shop if i["id"] == item_id), None)
        if not item:
            return await interaction.response.send_message("Item não encontrado.", ephemeral=True)
        u = self.cog.data.get_user(self.user_id)
        if u["wallet"] < item["price"]:
            return await interaction.response.send_message(f"Saldo insuficiente. Precisa de {_fmt(item['price'])}.", ephemeral=True)
        self.cog.data.add_money(self.user_id, -item["price"], "shop_buy")
        inv = u.get("inventory", {})
        inv[item_id] = inv.get(item_id, 0) + 1
        u = self.cog.data.get_user(self.user_id)
        u["inventory"] = inv
        self.cog.data.save_user(self.user_id, u)
        embed = discord.Embed(
            title="🛒 Compra realizada!",
            description=f"Você comprou **{item.get('emoji', '')} {item['name']}** por **{_fmt(item['price'])}** {CURRENCY}.",
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


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
            await interaction.response.send_message("🔒 Acesso negado. Apenas staff.", ephemeral=True)
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
        await interaction.response.send_message("⚠️ Confirmar RESET de TODOS os saldos?", view=view, ephemeral=True)

    @discord.ui.button(label="⚙️ Settings", style=discord.ButtonStyle.secondary, custom_id="adm_settings", row=2)
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.cog.data.get_settings()
        embed = discord.Embed(title="⚙️ Settings atuais", color=COLOR_ADMIN)
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
        await interaction.followup.send("Backup de carteiras:", file=file, ephemeral=True)


class AdminMoneyModal(discord.ui.Modal, title="Gerenciar saldo"):
    def __init__(self, cog: "Economy", mode: str):
        super().__init__()
        self.cog = cog
        self.mode = mode
        self.uid = discord.ui.TextInput(label="User ID", required=True)
        self.amt = discord.ui.TextInput(label="Quantia", required=True)
        self.add_item(self.uid)
        self.add_item(self.amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.uid.value.strip())
            amount = int(self.amt.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Valores inválidos.", ephemeral=True)
        if self.mode == "add":
            bal = self.cog.data.add_money(uid, amount, "admin_add")
            msg = f"Adicionado {_fmt(amount)}. Novo saldo: {_fmt(bal)}"
        elif self.mode == "remove":
            bal = self.cog.data.add_money(uid, -amount, "admin_remove")
            msg = f"Removido {_fmt(amount)}. Novo saldo: {_fmt(bal)}"
        else:
            bal = self.cog.data.set_money(uid, amount)
            msg = f"Saldo definido para {_fmt(bal)}"
        await interaction.response.send_message(f"✅ {msg}", ephemeral=True)


class AdminAllModal(discord.ui.Modal, title="Todos os usuários"):
    def __init__(self, cog: "Economy", mode: str):
        super().__init__()
        self.cog = cog
        self.mode = mode
        self.amt = discord.ui.TextInput(label="Quantia", required=True)
        self.add_item(self.amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amt.value.replace(".", "").replace(",", ""))
        except ValueError:
            return await interaction.response.send_message("Inválido.", ephemeral=True)
        users = self.cog.data.get_all_users()
        delta = amount if self.mode == "add" else -amount
        for uid in list(users.keys()):
            self.cog.data.add_money(int(uid), delta, f"admin_all_{self.mode}")
        await interaction.response.send_message(f"✅ Aplicado em {len(users)} usuários.", ephemeral=True)


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
            return await interaction.response.send_message("ID inválido.", ephemeral=True)
        self.cog.data.reset_user(uid)
        await interaction.response.send_message(f"✅ User {uid} resetado.", ephemeral=True)


class ConfirmResetView(discord.ui.View):
    def __init__(self, cog: "Economy"):
        super().__init__(timeout=30)
        self.cog = cog

    @discord.ui.button(label="CONFIRMAR RESET SERVER", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.data.reset_all()
        await interaction.response.edit_message(content="💥 Server economy resetado.", view=None)


class AdminDailyModal(discord.ui.Modal, title="Set Daily Amount"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.amt = discord.ui.TextInput(label="Valor do daily base", required=True)
        self.add_item(self.amt)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            v = int(self.amt.value)
        except ValueError:
            return await interaction.response.send_message("Inválido.", ephemeral=True)
        s = self.cog.data.get_settings()
        s["daily_amount"] = v
        self.cog.data.save_settings(s)
        await interaction.response.send_message(f"✅ Daily base = {_fmt(v)}", ephemeral=True)


class AdminShopAddModal(discord.ui.Modal, title="Adicionar item ao Shop"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.iid = discord.ui.TextInput(label="ID único (ex: pet_novo)", required=True)
        self.name = discord.ui.TextInput(label="Nome", required=True)
        self.price = discord.ui.TextInput(label="Preço", required=True)
        self.typ = discord.ui.TextInput(label="Tipo (pet/car/brasao/consumable)", required=True, default="pet")
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
            return await interaction.response.send_message("Preço inválido.", ephemeral=True)
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
        await interaction.response.send_message(f"✅ Item `{self.iid.value}` adicionado.", ephemeral=True)


class AdminShopRemModal(discord.ui.Modal, title="Remover item do Shop"):
    def __init__(self, cog: "Economy"):
        super().__init__()
        self.cog = cog
        self.iid = discord.ui.TextInput(label="ID do item", required=True)
        self.add_item(self.iid)

    async def on_submit(self, interaction: discord.Interaction):
        shop = self.cog.data.get_shop()
        new = [i for i in shop if i["id"] != self.iid.value.strip()]
        if len(new) == len(shop):
            return await interaction.response.send_message("Item não encontrado.", ephemeral=True)
        self.cog.data.save_shop(new)
        await interaction.response.send_message(f"✅ Item removido.", ephemeral=True)


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
        self, interaction: discord.Interaction, action: str
    ) -> Tuple[Optional[discord.Embed], Optional[discord.ui.View]]:
        uid = interaction.user.id
        u = self.data.get_user(uid)
        settings = self.data.get_settings()

        if action == "balance":
            embed = discord.Embed(
                title=f"{CURRENCY_EMOJI} Sua Carteira",
                description=f"**Saldo:** {_fmt(u['wallet'])} {CURRENCY}",
                color=COLOR_MAIN,
            )
            embed.add_field(name="Streak Daily", value=str(u.get("streak", 0)), inline=True)
            embed.add_field(name="Total ganho", value=_fmt(u.get("total_earned", 0)), inline=True)
            embed.add_field(name="Total gasto", value=_fmt(u.get("total_spent", 0)), inline=True)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Bovary Economy")
            return embed, None

        if action == "daily":
            now = _now_ts()
            last = float(u.get("last_daily", 0))
            # reset window: 20h to allow some flexibility, but streak requires ~22h gap max
            if now - last < 20 * 3600:
                remaining = int(20 * 3600 - (now - last))
                h, m = remaining // 3600, (remaining % 3600) // 60
                embed = discord.Embed(
                    title="📅 Daily já resgatado",
                    description=f"Volte em **{h}h {m}m**.",
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
                title="📅 Daily Resgatado!",
                description=(
                    f"Você recebeu **{_fmt(total)}** {CURRENCY}\n"
                    f"(base {_fmt(base)} + streak x{streak} = +{_fmt(bonus)})\n\n"
                    f"🔥 Streak atual: **{streak}** dias"
                ),
                color=COLOR_SUCCESS,
            )
            embed.set_footer(text="Bovary Economy")
            return embed, None

        if action == "work":
            now = _now_ts()
            last = float(u.get("last_work", 0))
            cd = settings["work_cooldown"]
            if now - last < cd:
                rem = int(cd - (now - last))
                embed = discord.Embed(
                    title="💼 Em cooldown",
                    description=f"Trabalhe novamente em **{rem // 60}m {rem % 60}s**.",
                    color=COLOR_FAIL,
                )
                return embed, None
            pay = random.randint(settings["work_min"], settings["work_max"])
            jobs = [
                "Você entregou pedidos do Bovary Café e ganhou",
                "Você limpou o servidor Fenrir e recebeu",
                "Você organizou um meet e ganhou",
                "Você vendeu memes no chat e faturou",
                "Você ajudou o Nazar e ele te pagou",
                "Você fez design de brasão e recebeu",
            ]
            text = random.choice(jobs)
            u["last_work"] = now
            self.data.save_user(uid, u)
            self.data.add_money(uid, pay, "work")
            embed = discord.Embed(
                title="💼 Trabalho concluído",
                description=f"{text} **{_fmt(pay)}** {CURRENCY}!",
                color=COLOR_SUCCESS,
            )
            return embed, None

        if action == "shop":
            shop = self.data.get_shop()
            if not shop:
                embed = discord.Embed(title="🛒 Shop vazia", description="Nenhum item disponível.", color=COLOR_INFO)
                return embed, None
            lines = []
            for it in shop:
                lines.append(f"{it.get('emoji','🎁')} **{it['name']}** — {_fmt(it['price'])} {CURRENCY} (`{it['type']}`)")
            embed = discord.Embed(
                title="🛒 Bovary Shop",
                description="\n".join(lines[:30]),
                color=COLOR_MAIN,
            )
            embed.set_footer(text="Selecione abaixo para comprar")
            view = ShopBuyView(self, uid, shop)
            return embed, view

        if action == "inventory":
            inv = u.get("inventory", {})
            if not inv:
                embed = discord.Embed(title="🎒 Inventário vazio", description="Compre itens na Shop!", color=COLOR_INFO)
                return embed, None
            shop = {i["id"]: i for i in self.data.get_shop()}
            lines = []
            for iid, qty in inv.items():
                name = shop.get(iid, {}).get("name", iid)
                emoji = shop.get(iid, {}).get("emoji", "🎁")
                lines.append(f"{emoji} **{name}** ×{qty}")
            embed = discord.Embed(title="🎒 Seu Inventário", description="\n".join(lines), color=COLOR_INFO)
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
                title=f"🏆 Ranking {CURRENCY}",
                description="\n".join(lines) or "Ninguém ainda.",
                color=COLOR_MAIN,
            )
            return embed, None

        return None, None

    # ── Slash (admin + optional) ───────────────────────────────────────────

    eco = app_commands.Group(name="economy", description="Bovary Economy (staff + util)")

    @eco.command(name="panel", description="[LOCKED] Postar painel de membros no Maze Bank")
    async def panel_cmd(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user, self.bot):
            return await interaction.response.send_message("🔒 Apenas staff.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ch = self.bot.get_channel(BANK_CHANNEL_ID) or await self.bot.fetch_channel(BANK_CHANNEL_ID)
        embed = discord.Embed(
            title=f"{CURRENCY_EMOJI} MAZE BANK",
            description=(
                f"**Bem-vindo ao sistema Bovary Economy!**\n\n"
                f"Moeda: **{CURRENCY}**\n\n"
                "Use os botões abaixo para:\n"
                "• Ver saldo & daily\n"
                "• Transferir, trabalhar, shop\n"
                "• Jogar Mines · Hack · Coinflip\n\n"
                f"📡 **Todas as respostas vão para** <#{MARKET_CHANNEL_ID}>"
            ),
            color=COLOR_MAIN,
        )
        embed.set_footer(text="Bovary Economy · Maze Bank · Clique nos botões")
        view = MemberPanelView(self)
        msg = await ch.send(embed=embed, view=view)
        panels = self.data.get_panels()
        panels["member"] = {"channel_id": BANK_CHANNEL_ID, "message_id": msg.id}
        self.data.save_panels(panels)
        await interaction.followup.send(f"✅ Painel postado em <#{BANK_CHANNEL_ID}> (Maze Bank)", ephemeral=True)

    @eco.command(name="adminpanel", description="[LOCKED] Postar painel admin no Bank Admin")
    async def adminpanel_cmd(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user, self.bot):
            return await interaction.response.send_message("🔒 Apenas staff.", ephemeral=True)
        if interaction.channel_id != ADMIN_CHANNEL_ID:
            return await interaction.response.send_message(
                f"Este painel só pode ser postado em <#{ADMIN_CHANNEL_ID}>.", ephemeral=True
            )
        embed = discord.Embed(
            title="🛡️ BANK ADMIN — Controle da Economia",
            description=(
                "**Painel restrito a staff.**\n\n"
                "Gerencie saldos, shop, settings e backups."
            ),
            color=COLOR_ADMIN,
        )
        view = AdminPanelView(self)
        await interaction.response.send_message(embed=embed, view=view)

    @eco.command(name="balance", description="Ver seu saldo (atalho slash)")
    async def bal_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        u = self.data.get_user(target.id)
        embed = discord.Embed(
            title=f"{CURRENCY_EMOJI} Carteira de {target.display_name}",
            description=f"**{_fmt(u['wallet'])}** {CURRENCY}",
            color=COLOR_MAIN,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
