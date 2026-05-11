# ============================================================
# main.py  —  Aria Bot · Entry Point
# ============================================================

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands, tasks

import config
import database as db
from gemini_engine import engine

# ── Logging ───────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("aria.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("aria.main")

# ── Intents ───────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.guilds          = True

# ── Bot Class ─────────────────────────────────────────────────

class AriaBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="§§§",   # effectively disabled; we use slash commands
            intents=intents,
            help_command=None,
        )
        self.guild_id = config.GUILD_ID

    # ── Lifecycle ────────────────────────────────────────────

    async def setup_hook(self) -> None:
        db.init_db()
        await self._load_all_cogs()
        guild_obj = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild_obj)
        synced = await self.tree.sync(guild=guild_obj)
        log.info("Synced %d slash commands to guild %d", len(synced), self.guild_id)

    async def _load_all_cogs(self) -> None:
        cogs_path = Path(config.COGS_DIR)
        if not cogs_path.exists():
            cogs_path.mkdir(parents=True)

        for fpath in sorted(cogs_path.glob("*.py")):
            ext = f"{config.COGS_DIR}.{fpath.stem}"
            try:
                await self.load_extension(ext)
                log.info("Loaded cog: %s", ext)
            except Exception as exc:
                log.error("Failed to load cog %s: %s", ext, exc)

    async def on_ready(self) -> None:
        log.info("Aria is online as %s (ID %d)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.CustomActivity(name=config.BOT_STATUS),
            status=discord.Status.online,
        )
        if not self.proactive_task.is_running():
            self.proactive_task.start()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if guild.id != self.guild_id:
            log.warning("Joined unexpected guild %d — leaving.", guild.id)
            await guild.leave()

    # ── Message Handler ───────────────────────────────────────

    async def on_message(self, message: discord.Message) -> None:
        # Ignore bots and wrong guilds
        if message.author.bot:
            return
        if not message.guild or message.guild.id != self.guild_id:
            return

        # Only the owner may interact with Aria
        if not db.is_authorized(message.author.id, self.guild_id):
            return

        channels = db.get_all_channels(self.guild_id)
        chat_id  = channels.get("chat")

        # Chat channel — direct AI conversation (no prefix required)
        if chat_id and message.channel.id == chat_id:
            await self._handle_chat(message)
            return

        await self.process_commands(message)

    async def _handle_chat(self, message: discord.Message) -> None:
        async with message.channel.typing():
            image_bytes = None
            image_mime  = "image/png"

            if message.attachments:
                att = message.attachments[0]
                if any(att.filename.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    image_bytes = await att.read()
                    image_mime  = att.content_type or "image/png"

            response = await engine.chat(
                channel_id  = message.channel.id,
                user_message= message.content or "وێنەکە شیکاری بکە.",
                image_bytes = image_bytes,
                image_mime  = image_mime,
            )

        await self._send_long(message.channel, response)
        await self._log_to_discord(f"💬 {message.author.display_name}: {message.content[:80]}…")

    # ── Proactive Task ────────────────────────────────────────

    @tasks.loop(seconds=config.PROACTIVE_INTERVAL_SECONDS)
    async def proactive_task(self) -> None:
        import random
        channels = db.get_all_channels(self.guild_id)
        ideas_id = channels.get("ideas")
        if not ideas_id:
            return

        channel = self.get_channel(ideas_id)
        if not channel:
            return

        prompt = random.choice(config.PROACTIVE_PROMPTS)
        try:
            text = await engine.quick(prompt)
            embed = discord.Embed(
                title="💡 ئایدیای نوێ — Aria",
                description=text,
                color=0x5865F2,
            )
            embed.set_footer(text="Everything is under control AnDex")
            await channel.send(embed=embed)
        except Exception as exc:
            log.error("Proactive task failed: %s", exc)

    @proactive_task.before_loop
    async def _before_proactive(self) -> None:
        await self.wait_until_ready()

    # ── Utilities ─────────────────────────────────────────────

    async def _send_long(self, channel: discord.abc.Messageable, text: str) -> None:
        """Split and send messages that exceed Discord's 2000-char limit."""
        chunks = [text[i:i+1990] for i in range(0, len(text), 1990)]
        for chunk in chunks:
            await channel.send(chunk)

    async def _log_to_discord(self, message: str) -> None:
        channels = db.get_all_channels(self.guild_id)
        log_id   = channels.get("logs")
        if log_id:
            ch = self.get_channel(log_id)
            if ch:
                try:
                    await ch.send(f"`[LOG]` {message}")
                except Exception:
                    pass

# ── Entry Point ───────────────────────────────────────────────

bot = AriaBot()

async def main() -> None:
    async with bot:
        await bot.start(config.DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
