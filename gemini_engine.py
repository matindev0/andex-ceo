# ============================================================

# gemini_engine.py  —  Aria Bot · Dual-Failover Gemini Client

# ============================================================

from **future** import annotations

import asyncio
import base64
import logging
from typing import Optional

import google.generativeai as genai

import config
import database as db

log = logging.getLogger(“aria.gemini”)

class GeminiEngine:
“””
Thread-safe Gemini wrapper with:
• Dual-API-key failover
• Model-list cycling (flash → pro → fallback key)
• Per-channel conversation history (from SQLite)
• Vision (image) support
“””

```
def __init__(self) -> None:
    self._primary_key_index   = 0    # index in GEMINI_MODELS_PRIMARY
    self._fallback_key_index  = 0    # index in GEMINI_MODELS_FALLBACK
    self._using_fallback      = False
    self._lock                = asyncio.Lock()

    # Initialise with primary key
    genai.configure(api_key=config.GEMINI_API_KEY)

# ── Internal helpers ──────────────────────────────────────

def _get_model(self) -> genai.GenerativeModel:
    if self._using_fallback:
        model_name = config.GEMINI_MODELS_FALLBACK[self._fallback_key_index]
    else:
        model_name = config.GEMINI_MODELS_PRIMARY[self._primary_key_index]

    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=config.GEMINI_GENERATION_CONFIG,
        system_instruction=config.SYSTEM_PROMPT,
    )

def _advance_model(self) -> bool:
    """
    Try the next model/key combination.
    Returns False when all combinations exhausted.
    """
    if not self._using_fallback:
        next_primary = self._primary_key_index + 1
        if next_primary < len(config.GEMINI_MODELS_PRIMARY):
            self._primary_key_index = next_primary
            log.warning("Switched to primary model #%d", next_primary)
            return True
        # Switch to fallback key
        self._using_fallback = True
        self._fallback_key_index = 0
        genai.configure(api_key=config.GEMINI_API_KEY_2)
        log.warning("Switched to FALLBACK Gemini API key")
        return True

    next_fallback = self._fallback_key_index + 1
    if next_fallback < len(config.GEMINI_MODELS_FALLBACK):
        self._fallback_key_index = next_fallback
        log.warning("Switched to fallback model #%d", next_fallback)
        return True

    log.error("All Gemini API keys and models exhausted!")
    return False

def _reset_to_primary(self) -> None:
    self._primary_key_index  = 0
    self._fallback_key_index = 0
    self._using_fallback     = False
    genai.configure(api_key=config.GEMINI_API_KEY)

# ── Public API ────────────────────────────────────────────

async def chat(
    self,
    channel_id: int,
    user_message: str,
    image_bytes: Optional[bytes] = None,
    image_mime: str = "image/png",
    extra_context: Optional[str] = None,
) -> str:
    """
    Send a message and receive a response.
    Conversation history is persisted in SQLite per channel_id.
    """
    async with self._lock:
        # Build content parts
        parts: list = []
        if extra_context:
            parts.append(extra_context)
        parts.append(user_message)

        if image_bytes:
            parts.append({
                "mime_type": image_mime,
                "data": base64.b64encode(image_bytes).decode(),
            })

        # Store user turn
        db.append_history(channel_id, "user", user_message)

        # Retrieve full history for context window
        history = db.get_history(channel_id, limit=40)

        # Attempt with failover
        last_error = None
        for _ in range(len(config.GEMINI_MODELS_PRIMARY) + len(config.GEMINI_MODELS_FALLBACK) + 1):
            try:
                model = self._get_model()
                chat_session = model.start_chat(history=history[:-1])  # last msg is current
                response = await asyncio.to_thread(
                    chat_session.send_message, parts
                )
                text = response.text.strip()
                db.append_history(channel_id, "model", text)
                return text

            except Exception as exc:
                last_error = exc
                err_str = str(exc).lower()
                is_quota = any(k in err_str for k in ("429", "quota", "rate", "limit", "exhausted"))
                is_model = any(k in err_str for k in ("404", "not found", "deprecated"))

                if is_quota or is_model:
                    log.warning("Gemini error (%s) — advancing model/key…", exc)
                    if not self._advance_model():
                        break
                else:
                    log.error("Non-retryable Gemini error: %s", exc)
                    break

        return (
            "ببووری، ئێستا گەیشتووم بە سنووری زانینم. "
            f"کێشەکە: `{last_error}`"
        )

async def quick(self, prompt: str) -> str:
    """One-shot prompt without history (for proactive messages, etc.)."""
    async with self._lock:
        for _ in range(len(config.GEMINI_MODELS_PRIMARY) + len(config.GEMINI_MODELS_FALLBACK) + 1):
            try:
                model = self._get_model()
                response = await asyncio.to_thread(model.generate_content, prompt)
                return response.text.strip()
            except Exception as exc:
                if not self._advance_model():
                    return f"ببووری، هەڵەی Gemini: `{exc}`"
        return "ببووری، هیچ Model ی Gemini ی بەردەست نییە."

async def analyse_image(self, image_bytes: bytes, mime: str = "image/png") -> str:
    """Describe / analyse an image in Kurdish."""
    prompt = (
        "وێنەکە بە کوردی سۆرانی شیکاری بکە و وەسفی دەتاڵیانەی پێ بدە. "
        "هەر تەکست یان نیشانە دیاری بکە. زمان: کوردی سۆرانی بەتەنها."
    )
    return await self.chat(
        channel_id=0,           # ephemeral — no history stored
        user_message=prompt,
        image_bytes=image_bytes,
        image_mime=mime,
    )

async def build_project_solution(self, project_name: str, chat_history_text: str) -> str:
    """Generate a full technical solution from project channel history."""
    prompt = (
        f"پرۆژەکە: **{project_name}**\n\n"
        f"مێژووی گفتوگۆی چەناڵی پرۆژە:\n```\n{chat_history_text}\n```\n\n"
        "بە کوردی سۆرانی:\n"
        "١. تەکنیک و ئامێرەکانی پێویست ناسیبکە\n"
        "٢. ئەرشیتیکچەری سیستەمەکە شرۆڤە بکە\n"
        "٣. کۆدی سەرەکی بنووسە (Python/JS/هەرچی گونجاوە)\n"
        "٤. قەدەمەکانی جێبەجێکردن ڕیز بکە\n"
        "٥. ئاگاداری و خستراوە پێشنیار بکە\n"
        "کۆدەکان بە ئینگلیزی بمێنن، شرۆڤەکان بە کوردی بن."
    )
    return await self.quick(prompt)

async def self_modify_suggestion(self, file_path: str, file_content: str, instruction: str) -> str:
    """Ask Gemini to suggest modifications to a bot source file."""
    prompt = (
        f"ئەمە کۆدی فایلی `{file_path}` یە:\n```python\n{file_content}\n```\n\n"
        f"داواکاری گۆڕانکاری: {instruction}\n\n"
        "تکایە:\n"
        "١. کۆدی تەواوی گۆڕاوەکە بنووسە (ئامادەی جێنووسینەوە)\n"
        "٢. گۆڕانکاریەکانت بە کوردی شرۆڤە بکە\n"
        "٣. ئەگەر کێشەیەک هەبێت ئاگادارم بکەرەوە\n"
        "کۆدەکە لە بلۆکی ```python ... ``` دا بنووسە."
    )
    return await self.quick(prompt)

async def acknowledge_request(self, channel_id: int, user_request: str) -> str:
    """
    Stage 1 — Acknowledge a feature/change request WITHOUT generating code.
    Returns a short Kurdish confirmation that queues the build.
    """
    prompt = (
        f"داواکاری بەکارهێنەر: «{user_request}»\n\n"
        "ئەم داواکاریە تۆمار بکە و پشتراستی بکەرەوە بە کوردی سۆرانی.\n"
        "دەستوورەکان:\n"
        "• داواکاری بە کورتی دووبارە بکەرەوە تا دەرکەوت فامت کردووە\n"
        "• ڕوون بکەرەوە کە ئەمە تۆمار کراوە و بناغەی نوێترین نەهاتووەتەوە\n"
        "• بە بەکارهێنەر بڵێ کە دووگمەی «🔨 Build New Version» دابگرێت بۆ دروستکردنی کۆدی تەواو\n"
        "• کورت بە، پیشەیی، و هاریکارانە — زۆرتر لە ٣ جووملە نەبێت\n"
        "• هیچ کۆدێک نەنووسە"
    )
    # Store in channel history so acknowledgement is part of conversation context
    response = await self.chat(channel_id=channel_id, user_message=user_request,
                               extra_context=prompt)
    return response

async def generate_versioned_build(
    self,
    project_name   : str,
    version        : int,
    channel_snapshot: str,
    previous_summary: str = "",
) -> str:
    """
    Stage 2 — Full source-code generation triggered by the Build button.
    Uses the complete channel snapshot plus an optional summary of prior builds.
    """
    prev_block = (
        f"### خولاصەی نەهاتوەکانی پێشوو:\n{previous_summary}\n\n"
        if previous_summary else ""
    )
    prompt = (
        f"## پرۆژە: {project_name}  |  Version {version}\n\n"
        f"{prev_block}"
        f"### کۆی مێژووی گفتوگۆی چەناڵ (هەموو داواکارییەکان و گۆڕانکارییەکان):\n"
        f"```\n{channel_snapshot}\n```\n\n"
        "---\n"
        "بە کوردی سۆرانی:\n\n"
        f"**نەهاتووی تەواوی پرۆژەی نوێ — Version {version}** دروست بکە:\n"
        "١. خولاصەی داواکارییەکانی نوێ لە نەهاتووەکانی پێشوو جیابکەرەوە\n"
        "٢. ئەرشیتیکچەری نوێکراوەکە شرۆڤە بکە\n"
        "٣. کۆدی سەرچاوەی تەواو بنووسە — هیچ شتێک کەم نەکە\n"
        "   • هەر فایلێک بە ناوی خۆی و ```language ... ``` code-block\n"
        "   • ئەگەر ژمارەی فایلەکان زۆرە، هەموویان لە ئەم وەڵامەدا دابنێ\n"
        "٤. دەستوورەکانی دامەزراندن و بەکارهێنان بنووسە\n"
        "٥. گۆڕانکارییە نوێیەکان بە ئینگلیزی نووسی و بە کوردی شرۆڤەیان بکە\n\n"
        "کۆدەکان بە ئینگلیزی، شرۆڤەکان بە کوردی سۆرانی."
    )
    return await self.quick(prompt)
```

# Singleton

engine = GeminiEngine()
