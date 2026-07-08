"""Ovozni matnga aylantirish — uzbekvoice.ai (Mohir AI) STT API.

Telegram'dan kelgan ovozli xabar yuklab olinadi va API'ga yuboriladi,
qaytgan matn eslatma sifatida qayta ishlanadi.
"""
import logging
from io import BytesIO

import aiohttp
from aiogram import Bot

from app.config import MOHIR_API_KEY

logger = logging.getLogger(__name__)

STT_URL = "https://uzbekvoice.ai/api/v1/stt"


def stt_available() -> bool:
    return bool(MOHIR_API_KEY)


def _extract_text(payload) -> str | None:
    """Javob JSON'idan matnni topadi (turli formatlarga chidamli)."""
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if isinstance(payload, dict):
        for key in ("conversation_text", "text", "transcript", "transcription",
                    "result", "data"):
            if key in payload:
                found = _extract_text(payload[key])
                if found:
                    return found
    if isinstance(payload, list):
        parts = [_extract_text(item) for item in payload]
        parts = [p for p in parts if p]
        if parts:
            return " ".join(parts)
    return None


async def transcribe_voice(bot: Bot, file_id: str) -> str | None:
    """Ovozli xabarni matnga aylantiradi. Xatoda None qaytaradi."""
    if not stt_available():
        return None

    buf = BytesIO()
    await bot.download(file_id, destination=buf)
    buf.seek(0)

    form = aiohttp.FormData()
    form.add_field("file", buf, filename="voice.ogg", content_type="audio/ogg")
    form.add_field("return_offsets", "false")
    form.add_field("run_diarization", "false")
    form.add_field("language", "uz")
    form.add_field("blocking", "true")

    try:
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                STT_URL, data=form, headers={"Authorization": MOHIR_API_KEY}
            ) as resp:
                payload = await resp.json(content_type=None)
                if resp.status != 200:
                    logger.error("STT xatosi (%s): %s", resp.status, payload)
                    return None
    except Exception:
        logger.exception("STT so'rovi muvaffaqiyatsiz")
        return None

    text = _extract_text(payload)
    if not text:
        logger.warning("STT javobidan matn topilmadi: %s", payload)
    return text
