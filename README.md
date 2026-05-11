# 🤖 Aria Bot — Kurdish AI Discord Agent

> **“Everything is under control AnDex”**

Aria یەک Agent ی Discord ی هوشیار و خۆگۆڕاوە، بە زمانی کوردی سۆرانی قسە دەکات، بە Google Gemini AI هێزداراوە، و بۆ خاوەنی سێرڤەر تایبەتە.

-----

## 📁 ساختاری پرۆژە

```
aria-bot/
├── main.py              # Entry point — bot lifecycle + message routing
├── config.py            # All settings, keys, IDs (no .env needed)
├── database.py          # SQLite manager — projects, channels, history
├── gemini_engine.py     # Dual-failover Gemini AI client
├── requirements.txt
├── aria.db              # Auto-created on first run
├── aria.log             # Auto-created on first run
└── cogs/
    ├── admin.py         # /setup  /authorize  /status  /clear_history
    ├── ai_chat.py       # /ask  /vision  /summarize  /translate  /generate_code
    ├── projects.py      # /new_project  /list_projects  /project_log  /close_project
    └── self_modify.py   # /read_source  /modify_source  /add_cog  /list_sources  /reload_cog
```

-----

## ⚡ دەستپێکردن (Setup)

### ١. پێشمەرجەکان دامەزرێنە

```bash
pip install -r requirements.txt
```

### ٢. `config.py` ئامادە بکە

```python
DISCORD_TOKEN    = "your_bot_token"
GUILD_ID         = 123456789          # Your server ID
OWNER_ID         = 987654321          # Your Discord user ID
GEMINI_API_KEY   = "primary_key"
GEMINI_API_KEY_2 = "fallback_key"
```

### ٣. Bot دەستپێ بکە

```bash
python main.py
```

### ٤. سازکردنی سێرڤەر

لەناو Discord، فەرمانەکە بەکاربهێنە:

```
/setup command_channel:#aria-commands chat_channel:#aria-chat
       ideas_channel:#aria-ideas logs_channel:#aria-logs
```

-----

## 🏗️ ئەرشیتیکچەر

### Dual Gemini Failover

```
Request
   │
   ▼
[ Primary Key ] → gemini-1.5-flash
   │ 429/404?
   ▼
[ Primary Key ] → gemini-1.5-pro
   │ 429/404?
   ▼
[ Fallback Key ] → gemini-1.5-pro
   │ 429/404?
   ▼
[ Fallback Key ] → gemini-1.5-flash
   │ Exhausted?
   ▼
Kurdish error message to user
```

### Channel Logic

|چەناڵ           |ڕۆڵ                                              |
|----------------|-------------------------------------------------|
|`#aria-commands`|تەنها Slash Commands                             |
|`#aria-chat`    |گفتوگۆی ڕاستەوخۆ — بێ prefix، وێنە پشتیوانی دەکات|
|`#aria-ideas`   |Aria هەر ٢ کاتژمێر خۆکارانە ئایدیا دەنێرێت       |
|`#aria-logs`    |تۆمارکردنی هەموو چالاکییەکان                     |

### Self-Modification Flow

```
/modify_source filepath:"cogs/admin.py" instruction:"Add rate limiting"
   │
   ▼
Read current source → Send to Gemini → Get new code
   │
   ▼
apply:"yes"? → Backup .py.bak → Overwrite → hot reload_extension
```

### Project Flow

```
/new_project name:"My App" description:"..."
   │
   ▼
Private Category + Channel created
   │
   ▼
User discusses project in channel
   │
   ▼
[🚀 Build Project] button clicked
   │
   ▼
Aria scrapes 200 messages → sends to Gemini with context
   │
   ▼
Full technical solution generated in Kurdish
```

-----

## 🛠️ Slash Commands

### Admin (`/setup`, `/authorize`, `/status`, `/clear_history`)

### AI Chat (`/ask`, `/vision`, `/summarize`, `/translate`, `/generate_code`)

### Projects (`/new_project`, `/list_projects`, `/project_log`, `/close_project`)

### Self-Modify (`/read_source`, `/modify_source`, `/add_cog`, `/list_sources`, `/reload_cog`)

-----

## 🔐 Discord Bot Permissions Required

- `Send Messages`, `Read Message History`, `Embed Links`, `Attach Files`
- `Manage Channels`, `Manage Roles` (for /new_project)
- `Use Application Commands`

**Privileged Gateway Intents:** `Message Content`, `Server Members`

-----

## 📝 تێبینی

- هەموو گفتوگۆی AI بە SQLite پاشەکەوت دەبێت (بە channel ID)
- هەر چەناڵێک تایبەت مێژووی خۆی هەیە (٤٠ پەیام)
- Bot تەنها لە سێرڤەری دیاریکراو کار دەکات (GUILD_ID)
- خۆگۆڕینی کۆد بەکارئامادەیە — `.py.bak` backup خودکارانەی دروست دەکات
