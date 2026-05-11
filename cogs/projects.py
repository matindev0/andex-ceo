# ============================================================

# cogs/projects.py  —  Aria Bot · Project Management

# 

# Build flow (two-stage, versioned):

# 

# User message in project channel

# │

# ▼

# Aria acknowledges in Kurdish   ← Stage 1  (no code sent)

# + posts “🔨 Build New Version” button

# │

# ▼  (button clicked)

# Scrape full channel history

# Generate complete source code  ← Stage 2  (Gemini heavy call)

# Post as “Updated Project Source — Version X”

# Record build in project_builds table

# ============================================================

from **future** import annotations

import json
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from gemini_engine import engine

log = logging.getLogger(“aria.projects”)

# ── Helpers ───────────────────────────────────────────────────

def _private_overwrites(
guild     : discord.Guild,
owner     : discord.Member,
bot_member: discord.Member,
) -> dict:
return {
guild.default_role: discord.PermissionOverwrite(view_channel=False),
owner              : discord.PermissionOverwrite(view_channel=True, send_messages=True),
bot_member         : discord.PermissionOverwrite(view_channel=True, send_messages=True),
}

async def _scrape_channel(channel: discord.TextChannel, limit: int = 400) -> str:
“””
Collect the full readable history of a project channel.
Skips bot build-output embeds (Version X headers) to avoid
polluting Gemini’s context with previously generated code.
Returns a plain-text transcript.
“””
lines: list[str] = []
async for msg in channel.history(limit=limit, oldest_first=True):
if msg.author.bot:
# Summarise build-output embeds rather than including full code
for embed in msg.embeds:
if embed.title and “Version” in embed.title:
lines.append(f”[Aria — Build Output: {embed.title} (skipped)]”)
break
else:
if msg.content:
lines.append(f”[Aria]: {msg.content}”)
continue
if msg.content:
lines.append(f”[{msg.author.display_name}]: {msg.content}”)

```
return "\n".join(lines) or "مێژووی گفتوگۆ نییە."
```

def _previous_build_summary(project_id: int) -> str:
“”“Short summary of prior builds for Gemini context.”””
builds = db.list_builds(project_id)
if not builds:
return “”
parts = [
f”v{b[‘version’]} — {b[‘status’]} ({b[‘created_at’][:10]})”
for b in builds
]
return “نەهاتووەکانی پێشوو: “ + “, “.join(parts)

# ── Persistent Views ──────────────────────────────────────────

class BuildVersionView(discord.ui.View):
“””
Posted after every Stage-1 acknowledgement.
Encodes project_id + version in custom_id so it survives restarts.
“””

