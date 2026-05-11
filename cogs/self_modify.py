# ============================================================
# cogs/self_modify.py  —  Aria Bot · Self-Modification Engine
# ============================================================

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from gemini_engine import engine

log = logging.getLogger("aria.self_modify")
MAX_FILE_SIZE = 64_000  # Safety cap

class SelfModifyCog(commands.Cog, name="SelfModify"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /read_source ──────────────────────────────────────────
    @app_commands.command(
        name="read_source",
        description="(Owner) سۆرس کۆدی فایلێک بخوێنەرەوە و نیشان بدە",
    )
    @app_commands.describe(filepath="بۆ نموونە: cogs/admin.py یان config.py")
    async def read_source(self, interaction: discord.Interaction, filepath: str) -> None:
        if interaction.user.id != config.OWNER_ID:
            return await interaction.response.send_message("⛔ تەنها خاوەنی سێرڤەر دەتوانێت.", ephemeral=True)

        safe = self._safe_path(filepath)
        if safe is None or not safe.exists():
            return await interaction.response.send_message(f"❌ فایلی `{filepath}` نەدۆزرایەوە.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        content = safe.read_text(encoding="utf-8")
        
        if len(content) > MAX_FILE_SIZE:
            content = content[:MAX_FILE_SIZE] + "\n\n... [بڕدراوە - فایلەکە زۆر گەورەیە]"

        chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
        for i, chunk in enumerate(chunks):
            msg = f"```python\n{chunk}\n```"
            if i == 0:
                await interaction.followup.send(f"📄 **{filepath}**\n{msg}", ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)

    # ── /modify_source ────────────────────────────────────────
    @app_commands.command(
        name="modify_source",
        description="(Owner) داوا بکە Aria گۆڕانکاری پێشنیار بکات و جێبەجێی بکات",
    )
    @app_commands.describe(
        filepath   ="فایلی مەبەست (بۆ نموونە: cogs/admin.py)",
        instruction="شرۆڤەی گۆڕانکارییەکە بە کوردی",
        apply      ="بنووسە yes بۆ جێبەجێکردن"
    )
    async def modify_source(
        self, 
        interaction: discord.Interaction, 
        filepath: str, 
        instruction: str, 
        apply: str = "no"
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            return await interaction.response.send_message("⛔ تەنها خاوەن.", ephemeral=True)

        safe = self._safe_path(filepath)
        if safe is None or not safe.exists():
            return await interaction.response.send_message("❌ فایلەکە نەدۆزرایەوە.", ephemeral=True)

        await interaction.response.defer(thinking=True)
        original = safe.read_text(encoding="utf-8")
        
        suggestion = await engine.self_modify_suggestion(filepath, original[:MAX_FILE_SIZE], instruction)
        code_match = re.search(r"```python\s*(.*?)```", suggestion, re.DOTALL)
        new_code = code_match.group(1).strip() if code_match else None

        if apply.lower() == "yes" and new_code:
            # Backup
            safe.with_suffix(".py.bak").write_text(original, encoding="utf-8")
            safe.write_text(new_code, encoding="utf-8")

            reload_msg = ""
            if filepath.startswith("cogs/"):
                ext = filepath.replace("/", ".").removesuffix(".py")
                try:
                    await self.bot.reload_extension(ext)
                    reload_msg = f"✅ Cog `{ext}` نوێکرایەوە."
                except Exception as e:
                    reload_msg = f"⚠️ هەڵە لە نوێکردنەوە: `{e}`"
            
            await interaction.followup.send(f"✅ گۆڕانکاری کرا لە `{filepath}`.\n{reload_msg}")
        else:
            preview = suggestion[:1900]
            await interaction.followup.send(f"🔎 **پێشنیار بۆ `{filepath}`:**\n{preview}\n\nبۆ جێبەجێکردن: `apply: yes`.")

    # ── /add_cog ──────────────────────────────────────────────
    @app_commands.command(
        name="add_cog",
        description="(Owner) دروستکردنی Cog ی نوێ لەلایەن Aria"
    )
    async def add_cog(self, interaction: discord.Interaction, cog_name: str, description: str) -> None:
        if interaction.user.id != config.OWNER_ID:
            return await interaction.response.send_message("⛔ تەنها خاوەن.", ephemeral=True)

        safe_name = re.sub(r"[^\w]", "_", cog_name.lower())
        cog_file = Path(config.COGS_DIR) / f"{safe_name}.py"

        if cog_file.exists():
            return await interaction.response.send_message("⚠️ فایلەکە هەیە، `/modify_source` بەکاربهێنە.", ephemeral=True)

        await interaction.response.defer(thinking=True)
        prompt = f"کۆدی تەواوی discord.py Cog بنووسە بۆ: {description}. ناوی فایل: cogs/{safe_name}.py. تەنها کۆدەکە بنێرە."
        
        generated = await engine.quick(prompt)
        code_match = re.search(r"```python\s*(.*?)```", generated, re.DOTALL)
        new_code = code_match.group(1).strip() if code_match else generated.strip()

        cog_file.write_text(new_code, encoding="utf-8")
        
        try:
            await self.bot.load_extension(f"cogs.{safe_name}")
            await interaction.followup.send(f"✅ Cog ی نوێ `cogs/{safe_name}.py` دروستکرا و بارکرا.")
        except Exception as e:
            await interaction.followup.send(f"⚠️ فایلەکە دروستکرا بەڵام بارنەکرا: `{e}`")

    # ── /list_sources ─────────────────────────────────────────
    @app_commands.command(name="list_sources", description="لیستی هەموو فایلەکانی بۆت")
    async def list_sources(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != config.OWNER_ID: return
        root = Path(config.BOT_SOURCE_ROOT)
        files = [f"`{p.relative_to(root)}`" for p in root.rglob("*.py") if "__pycache__" not in str(p)]
        
        embed = discord.Embed(title="📁 سۆرس فایلەکانی Aria", description="\n".join(files), color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @staticmethod
    def _safe_path(filepath: str) -> Optional[Path]:
        root = Path(config.BOT_SOURCE_ROOT).resolve()
        try:
            target = (root / filepath).resolve()
            if root in target.parents or target == root:
                return target
        except:
            return None
        return None

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SelfModifyCog(bot))
