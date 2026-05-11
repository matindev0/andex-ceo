# ============================================================
# gemini_engine.py  —  Aria Bot · Dual-Failover Gemini Client
# ============================================================

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

import google.generativeai as genai

import config
import database as db

log = logging.getLogger("aria.gemini")

class GeminiEngine:
    """
    Thread-safe Gemini wrapper with:
    • Dual-API-key failover
    • Model-list cycling (flash → pro → fallback key)
    • Per-channel conversation history (from SQLite)
    • Vision (image) support
    """

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
        """Try the next model/key combination. Returns False when exhausted."""
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

    # ── Public API ────────────────────────────────────────────

    async def chat(
        self,
        channel_id: int,
        user_message: str,
        image_bytes: Optional[bytes] = None,
        image_mime: str = "image/png",
        extra_context: Optional[str] = None,
    ) -> str:
        async with self._lock:
            parts: list = []
            if extra_context:
                parts.append(extra_context)
            parts.append(user_message)

            if image_bytes:
                parts.append({
                    "mime_type": image_mime,
                    "data": base64.b64encode(image_bytes).decode(),
                })

            db.append_history(channel_id, "user", user_message)
            history = db.get_history(channel_id, limit=40)

            last_error = None
            total_attempts = len(config.GEMINI_MODELS_PRIMARY) + len(config.GEMINI_MODELS_FALLBACK) + 1
            
            for _ in range(total_attempts):
                try:
                    model = self._get_model()
                    chat_session = model.start_chat(history=history[:-1])
                    response = await asyncio.to_thread(chat_session.send_message, parts)
                    text = response.text.strip()
                    db.append_history(channel_id, "model", text)
                    return text
                except Exception as exc:
                    last_error = exc
                    err_str = str(exc).lower()
                    is_quota = any(k in err_str for k in ("429", "quota", "rate", "limit"))
                    if is_quota:
                        if not self._advance_model(): break
                    else:
                        log.error("Gemini error: %s", exc)
                        break
            return f"ببووری، کێشەیەک لە Gemini هەیە: `{last_error}`"

    async def quick(self, prompt: str) -> str:
        async with self._lock:
            for _ in range(len(config.GEMINI_MODELS_PRIMARY) + 1):
                try:
                    model = self._get_model()
                    response = await asyncio.to_thread(model.generate_content, prompt)
                    return response.text.strip()
                except Exception as exc:
                    if not self._advance_model(): break
            return "ببووری، هیچ مۆدێلێکی Gemini بەردەست نییە."

    async def acknowledge_request(self, channel_id: int, user_request: str) -> str:
        prompt = (
            f"داواکاری بەکارهێنەر: «{user_request}»\n\n"
            "ئەم داواکاریە تۆمار بکە و پشتراستی بکەرەوە بە کوردی سۆرانی.\n"
            "دەستوورەکان:\n"
            "• بە کورتی بڵێ کە تێگەیشتووی و تۆمارت کردووە.\n"
            "• بڵێ بۆ دروستکردنی کۆدی تەواو کلیک لە «🔨 Build New Version» بکە.\n"
            "• هیچ کۆدێک مەنووسە."
        )
        return await self.chat(channel_id=channel_id, user_message=user_request, extra_context=prompt)

    async def generate_versioned_build(
        self, project_name: str, version: int, channel_snapshot: str, previous_summary: str = ""
    ) -> str:
        prompt = (
            f"## پرۆژە: {project_name} | Version {
