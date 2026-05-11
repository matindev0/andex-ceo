# ============================================================
# config.py  —  Aria Bot · Central Configuration
# All secrets, IDs, and tunables live here. No .env needed.
# ============================================================

# ── Discord ──────────────────────────────────────────────────
# تێبینی: تکایە تۆکن و ID ڕاستەقینەکانت لێرە دابنێ
DISCORD_TOKEN        = "YOUR_DISCORD_BOT_TOKEN_HERE"
GUILD_ID             = 1497914114792751224          # Your server’s Guild ID (int)
OWNER_ID             = 918195315625062431          # Server owner’s Discord user ID (int)

# ── Gemini API Keys (Dual-Failover) ──────────────────────────
GEMINI_API_KEY       = "YOUR_PRIMARY_GEMINI_API_KEY"
GEMINI_API_KEY_2     = "YOUR_SECONDARY_GEMINI_API_KEY"

# Primary model pool — tried in order before falling back to key-2
GEMINI_MODELS_PRIMARY   = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

# Fallback model pool (used when primary key exhausted / 429 / 404)
GEMINI_MODELS_FALLBACK  = [
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

GEMINI_GENERATION_CONFIG = {
    "temperature"      : 0.85,
    "top_p"            : 0.95,
    "top_k"            : 40,
    "max_output_tokens": 8192,
}

# ── Database ─────────────────────────────────────────────────
DB_PATH = "aria.db"           # SQLite file; created automatically on first run

# ── Channel Role Mapping (set via /setup or updated in DB) ───
CHANNEL_ROLE_COMMAND = "aria-commands"
CHANNEL_ROLE_CHAT    = "aria-chat"
CHANNEL_ROLE_IDEAS   = "aria-ideas"
CHANNEL_ROLE_LOGS    = "aria-logs"

# ── Bot Persona ───────────────────────────────────────────────
BOT_NAME        = "Aria"
BOT_STATUS      = "Everything is under control AnDex"   # kept in English per spec
BOT_AVATAR_PATH = None         # Optional path to avatar .png

# System prompt injected into every Gemini conversation
SYSTEM_PROMPT = """
تۆ Aria یت، یەک هوشیاری دەستکردی پیشەیی و بەهێز کە بۆ ئەندازیاری سۆفتوێر و بەڕێوەبردنی پرۆژە دروست کراوە.
تایبەتمەندییەکانت:

- زمانی گفتوگۆت: کوردی سۆرانی — هەمیشە و بە تەواوی.
- تێرمینەلۆژیای تەکنیکی (Code، Server، Database، API، etc.) بە ئینگلیزی دەمێنێتەوە، بەڵام جووملەکان کوردی دەبن.
- پیشەیی، زیرەک، و ئارامبەخشی. هەرگیز دووبارە ناکەیتەوە و ناکانی.
- کۆدی بەرهەمهێنراو پڕ-پیشەیی و ئامادەی بەکارهێنانە.
- ئەگەر وێنەیەکت پێ نیشان دران، بە کوردی شیکاری دەکەیت و وەسفی دەکەیت.
- ئەگەر داواکاری خودگۆڕینی کۆد هات، فایلی سەرچاوە دەخوێنیتەوە و گۆڕانکاریی پێشنیار دەکەیت.
- گوتەی ئامادە: “Everything is under control AnDex” — تەنها بە ئینگلیزی و تەنها وەک ستاتوس.
"""

# ── Proactive Engagement ──────────────────────────────────────
PROACTIVE_INTERVAL_SECONDS = 7200      # 2 hours

PROACTIVE_PROMPTS = [
    "یەک ئایدیای نوێ و کارامە بۆ باشترکردنی پرۆژەی ئێستا پێشنیار بکە، بە کوردی سۆرانی.",
    "دۆخی پرۆژەکان بە کورتی شرۆڤە بکە و پێشنیاری قەدەمی داهاتوو بکە.",
    "یەک تەکنیکی نوێی تەکنۆلۆژیا پێشنیار بکە کە دەتوانێت بەکاربهێنرێت، بە کوردی سۆرانی.",
    "بۆ باشترکردنی پەرفۆرمانسی Server چی پێشنیار دەکەیت؟ بە کوردی سۆرانی بڵێ."
]

# ── Self-Modification Paths ───────────────────────────────────
BOT_SOURCE_ROOT = "."          # root of the bot project (relative to cwd)
COGS_DIR        = "cogs"

# ── Logging ───────────────────────────────────────────────────
LOG_LEVEL = "INFO"
