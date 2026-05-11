# ============================================================

# cogs/ai_chat.py  —  Aria Bot · AI Commands (Slash)

# ============================================================

from **future** import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from gemini_engine import engine

log = logging.getLogger(“aria.ai_chat”)

class AIChatCog(commands.Cog, name=“AIChat”):
def **init**(self, bot: commands.Bot) -> None:
self.bot = bot

```
# ── /ask ─────────────────────────────────────────────────
@app_commands.command(
    name="ask",
    description="پرسیارێک بکە Aria — بە کوردی یان ئینگلیزی",
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
    description="وێنەیەک بنێرە Aria بە کوردی شیکاری بکات",
)
@app_commands.describe(
    image  ="وێنەی پیوەندراو",
    context="زیادەی پرسیار (ئارەزوومەند)",
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

    if not any(image.filename.lower().endswith(e) for e in (".png",".jpg",".jpeg",".gif",".webp")):
        await interaction.response.send_message(
            "❌ تەنها فایلی وێنە قبوڵ دەکرێت (PNG، JPG، GIF، WEBP).",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)
    image_bytes = await image.read()
    mime        = image.content_type or "image/png"

    prompt = context or "وێنەکە بە تەواوی شیکاری بکە و وەسفی دەتاڵیانەی بدە."
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
    description="دوایین N پەیامی چەناڵێک کورت بکەرەوە",
)
@app_commands.describe(
    channel="چەناڵی مەبەست",
    limit  ="ژمارەی پەیام (بنەڕەت: ٥٠)",
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
        if msg.author.bot:
            continue
        lines.append(f"[{msg.author.display_name}]: {msg.content}")

    if not lines:
        await interaction.followup.send("❌ پەیامی مرۆڤی نەدۆزرایەوە.", ephemeral=True)
        return

    prompt = (
        f"ئەم گفتوگۆیە لە {ch.name} کورت بکەرەوە بە کوردی سۆرانی:\n\n"
        + "\n".join(lines[:300])   # cap to avoid token overflow
    )
    summary = await engine.quick(prompt)

    embed = discord.Embed(
        title      =f"📝 کورتەی {ch.mention}",
        description=summary,
        color      =0x57F287,
    )
    embed.set_footer(text=f"داواکار: {interaction.user.display_name}  |  Everything is under control AnDex")
    await interaction.followup.send(embed=embed)

# ── /translate ────────────────────────────────────────────
@app_commands.command(
    name="translate",
    description="دەقێک بگەڕێنە بۆ کوردی سۆرانی",
)
@app_commands.describe(text="دەقی وەرگێڕان")
async def translate(
    self,
    interaction: discord.Interaction,
    text       : str,
) -> None:
    if not db.is_authorized(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    prompt = (
        f"ئەم دەقە بگەڕێنە بۆ کوردی سۆرانی بە شێوازی سروشتی و ڕۆانی:\n\n{text}"
    )
    result = await engine.quick(prompt)

    embed = discord.Embed(
        title      ="🌐 وەرگێڕان → کوردی سۆرانی",
        description=result,
        color      =0xFEE75C,
    )
    embed.add_field(name="دەقی ئەصلی", value=f"_{text[:300]}_", inline=False)
    embed.set_footer(text="Everything is under control AnDex")
    await interaction.followup.send(embed=embed)

# ── /generate_code ────────────────────────────────────────
@app_commands.command(
    name="generate_code",
    description="کۆدی نوێ بە زمانی پرۆگرامی داواکراو دروست بکە",
)
@app_commands.describe(
    language   ="زمانی پرۆگرامی (مەسەلا: Python، JavaScript)",
    description="شرۆڤەی کۆدی پێویست",
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
        f"کۆدی {language} بنووسە بۆ ئەم داواکاریە:\n{description}\n\n"
        "شرۆڤەی کۆدەکان بە کوردی سۆرانی بنووسە (Comment ەکان). "
        "کۆدەکە پڕ-پیشەیی و ئامادەی بەکارهێنان بێت."
    )
    result = await engine.quick(prompt)

    # Send as file if large
    if len(result) > 1800:
        ext_map = {
            "python": "py", "javascript": "js", "typescript": "ts",
            "rust": "rs", "go": "go", "java": "java", "c++": "cpp",
            "c#": "cs", "bash": "sh",
        }
        file_ext = ext_map.get(language.lower(), "txt")
        file_obj = discord.File(
            fp      =__import__("io").BytesIO(result.encode()),
            filename=f"aria_code.{file_ext}",
        )
        await interaction.followup.send(
            f"📦 کۆدەکە زۆر گەورەیە — بە فایل ناردراوە:", file=file_obj
        )
    else:
        await interaction.followup.send(result)
```

async def setup(bot: commands.Bot) -> None:
await bot.add_cog(AIChatCog(bot))
