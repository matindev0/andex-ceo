# ============================================================

# cogs/self_modify.py  —  Aria Bot · Self-Modification Engine

# ============================================================

from **future** import annotations

import importlib
import logging
import os
import re
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from gemini_engine import engine

log = logging.getLogger(“aria.self_modify”)

MAX_FILE_SIZE = 64_000   # chars — safety cap before sending to Gemini

class SelfModifyCog(commands.Cog, name=“SelfModify”):
def **init**(self, bot: commands.Bot) -> None:
self.bot = bot

```
# ── /read_source ──────────────────────────────────────────
@app_commands.command(
    name="read_source",
    description="(Owner) سۆرس کۆدی فایلێک بخوێنەرەوە و نیشان بدە",
)
@app_commands.describe(filepath="مەسەلا: cogs/admin.py  یان  config.py")
async def read_source(
    self,
    interaction: discord.Interaction,
    filepath   : str,
) -> None:
    if interaction.user.id != config.OWNER_ID:
        await interaction.response.send_message("⛔ تەنها خاوەنی سێرڤەر.", ephemeral=True)
        return

    safe = self._safe_path(filepath)
    if safe is None:
        await interaction.response.send_message(
            "⛔ فایلی داواکراو لە دەرەوەی قۆناغی Bot دایە.", ephemeral=True
        )
        return

    if not safe.exists():
        await interaction.response.send_message(f"❌ فایلی `{filepath}` نەدۆزرایەوە.", ephemeral=True)
        return

    content = safe.read_text(encoding="utf-8")
    if len(content) > MAX_FILE_SIZE:
        content = content[:MAX_FILE_SIZE] + "\n\n… [بریندراوە — فایل زۆر گەورەیە]"

    await interaction.response.defer(ephemeral=True, thinking=True)
    chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
    first  = True
    for chunk in chunks:
        msg = f"```python\n{chunk}\n```"
        if first:
            await interaction.followup.send(f"📄 **{filepath}**\n{msg}", ephemeral=True)
            first = False
        else:
            await interaction.followup.send(msg, ephemeral=True)

# ── /modify_source ────────────────────────────────────────
@app_commands.command(
    name="modify_source",
    description="(Owner) داوا بکە Aria گۆڕانکاریی پێشنیاری بکات و جێبەجێی بکات",
)
@app_commands.describe(
    filepath   ="فایلی مۆدیفایکراو (مەسەلا: cogs/admin.py)",
    instruction="شرۆڤەی گۆڕانکاری بە کوردی یان ئینگلیزی",
    apply      ="ئایا گۆڕانکاری جێبەجێ بکات؟ (بنووسە: yes بۆ جێبەجێکردن)",
)
async def modify_source(
    self,
    interaction: discord.Interaction,
    filepath   : str,
    instruction: str,
    apply      : str = "no",
) -> None:
    if interaction.user.id != config.OWNER_ID:
        await interaction.response.send_message("⛔ تەنها خاوەنی سێرڤەر.", ephemeral=True)
        return

    safe = self._safe_path(filepath)
    if safe is None or not safe.exists():
        await interaction.response.send_message("❌ فایلەکە نەدۆزرایەوە.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    original = safe.read_text(encoding="utf-8")
    suggestion = await engine.self_modify_suggestion(filepath, original[:MAX_FILE_SIZE], instruction)

    # Extract code block if Gemini wrapped it
    code_match = re.search(r"```python\s*(.*?)```", suggestion, re.DOTALL)
    new_code   = code_match.group(1).strip() if code_match else None

    if apply.lower() == "yes" and new_code:
        # Backup
        backup_path = safe.with_suffix(".py.bak")
        backup_path.write_text(original, encoding="utf-8")

        # Write new code
        safe.write_text(new_code, encoding="utf-8")

        # Hot-reload if it's a cog
        if filepath.startswith("cogs/"):
            ext = filepath.replace("/", ".").removesuffix(".py")
            try:
                await self.bot.reload_extension(ext)
                reload_msg = f"✅ Cog `{ext}` دووبارە بارکرا."
            except Exception as exc:
                reload_msg = f"⚠️ Reload شکستی هێنا: `{exc}`"
        else:
            reload_msg = "⚠️ فایلی سەرەکی — Restart پێویستە بۆ جێبەجێکردنی گۆڕانکاری."

        await interaction.followup.send(
            f"✅ گۆڕانکاری جێبەجێکرا لە `{filepath}`.\n"
            f"Backup: `{backup_path.name}`\n"
            f"{reload_msg}"
        )
        db_log = f"modify_source:{filepath}"
        await self.bot._log_to_discord(f"🔧 گۆڕانکاری کۆد: `{filepath}` — {instruction[:60]}")
    else:
        # Just show the suggestion
        preview = suggestion[:3800]
        await interaction.followup.send(
            f"🔎 **پێشنیاری Gemini بۆ `{filepath}`:**\n{preview}\n\n"
            "بۆ جێبەجێکردن دووبارە فەرمانەکە بخوێنەرەوە و `apply: yes` بنووسە."
        )

# ── /add_cog ──────────────────────────────────────────────
@app_commands.command(
    name="add_cog",
    description="(Owner) Aria داوا دەکات Cog ی نوێ بنووسێت و بیباتە خوارەوە",
)
@app_commands.describe(
    cog_name   ="ناوی فایلی نوێ (بێ .py، مەسەلا: reminders)",
    description="چی پێویستە ئەم Cog ە بکات؟",
)
async def add_cog(
    self,
    interaction: discord.Interaction,
    cog_name   : str,
    description: str,
) -> None:
    if interaction.user.id != config.OWNER_ID:
        await interaction.response.send_message("⛔ تەنها خاوەنی سێرڤەر.", ephemeral=True)
        return

    safe_name = re.sub(r"[^\w]", "_", cog_name.lower())
    cog_file  = Path(config.COGS_DIR) / f"{safe_name}.py"

    if cog_file.exists():
        await interaction.response.send_message(
            f"⚠️ فایلی `cogs/{safe_name}.py` هەیە. `/modify_source` بەکاربهێنە.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    prompt = (
        f"یەک discord.py Cog ی تەواو بنووسە بۆ ئەم داواکاریە:\n"
        f"ناوی فایل: cogs/{safe_name}.py\n"
        f"داواکاری: {description}\n\n"
        "پێویستییەکان:\n"
        "- discord.py 2.x بەکاربهێنە (app_commands Slash Commands)\n"
        "- هەموو پاسخەکان بە کوردی سۆرانی بن\n"
        "- تێرمینەلۆژیای تەکنیکی بە ئینگلیزی بمێنێت\n"
        "- `async def setup(bot)` لەکۆتاییدا هەبێت\n"
        "- کۆدی تەواو و ئامادەی جێبەجێکردن بنووسە\n"
        "- تەنها بلۆکی ```python ... ``` بدەرەوە"
    )

    generated = await engine.quick(prompt)
    code_match = re.search(r"```python\s*(.*?)```", generated, re.DOTALL)
    new_code   = code_match.group(1).strip() if code_match else generated.strip()

    cog_file.write_text(new_code, encoding="utf-8")

    # Load the new cog
    ext = f"{config.COGS_DIR}.{safe_name}"
    try:
        await self.bot.load_extension(ext)
        load_msg = f"✅ Cog `{ext}` بار و چالاک کرا."
        guild_obj = discord.Object(id=config.GUILD_ID)
        self.bot.tree.copy_global_to(guild=guild_obj)
        await self.bot.tree.sync(guild=guild_obj)
    except Exception as exc:
        load_msg = f"⚠️ بارکردن شکستی هێنا: `{exc}`"

    preview = new_code[:2000]
    await interaction.followup.send(
        f"✅ Cog ی نوێ دروست کرا: `cogs/{safe_name}.py`\n"
        f"{load_msg}\n\n"
        f"```python\n{preview}\n```"
    )
    await self.bot._log_to_discord(f"🆕 Cog ی نوێ زیادکرا: `{safe_name}` — {description[:60]}")

# ── /list_sources ─────────────────────────────────────────
@app_commands.command(
    name="list_sources",
    description="لیستی هەموو فایلەکانی Bot نیشان بدە",
)
async def list_sources(self, interaction: discord.Interaction) -> None:
    if interaction.user.id != config.OWNER_ID:
        await interaction.response.send_message("⛔ تەنها خاوەنی سێرڤەر.", ephemeral=True)
        return

    root  = Path(config.BOT_SOURCE_ROOT)
    files = sorted(
        p for p in root.rglob("*.py")
        if not any(part.startswith((".","__pycache__","venv","env")) for part in p.parts)
    )

    lines = [f"`{f.relative_to(root)}`  ({f.stat().st_size:,} bytes)" for f in files]
    embed = discord.Embed(
        title      ="📁 سۆرس فایلەکانی Aria",
        description="\n".join(lines) or "هیچ فایلێک نەدۆزرایەوە.",
        color      =0x5865F2,
    )
    embed.set_footer(text="Everything is under control AnDex")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── /reload_cog ───────────────────────────────────────────
@app_commands.command(
    name="reload_cog",
    description="(Owner) Cog ێک دووبارە بار بکە",
)
@app_commands.describe(cog_name="ناوی Cog (بێ cogs/ و .py، مەسەلا: admin)")
async def reload_cog(self, interaction: discord.Interaction, cog_name: str) -> None:
    if interaction.user.id != config.OWNER_ID:
        await interaction.response.send_message("⛔ تەنها خاوەنی سێرڤەر.", ephemeral=True)
        return

    ext = f"cogs.{cog_name.lower().strip()}"
    try:
        await self.bot.reload_extension(ext)
        await interaction.response.send_message(f"✅ `{ext}` دووبارە بارکرا.", ephemeral=True)
    except Exception as exc:
        await interaction.response.send_message(f"❌ `{exc}`", ephemeral=True)

# ── Helper ────────────────────────────────────────────────

@staticmethod
def _safe_path(filepath: str) -> Path | None:
    """Resolve path and ensure it's within the bot root."""
    root = Path(config.BOT_SOURCE_ROOT).resolve()
    try:
        target = (root / filepath).resolve()
    except Exception:
        return None
    if root not in target.parents and target != root:
        return None
    return target
```

async def setup(bot: commands.Bot) -> None:
await bot.add_cog(SelfModifyCog(bot))