```
def __init__(self, project_id: int, version: int) -> None:
    super().__init__(timeout=None)
    self.project_id = project_id
    self.version    = version
    self.build_btn.custom_id = f"build_version|{project_id}|{version}"

@discord.ui.button(
    label    ="🔨 Build New Version",
    style    =discord.ButtonStyle.success,
    custom_id="build_version|0|0",
)
async def build_btn(
    self, interaction: discord.Interaction, button: discord.ui.Button
) -> None:
    # Parse live custom_id (handles restarts where self.* may be 0)
    try:
        _, pid_str, ver_str = button.custom_id.split("|")
        project_id = int(pid_str)
        version    = int(ver_str)
    except (ValueError, AttributeError):
        project_id = self.project_id
        version    = self.version

    if not db.is_authorized(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
        return

    project = db.get_project(project_id)
    if not project:
        await interaction.response.send_message("❌ پرۆژەکە نەدۆزرایەوە.", ephemeral=True)
        return

    # Disable button immediately — prevent double-clicks
    button.disabled = True
    button.label    = f"⏳ دروستکردن … (v{version})"
    await interaction.response.edit_message(view=self)

    # ── Stage 2 ───────────────────────────────────────────
    channel_snapshot = await _scrape_channel(interaction.channel)
    prev_summary     = _previous_build_summary(project_id)

    build_id = db.create_build(
        project_id       = project_id,
        triggered_by     = interaction.user.id,
        version          = version,
        channel_snapshot = channel_snapshot,
    )
    db.update_project_status(project_id, "active")

    # Temporary "building…" embed
    building_embed = discord.Embed(
        title       = f"⚙️ دروستکردنی Version {version} …",
        description = (
            "Aria کۆی مێژووی گفتوگۆکەت دەخوێنێتەوە و کۆدی تەواو دەنووسێت.\n"
            "چەند خولەک چاوەڕێ بکە ⏳"
        ),
        color=0xFEE75C,
    )
    building_embed.set_footer(text="Everything is under control AnDex")
    status_msg = await interaction.channel.send(embed=building_embed)

    try:
        full_output = await engine.generate_versioned_build(
            project_name     = project["name"],
            version          = version,
            channel_snapshot = channel_snapshot,
            previous_summary = prev_summary,
        )
    except Exception as exc:
        db.fail_build(build_id, str(exc))
        log.error("Build v%d failed for project %d: %s", version, project_id, exc)
        await status_msg.delete()
        await interaction.channel.send(
            f"❌ بیناکردنی Version {version} شکستی هێنا:\n`{exc}`"
        )
        return

    await status_msg.delete()

    # ── Header embed ──────────────────────────────────────
    header_embed = discord.Embed(
        title=(
            f"📦 Updated Project Source — Version {version}\n"
            f"پرۆژە: {project['name']}"
        ),
        description=(
            f"✅ کۆدی تەواوی نوێترین نەهاتوو ئامادەیە\n"
            f"**داواکار:** {interaction.user.mention}  |  **Build ID:** `{build_id}`"
        ),
        color=0x57F287,
    )
    header_embed.set_footer(text="Everything is under control AnDex")
    first_msg = await interaction.channel.send(embed=header_embed)

    # Split output into ≤1990-char chunks
    chunks  = [full_output[i:i+1990] for i in range(0, len(full_output), 1990)]
    msg_ids = [str(first_msg.id)]
    for chunk in chunks:
        m = await interaction.channel.send(chunk)
        msg_ids.append(str(m.id))

    # Persist
    db.finish_build(
        build_id       = build_id,
        generated_code = full_output,
        discord_msg_ids= json.dumps(msg_ids),
    )
    db.add_project_log(
        project_id, interaction.user.id,
        f"build_v{version}",
        f"Version {version} دروست کرا — Build ID {build_id}",
    )

    # ── Invite next version ───────────────────────────────
    next_ver  = version + 1
    next_view = BuildVersionView(project_id, next_ver)
    nxt_embed = discord.Embed(
        description=(
            f"Version **{version}** تەواو بوو ✅\n"
            f"گۆڕانکارییەکانی نوێت بڵێ — Aria گوێی لێ دەگرێت، "
            f"کاتێک ئامادەیت **Version {next_ver}** دروست بکات."
        ),
        color=0x5865F2,
    )
    nxt_embed.set_footer(text="Everything is under control AnDex")
    await interaction.channel.send(embed=nxt_embed, view=next_view)

    await interaction.client._log_to_discord(
        f"🏗️ `{project['name']}` — Version {version} دروست کرا "
        f"(Build {build_id}, {len(chunks)} chunk)"
    )
```

class InitialBuildView(discord.ui.View):
“”“Welcome-message button for brand-new projects (triggers v1).”””

```
def __init__(self, project_id: int) -> None:
    super().__init__(timeout=None)
    self.project_id = project_id
    self.start_btn.custom_id = f"initial_build|{project_id}"

@discord.ui.button(
    label    ="🚀 پرۆژە بنا — Build v1",
    style    =discord.ButtonStyle.success,
    custom_id="initial_build|0",
)
async def start_btn(
    self, interaction: discord.Interaction, button: discord.ui.Button
) -> None:
    try:
        _, pid_str = button.custom_id.split("|")
        project_id = int(pid_str)
    except (ValueError, AttributeError):
        project_id = self.project_id

    if not db.is_authorized(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
        return

    button.disabled = True
    button.label    = "⏳ دروستکردنی v1 …"
    await interaction.response.edit_message(view=self)

    # Delegate to BuildVersionView v1 handler
    bvv = BuildVersionView(project_id, 1)
    bvv.build_btn.custom_id = f"build_version|{project_id}|1"
    await bvv.build_btn.callback(bvv, interaction, bvv.build_btn)
```

# ── Projects Cog ─────────────────────────────────────────────

class ProjectsCog(commands.Cog, name=“Projects”):

