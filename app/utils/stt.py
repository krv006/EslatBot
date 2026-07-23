"""Ovozni matnga aylantirish — uzbekvoice.ai (Mohir AI) STT API.

Telegram'dan kelgan ovozli xabar yuklab olinadi va API'ga yuboriladi,
qaytgan matn eslatma sifatida qayta ishlanadi.
"""
import logging
import re
from io import BytesIO

import aiohttp
from aiogram import Bot

from app.config import MOHIR_API_KEY

logger = logging.getLogger(__name__)

STT_URL = "https://uzbekvoice.ai/api/v1/stt"


def stt_available() -> bool:
    return bool(MOHIR_API_KEY)


def _strip_labels(text: str) -> str:
    """STT qo'shadigan 'Speaker 0:' kabi yorliqlarni olib tashlaydi."""
    text = re.sub(r"\bspeaker\s*\d+\s*:\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


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


async def voice_to_text(message) -> str | None:
    """Ovozli xabarni to'liq muomala bilan matnga aylantiradi.

    STT yo'qligi, uzunlik chegarasi va xatolarda foydalanuvchiga o'zi javob
    berib None qaytaradi — barcha oqimlar (yangi eslatma, referal, kunlik
    reja) bitta xulqda ishlashi uchun.
    """
    from app.utils.fmt import esc  # aylanma import bo'lmasligi uchun shu yerda

    if not stt_available():
        await message.answer(
            "Ovozli xabarlarni hozircha tushunmayman 😅 Iltimos, yozib yuboring."
        )
        return None
    if message.voice.duration > 120:
        await message.answer(
            "Ovozli xabar juda uzun (2 daqiqagacha qabul qilaman) 😅"
        )
        return None
    wait_msg = await message.answer("🎙 Eshityapman...")
    text = await transcribe_voice(message.bot, message.voice.file_id)
    if not text:
        await wait_msg.edit_text(
            "Ovozni tushuna olmadim 😔 Qaytadan urinib ko'ring yoki yozib yuboring."
        )
        return None
    await wait_msg.edit_text(f"🎙 Eshitdim: <i>«{esc(text)}»</i>")
    return text


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
        return None
    return _strip_labels(text) or None
