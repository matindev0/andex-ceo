# ============================================================
# cogs/admin.py  —  Aria Bot · Admin & Setup Commands
# ============================================================

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from gemini_engine import engine

def owner_only():
    """App-command check: only the configured owner may run this."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message(
                "⛔ تەنها خاوەنی سێرڤەر دەتوانێت ئەم فەرمانە بەکاربهێنێت.",
                ephemeral=True,
            )
            return False
        return True
    return app_commands.check(predicate)

class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /setup ────────────────────────────────────────────────
    @app_commands.command(
        name="setup",
        description="(Owner) سازکردنی Aria — چەناڵەکانی Command، Chat، Ideas، و Logs دیاری بکە",
    )
    @app_commands.describe(
        command_channel="چەناڵی Slash Commands",
        chat_channel   ="چەناڵی گفتوگۆی ڕاستەوخۆ بە AI",
        ideas_channel  ="چەناڵی ئایدیا و پرۆگرام",
        logs_channel   ="چەناڵی تۆمارکردنی چالاکییەکان",
    )
    @owner_only()
    async def setup(
        self,
        interaction: discord.Interaction,
        command_channel: discord.TextChannel,
        chat_channel   : discord.TextChannel,
        ideas_channel  : discord.TextChannel,
        logs_channel   : discord.TextChannel,
    ) -> None:
        gid = interaction.guild_id
        db.set_channel(gid, "command", command_channel.id)
        db.set_channel(gid, "chat",    chat_channel.id)
        db.set_channel(gid, "ideas",   ideas_channel.id)
        db.set_channel(gid, "logs",    logs_channel.id)

        # Ensure owner is authorized
        db.authorize_user(interaction.user.id, gid, level=99)

        embed = discord.Embed(
            title="✅ Aria سازکرایەوە",
            color=0x57F287,
            description=(
                f"**Commands:** {command_channel.mention}\n"
                f"**Chat:** {chat_channel.mention}\n"
                f"**Ideas:** {ideas_channel.mention}\n"
                f"**Logs:** {logs_channel.mention}"
            ),
        )
        embed.set_footer(text="Everything is under control AnDex")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.bot._log_to_discord("⚙️ Setup تەواو بوو")

    # ── /authorize ────────────────────────────────────────────
    @app_commands.command(
        name="authorize",
        description="(Owner) بەکارهێنەرێکی تر مۆڵەت بدە بۆ بەکارهێنانی Aria",
    )
    @app_commands.describe(user="بەکارهێنەری مۆڵەتدراو")
    @owner_only()
    async def authorize(
        self,
        interaction: discord.Interaction,
        user       : discord.Member,
    ) -> None:
        db.authorize_user(user.id, interaction.guild_id)
        await interaction.response.send_message(
            f"✅ **{user.display_name}** مۆڵەتی پێدرا — ئێستا دەتوانێت بە Aria قسە بکات.",
            ephemeral=True,
        )

    # ── /status ───────────────────────────────────────────────
    @app_commands.command(
        name="status",
        description="دۆخی سیستەم و Database نیشان بدە",
    )
    @owner_only()
    async def status(self, interaction: discord.Interaction) -> None:
        projects_active  = len(db.list_projects(interaction.guild_id, status="active"))
        projects_all     = len(db.list_projects(interaction.guild_id))
        channels         = db.get_all_channels(interaction.guild_id)

        embed = discord.Embed(
            title="📊 دۆخی Aria",
            color=0x5865F2,
        )
        embed.add_field(name="🤖 Bot", value=f"`{config.BOT_NAME}` — ئۆنلاینە", inline=True)
        embed.add_field(name="📁 پرۆژە", value=f"کۆی گشتی: **{projects_all}** | چالاک: **{projects_active}**", inline=True)
        
        ch_text = "\n".join(f"`{role}`: <#{ch_id}>" for role, ch_id in channels.items())
        embed.add_field(
            name="📡 چەناڵەکان",
            value=ch_text if ch_text else "هێشتا سازنەکراوە",
            inline=False,
        )
        embed.set_footer(text="Everything is under control AnDex")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /clear_history ────────────────────────────────────────
    @app_commands.command(
        name="clear_history",
        description="(Owner) مێژووی گفتوگۆی چەناڵێک پاک بکەرەوە",
    )
    @app_commands.describe(channel="ئەو چەناڵەی مێژووەکەی پاک دەکرێتەوە")
    @owner_only()
    async def clear_history(
        self,
        interaction: discord.Interaction,
        channel    : discord.TextChannel,
    ) -> None:
        db.clear_history(channel.id)
        await interaction.response.send_message(
            f"🗑️ مێژووی {channel.mention} پاک کرایەوە.", ephemeral=True
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