```
def __init__(self, bot: commands.Bot) -> None:
    self.bot = bot
    bot.add_view(InitialBuildView(0))
    bot.add_view(BuildVersionView(0, 0))

# ── Listener: Stage 1 acknowledgement ────────────────────

@commands.Cog.listener("on_message")
async def _project_channel_listener(self, message: discord.Message) -> None:
    """
    Intercepts messages in project channels.
    Aria acknowledges the request in Kurdish without generating code,
    then offers a Build New Version button.
    """
    if message.author.bot:
        return
    if not message.guild or message.guild.id != config.GUILD_ID:
        return
    if not db.is_authorized(message.author.id, message.guild.id):
        return

    project = db.get_project_by_channel(message.channel.id)
    if not project:
        return

    # Ignore trivially short messages or slash-command invocations
    content = message.content.strip()
    if len(content) < 8 or content.startswith("/"):
        return

    async with message.channel.typing():
        ack_text = await engine.acknowledge_request(
            channel_id   = message.channel.id,
            user_request = content,
        )

    next_version = db.next_build_version(project["id"])
    view         = BuildVersionView(project["id"], next_version)

    ack_embed = discord.Embed(description=ack_text, color=0x5865F2)
    ack_embed.set_author(
        name    =config.BOT_NAME,
        icon_url=message.guild.me.display_avatar.url,
    )
    ack_embed.set_footer(
        text=(
            f"Version {next_version} ئامادەی بیناکردنە  |  "
            "Everything is under control AnDex"
        )
    )
    await message.channel.send(embed=ack_embed, view=view)

# ── /new_project ──────────────────────────────────────────

@app_commands.command(
    name       ="new_project",
    description="پرۆژەیەکی تایبەت دروست بکە بە Category و Channel",
)
@app_commands.describe(
    name       ="ناوی پرۆژە",
    description="کورتەی پرۆژە (ئارەزوومەند)",
)
async def new_project(
    self,
    interaction: discord.Interaction,
    name       : str,
    description: Optional[str] = None,
) -> None:
    if not db.is_authorized(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    guild      = interaction.guild
    owner_mem  = guild.get_member(interaction.user.id)
    bot_mem    = guild.get_member(self.bot.user.id)
    overwrites = _private_overwrites(guild, owner_mem, bot_mem)

    safe_name = name[:90]
    category  = await guild.create_category(
        f"📁 {safe_name}", overwrites=overwrites
    )
    channel   = await guild.create_text_channel(
        name      =safe_name.lower().replace(" ", "-"),
        category  =category,
        overwrites=overwrites,
        topic     =f"پرۆژە: {safe_name} | {description or ''}",
    )

    proj_id = db.create_project(
        guild_id   =interaction.guild_id,
        owner_id   =interaction.user.id,
        name       =safe_name,
        description=description or "",
        category_id=category.id,
        channel_id =channel.id,
    )
    db.add_project_log(proj_id, interaction.user.id, "created", "پرۆژە دروست کرا")

    view  = InitialBuildView(proj_id)
    embed = discord.Embed(
        title      =f"🎯 پرۆژەی نوێ: {safe_name}",
        description=(
            f"**شرۆڤە:** {description or 'هێشتا زیاد نەکراوە'}\n\n"
            "**چۆن کار دەکات:**\n"
            "١. داواکارییەکانت بنووسە — Aria گوێی لێ دەگرێت و پشتراستی دەکاتەوە\n"
            "٢. Aria **هیچ کۆدێک** لە قۆناغی یەکەمدا ناناردێت\n"
            "٣. دووگمەی **🔨 Build New Version** دابگرە بۆ دروستکردنی کۆدی تەواو\n"
            "٤. هەر بیناکردنێک وەک **Version X** تۆمار دەکرێت"
        ),
        color=0x5865F2,
    )
    embed.set_footer(text="Everything is under control AnDex")
    await channel.send(embed=embed, view=view)

    await interaction.followup.send(
        f"✅ پرۆژە دروست کرا: {channel.mention}", ephemeral=True
    )
    await self.bot._log_to_discord(
        f"📁 پرۆژەی نوێ `{safe_name}` (ID:{proj_id}) دروست کرا"
    )

# ── /list_projects ────────────────────────────────────────

@app_commands.command(
    name       ="list_projects",
    description="لیستی هەموو پرۆژەکان نیشان بدە",
)
@app_commands.describe(status="فلتەر بە دۆخ (planning | active | done)")
async def list_projects(
    self,
    interaction: discord.Interaction,
    status     : Optional[str] = None,
) -> None:
    if not db.is_authorized(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
        return

    rows = db.list_projects(interaction.guild_id, status=status)
    if not rows:
        await interaction.response.send_message(
            "📂 هیچ پرۆژەیەک نەدۆزرایەوە.", ephemeral=True
        )
        return

    STATUS_EMOJI = {"planning": "🗒️", "active": "⚙️", "done": "✅"}
    embed = discord.Embed(
        title=f"📂 پرۆژەکان{(' — ' + status) if status else ''}",
        color=0x5865F2,
    )
    for row in rows[:20]:
        builds     = db.list_builds(row["id"])
        last_ver   = f"v{builds[-1]['version']}" if builds else "بیناکراو نییە"
        ch_mention = f"<#{row['channel_id']}>" if row["channel_id"] else "—"
        emoji      = STATUS_EMOJI.get(row["status"], "❓")
        embed.add_field(
            name  =f"{emoji} {row['name']} (ID: {row['id']})",
            value =(
                f"دۆخ: `{row['status']}` | دوایین: `{last_ver}` | {ch_mention}\n"
                f"_{row['description'][:80] or '—'}_"
            ),
            inline=False,
        )
    embed.set_footer(
        text=f"کۆی گشتی: {len(rows)} پرۆژە  |  Everything is under control AnDex"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── /build_history ────────────────────────────────────────

@app_commands.command(
    name       ="build_history",
    description="مێژووی هەموو Versions ی پرۆژەیەک نیشان بدە",
)
@app_commands.describe(project_id="ID ی پرۆژە")
async def build_history(
    self,
    interaction: discord.Interaction,
    project_id : int,
) -> None:
    if not db.is_authorized(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
        return

    project = db.get_project(project_id)
    if not project or project["guild_id"] != interaction.guild_id:
        await interaction.response.send_message("❌ پرۆژەکە نەدۆزرایەوە.", ephemeral=True)
        return

    builds = db.list_builds(project_id)
    embed  = discord.Embed(
        title =f"🏗️ مێژووی بیناکردن: {project['name']}",
        color =0xEB459E,
    )
    STATUS_ICONS = {
        "pending": "⏳", "building": "⚙️", "done": "✅", "failed": "❌"
    }
    for b in builds:
        icon    = STATUS_ICONS.get(b["status"], "❓")
        msg_ids = json.loads(b["discord_msg_ids"] or "[]")
        embed.add_field(
            name  =f"{icon} Version {b['version']}  (Build ID: {b['id']})",
            value =(
                f"دۆخ: `{b['status']}`\n"
                f"دروستکراوە: `{b['created_at'][:16]}`\n"
                f"تەواوبووە: `{(b['completed_at'] or '—')[:16]}`\n"
                f"Discord پەیامەکان: {len(msg_ids)}"
            ),
            inline=False,
        )
    if not builds:
        embed.description = "هیچ بیناکردنێک تۆمار نەکراوە."
    embed.set_footer(text="Everything is under control AnDex")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── /project_log ─────────────────────────────────────────

@app_commands.command(
    name       ="project_log",
    description="تۆمارەکانی چالاکییەکانی پرۆژەیەک",
)
@app_commands.describe(project_id="ID ی پرۆژە")
async def project_log(
    self,
    interaction: discord.Interaction,
    project_id : int,
) -> None:
    if not db.is_authorized(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message("⛔ مۆڵەتت نییە.", ephemeral=True)
        return

    project = db.get_project(project_id)
    if not project or project["guild_id"] != interaction.guild_id:
        await interaction.response.send_message("❌ پرۆژەکە نەدۆزرایەوە.", ephemeral=True)
        return

    logs  = db.get_project_logs(project_id, limit=20)
    embed = discord.Embed(
        title=f"📋 تۆمارەکانی پرۆژە: {project['name']}",
        color=0xEB459E,
    )
    for entry in logs:
        embed.add_field(
            name  =f"🔹 {entry['action']}",
            value =f"{entry['detail'] or '—'}\n`{entry['created_at']}`",
            inline=False,
        )
    if not logs:
        embed.description = "هیچ تۆمارێک نەدۆزرایەوە."
    embed.set_footer(text="Everything is under control AnDex")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── /close_project ────────────────────────────────────────

@app_commands.command(
    name       ="close_project",
    description="پرۆژەیەک دادخەرێنە و وەک تەواوکراو نیشانی بکە",
)
@app_commands.describe(project_id="ID ی پرۆژە")
async def close_project(
    self,
    interaction: discord.Interaction,
    project_id : int,
) -> None:
    if interaction.user.id != config.OWNER_ID:
        await interaction.response.send_message(
            "⛔ تەنها خاوەنی سێرڤەر دەتوانێت.", ephemeral=True
        )
        return

    project = db.get_project(project_id)
    if not project or project["guild_id"] != interaction.guild_id:
        await interaction.response.send_message("❌ نەدۆزرایەوە.", ephemeral=True)
        return

    db.update_project_status(project_id, "done")
    db.add_project_log(project_id, interaction.user.id, "closed", "پرۆژە داخرا")
    await interaction.response.send_message(
        f"✅ پرۆژە `{project['name']}` داخرا و وەک **تەواوکراو** تۆمار کرا.",
        ephemeral=True,
    )
```

async def setup(bot: commands.Bot) -> None:
await bot.add_cog(ProjectsCog(bot))
