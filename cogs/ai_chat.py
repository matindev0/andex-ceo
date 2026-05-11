# ============================================================
# cogs/ai_chat.py  —  Aria Bot · AI Commands (Slash)
# ============================================================

from __future__ import annotations

import logging
from typing import Optional
import io

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from gemini_engine import engine

log = logging.getLogger("aria.ai_chat")

class AIChatCog(commands.Cog, name="AIChat"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /ask ─────────────────────────────────────────────────
    @app_commands.command(
        name="ask",
        description="پرسیارێک بکە لە Aria — بە کوردی یان ئینگلیزی",
    )
    @app_commands.describe(question="پرسیارەکەت")
    async def ask(
        self,
        interaction: discord.Interaction,
        question   : str,
    ) -> None:
        if not db.is_authorized(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        response = await engine.chat(
            channel_id  =interaction.channel_id,
            user_message=question,
        )

        embed = discord.Embed(description=response, color=0x5865F2)
        embed.set_author(name=f"پرسیار: {question[:80]}")
        embed.set_footer(text="Everything is under control AnDex")
        await interaction.followup.send(embed=embed)

    # ── /vision ───────────────────────────────────────────────
    @app_commands.command(
        name="vision",
        description="وێنەیەک بنێرە بۆ Aria تا بە کوردی شیکاری بکات",
    )
    @app_commands.describe(
        image  ="وێنەی پەیوەندراو",
        context="زیادەی پرسیار (ئارەزوومەندانە)",
    )
    async def vision(
        self,
        interaction: discord.Interaction,
        image      : discord.Attachment,
        context    : Optional[str] = None,
    ) -> None:
        if not db.is_authorized(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
            return

        valid_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        if not any(image.filename.lower().endswith(e) for e in valid_exts):
            await interaction.response.send_message(
                "❌ تەنها فایلی وێنە قبوڵ دەکرێت (PNG, JPG, GIF, WEBP).",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        image_bytes = await image.read()
        mime        = image.content_type or "image/png"

        prompt = context or "وێنەکە بە تەواوی شیکاری بکە و وەسفی وردی بدە."
        response = await engine.chat(
            channel_id  =interaction.channel_id,
            user_message=prompt,
            image_bytes =image_bytes,
            image_mime  =mime,
        )

        embed = discord.Embed(description=response, color=0xED4245)
        embed.set_image(url=image.url)
        embed.set_footer(text="Everything is under control AnDex")
        await interaction.followup.send(embed=embed)

    # ── /summarize ────────────────────────────────────────────
    @app_commands.command(
        name="summarize",
        description="دوایین پەیامەکانی چەناڵێک کورت بکەرەوە",
    )
    @app_commands.describe(
        channel="چەناڵی مەبەست",
        limit  ="ژمارەی پەیامەکان (بنەڕەت: 50)",
    )
    async def summarize(
        self,
        interaction: discord.Interaction,
        channel    : Optional[discord.TextChannel] = None,
        limit      : Optional[int]                 = 50,
    ) -> None:
        if not db.is_authorized(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
            return

        ch    = channel or interaction.channel
        limit = max(1, min(limit or 50, 200))

        await interaction.response.defer(thinking=True)

        lines: list[str] = []
        async for msg in ch.history(limit=limit, oldest_first=True):
            if msg.author.bot or not msg.content:
                continue
            lines.append(f"[{msg.author.display_name}]: {msg.content}")

        if not lines:
            await interaction.followup.send("❌ هیچ پەیامێکی مرۆڤ بۆ کورتکردنەوە نەدۆزرایەوە.", ephemeral=True)
            return

        prompt = (
            f"ئەم گفتوگۆیە لە چەناڵی {ch.name} کورت بکەرەوە بە کوردی سۆرانی:\n\n"
            + "\n".join(lines[:300])
        )
        summary = await engine.quick(prompt)

        embed = discord.Embed(
            title      =f"📝 کورتەی {ch.name}",
            description=summary,
            color      =0x57F287,
        )
        embed.set_footer(text=f"داواکار: {interaction.user.display_name} | AnDex")
        await interaction.followup.send(embed=embed)

    # ── /translate ────────────────────────────────────────────
    @app_commands.command(
        name="translate",
        description="دەقێک وەربگێڕە بۆ کوردی سۆرانی",
    )
    @app_commands.describe(text="ئەو دەقەی دەتەوێت وەربگێڕدرێت")
    async def translate(
        self,
        interaction: discord.Interaction,
        text       : str,
    ) -> None:
        if not db.is_authorized(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        prompt = f"ئەم دەقە وەربگێڕە بۆ کوردی سۆرانی بە شێوازێکی سروشتی:\n\n{text}"
        result = await engine.quick(prompt)

        embed = discord.Embed(
            title      ="🌐 وەرگێڕان بۆ کوردی",
            description=result,
            color      =0xFEE75C,
        )
        embed.add_field(name="دەقی ئەسڵی", value=f"_{text[:300]}_", inline=False)
        embed.set_footer(text="Everything is under control AnDex")
        await interaction.followup.send(embed=embed)

    # ── /generate_code ────────────────────────────────────────
    @app_commands.command(
        name="generate_code",
        description="کۆدی نوێ بە زمانێکی پرۆگرامسازی دروست بکە",
    )
    @app_commands.describe(
        language   ="زمانی پرۆگرامسازی (بۆ نموونە: Python, JS)",
        description="وەسفی ئەو کۆدەی پێویستتە",
    )
    async def generate_code(
        self,
        interaction: discord.Interaction,
        language   : str,
        description: str,
    ) -> None:
        if not db.is_authorized(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        prompt = (
            f"کۆدی {language} بنووسە بۆ ئەم داواکارییە:\n{description}\n\n"
            "تێبینی و Commentەکان بە کوردی بن. کۆدەکە پڕۆفیشناڵ بێت."
        )
        result = await engine.quick(prompt)

        if len(result) > 1800:
            file_obj = discord.File(
                fp      =io.BytesIO(result.encode()),
                filename=f"aria_code.txt",
            )
            await interaction.followup.send("📦 کۆدەکە زۆر گەورەیە، وەک فایل ناردراوە:", file=file_obj)
        else:
            await interaction.followup.send(f"```\n{result}\n```")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIChatCog(bot))
