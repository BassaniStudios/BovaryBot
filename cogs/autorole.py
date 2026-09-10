"""Auto-role (button roles) module — supports multiple roles."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json, default_autorole

logger = logging.getLogger("bovary_bot.autorole")
CONFIG_FILE = "autorole.json"


class AutoRoleView(discord.ui.View):
    """Dynamic buttons for each configured role (up to 20 / 4 rows)."""

    def __init__(self, bot: commands.Bot, roles_data: list):
        super().__init__(timeout=None)
        self.bot = bot
        for i, entry in enumerate(roles_data[:20]):
            role_id = entry.get("role_id")
            label = entry.get("label", "Role")[:80]
            emoji = entry.get("emoji")
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"autorole:{role_id}",
                emoji=emoji if emoji else None,
                row=i // 5,
            )
            btn.callback = self._make_callback(role_id, label)
            self.add_item(btn)

    def _make_callback(self, role_id: int, label: str):
        async def callback(interaction: discord.Interaction):
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message("Guild only.", ephemeral=True)
                return
            role = interaction.guild.get_role(int(role_id))
            if not role:
                await interaction.response.send_message("Role not found.", ephemeral=True)
                return

            me = interaction.guild.me
            if me and role >= me.top_role:
                await interaction.response.send_message(
                    "I cannot manage this role (hierarchy). Move my role higher.",
                    ephemeral=True,
                )
                return

            member = interaction.user
            try:
                if role in member.roles:
                    await member.remove_roles(role, reason="Auto-role toggle")
                    await interaction.response.send_message(
                        f"Removed **{role.name}**.", ephemeral=True
                    )
                else:
                    await member.add_roles(role, reason="Auto-role toggle")
                    await interaction.response.send_message(
                        f"Added **{role.name}**.", ephemeral=True
                    )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "I lack permission to manage this role.", ephemeral=True
                )
        return callback


class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_json(CONFIG_FILE, default_autorole())
        if self.config.get("roles"):
            try:
                self.bot.add_view(AutoRoleView(bot, self.config["roles"]))
            except Exception:
                logger.exception("Failed to register AutoRoleView")

    def _save(self):
        save_json(CONFIG_FILE, self.config)

    def _reregister_view(self):
        roles = self.config.get("roles") or []
        if roles:
            try:
                self.bot.add_view(AutoRoleView(self.bot, roles))
            except Exception:
                logger.exception("Failed to re-register AutoRoleView")

    @app_commands.command(name="autorole_panel", description="Post the auto-role panel in this channel")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_panel(self, interaction: discord.Interaction):
        roles = self.config.get("roles") or []
        if not roles:
            await interaction.response.send_message(
                "No roles configured. Use `/autorole_add` (multiple times) or the web panel first.",
                ephemeral=True,
            )
            return

        color = self.config.get("color", 0xB450FF)
        embed = discord.Embed(
            title=self.config.get("title", "Choose your roles"),
            description=self.config.get("description", ""),
            color=color,
        )
        embed.set_footer(text="Bova's Bot · Auto-Role · Click to toggle")
        view = AutoRoleView(self.bot, roles)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        self.config["message_id"] = msg.id
        self.config["channel_id"] = interaction.channel_id
        self._save()
        self._reregister_view()

    @app_commands.command(name="autorole_add", description="Add a role to the auto-role panel (supports many)")
    @app_commands.describe(role="Role to add", label="Button label", emoji="Optional emoji")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_add(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        label: Optional[str] = None,
        emoji: Optional[str] = None,
    ):
        entry = {
            "role_id": role.id,
            "label": label or role.name,
            "emoji": emoji,
        }
        roles = self.config.setdefault("roles", [])
        roles = [r for r in roles if r.get("role_id") != role.id]
        roles.append(entry)
        self.config["roles"] = roles
        self._save()
        self._reregister_view()
        await interaction.response.send_message(
            f"Added **{role.name}** ({len(roles)} role(s) total). "
            f"Re-post the panel with `/autorole_panel` to update buttons.",
            ephemeral=True,
        )

    @app_commands.command(name="autorole_remove", description="Remove a role from the auto-role panel")
    @app_commands.describe(role="Role to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_remove(self, interaction: discord.Interaction, role: discord.Role):
        before = len(self.config.get("roles", []))
        self.config["roles"] = [r for r in self.config.get("roles", []) if r.get("role_id") != role.id]
        self._save()
        self._reregister_view()
        removed = before - len(self.config["roles"])
        await interaction.response.send_message(
            f"Removed {removed} entry/entries. Re-post panel with `/autorole_panel`.",
            ephemeral=True,
        )

    @app_commands.command(name="autorole_list", description="List roles configured for auto-role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_list(self, interaction: discord.Interaction):
        roles = self.config.get("roles") or []
        if not roles:
            await interaction.response.send_message("No roles configured.", ephemeral=True)
            return
        lines = [
            f"{r.get('emoji') or '•'} **{r.get('label')}** — `<@&{r.get('role_id')}>`"
            for r in roles
        ]
        await interaction.response.send_message(
            f"**Auto-role entries ({len(roles)}):**\n" + "\n".join(lines),
            ephemeral=True,
        )

    @app_commands.command(name="autorole_config", description="Set auto-role embed title and description")
    @app_commands.describe(title="Embed title", description="Embed description")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_config(
        self,
        interaction: discord.Interaction,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if title:
            self.config["title"] = title
        if description:
            self.config["description"] = description
        self._save()
        await interaction.response.send_message(
            f"**Title:** {self.config.get('title')}\n**Description:** {self.config.get('description')}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
