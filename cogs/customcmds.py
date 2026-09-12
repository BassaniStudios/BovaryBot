"""Custom commands / tags — staff can create simple text or embed responses."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import make_embed
from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.customcmds")
FILE = "customcmds.json"


class CustomCmds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: Dict[str, Any] = load_json(FILE, {"commands": {}})

    def _save(self):
        save_json(FILE, self.data)

    def _cmds(self) -> Dict[str, Dict]:
        return self.data.setdefault("commands", {})

    @app_commands.command(name="cmd_add", description="Create a custom command (tag)")
    @app_commands.describe(
        name="Command name (no spaces)",
        response="Text response (supports simple markdown)",
        embed="If true, send as embed",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def cmd_add(
        self,
        interaction: discord.Interaction,
        name: str,
        response: str,
        embed: bool = False,
    ):
        name = name.strip().lower().replace(" ", "_")[:32]
        if not name:
            await interaction.response.send_message("Invalid name.", ephemeral=True)
            return
        self._cmds()[name] = {
            "response": response[:2000],
            "embed": embed,
            "author_id": interaction.user.id,
        }
        self._save()
        await interaction.response.send_message(f"✅ Custom command `/{name}` saved. Use `/run {name}`.", ephemeral=True)

    @app_commands.command(name="cmd_remove", description="Remove a custom command")
    @app_commands.describe(name="Command name")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def cmd_remove(self, interaction: discord.Interaction, name: str):
        name = name.strip().lower()
        if name in self._cmds():
            del self._cmds()[name]
            self._save()
            await interaction.response.send_message(f"✅ Removed `{name}`.", ephemeral=True)
        else:
            await interaction.response.send_message("Not found.", ephemeral=True)

    @app_commands.command(name="cmd_list", description="List custom commands")
    async def cmd_list(self, interaction: discord.Interaction):
        cmds = self._cmds()
        if not cmds:
            await interaction.response.send_message("No custom commands.", ephemeral=True)
            return
        lines = [f"`{n}`" for n in sorted(cmds.keys())]
        await interaction.response.send_message("**Custom commands:** " + ", ".join(lines), ephemeral=True)

    @app_commands.command(name="run", description="Run a custom command / tag")
    @app_commands.describe(name="Command name")
    async def run_cmd(self, interaction: discord.Interaction, name: str):
        name = name.strip().lower()
        entry = self._cmds().get(name)
        if not entry:
            await interaction.response.send_message("Unknown command. Use `/cmd_list`.", ephemeral=True)
            return
        text = entry.get("response", "")
        if entry.get("embed"):
            embed = make_embed(title=name, description=text, color=discord.Color.from_rgb(180, 80, 255))
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(text)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCmds(bot))
