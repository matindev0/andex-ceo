# ============================================================
# cogs/projects.py  —  Aria Bot · Project Management
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from gemini_engine import engine

log = logging.getLogger("aria.projects")

# ── Helpers ───────────────────────────────────────────────────

def _private_overwrites(guild: discord.Guild, owner: discord.Member, bot_member: discord.Member) -> dict:
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        owner: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        bot_member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

async def _scrape_channel(channel: discord.TextChannel, limit: int = 400) -> str:
    """Collect full history, skipping bot code blocks to save context space."""
    lines: list[str] = []
    async for msg in channel.history(limit=limit, oldest_first=True):
        if msg.author.bot:
            for embed in msg.embeds:
                if embed.title and "Version" in embed.title:
                    lines.append(f"[Aria — Build Output: {embed.title} (skipped)]")
                    break
            continue
        if msg.content:
            lines.append(f"[{msg.author.display_name}]: {msg.content}")
    return "\n".join(lines) or "مێژووی گفتوگۆ نییە."

def _previous_build_summary(project_id: int) -> str:
    builds = db.list_builds(project_id)
    if not builds: return ""
    parts = [f"v{b['version']} ({b['status']})" for b in builds]
    return "نەهاتووەکانی پێشوو: " + ", ".join(parts)

# ── Persistent Views ──────────────────────────────────────────

class BuildVersionView(discord.ui.View):
    def __init__(self, project_id: int, version: int) -> None:
        super().__init__(timeout=None)
        self.project_id = project_id
        self.version    = version
        self.build_btn.custom_id = f"build_version|{project_id}|{version}"

    @discord.ui.button(label="🔨 Build New Version", style=discord.ButtonStyle.success)
    async def build_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            _, pid_str, ver_str = button.custom_id.split("|")
            project_id, version = int(pid_str), int(ver_str)
        except:
            project_id, version = self.project_id, self.version

        if not db.is_authorized(interaction.user.id, interaction.guild_id):
            return await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)

        project = db.get_project(project_id)
        button.disabled = True
        button.label = f"⏳ دروستکردن (v{version})..."
        await interaction.response.edit_message(view=self)

        status_msg = await interaction.channel.send("⚙️ Aria دەستی کرد بە نووسینی کۆدی نوێ...")
        channel_snapshot = await _scrape_channel(interaction.channel)
        
        try:
            full_output = await engine.generate_versioned_build(
                project_name=project["name"], version=version, channel_snapshot=channel_snapshot
            )
            build_id = db.create_build(project_id, interaction.user.id, version, channel_snapshot)
            
            # Split and send
            chunks = [full_output[i:i+1990] for i in range(0, len(full_output), 1990)]
            for chunk in chunks:
                await interaction.channel.send(f"```python\n{chunk}\n```")
            
            db.finish_build(build_id, full_output, "[]")
            await status_msg.edit(content=f"✅ Version {version} بە سەرکەوتوویی دروست کرا!")
        except Exception as e:
            await status_msg.edit(content=f"❌ هەڵە لە دروستکردن: {e}")

class InitialBuildView(discord.ui.View):
    def __init__(self, project_id: int) -> None:
        super().__init__(timeout=None)
        self.start_btn.custom_id = f"initial_build|{project_id}"

    @discord.ui.button(label="🚀 پرۆژە بنا — Build v1", style=discord.ButtonStyle.success)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # بڕوانە بۆ BuildVersionView v1
        pass

# ── Projects Cog ─────────────────────────────────────────────

class ProjectsCog(commands.Cog, name="Projects"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def _project_channel_listener(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild: return
        project = db.get_project_by_channel(message.channel.id)
        if not project: return

        if len(message.content) < 5: return
        
        async with message.channel.typing():
            ack = await engine.acknowledge_request(message.channel.id, message.content)
            view = BuildVersionView(project["id"], db.next_build_version(project["id"]))
            await message.channel.send(ack, view=view)

    @app_commands.command(name="new_project", description="پرۆژەیەکی نوێ دروست بکە")
    async def new_project(self, interaction: discord.Interaction, name: str, description: str = "") -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = await guild.create_category(f"📁 {name}")
        channel = await guild.create_text_channel(name.lower().replace(" ","-"), category=category)
        
        pid = db.create_project(guild.id, interaction.user.id, name, description, category.id, channel.id)
        await channel.send(f"🎯 پرۆژەی **{name}** دروست کرا! داواکارییەکانت لێرە بنووسە.", view=InitialBuildView(pid))
        await interaction.followup.send(f"✅ پرۆژە ئامادەیە: {channel.mention}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProjectsCog(bot))
