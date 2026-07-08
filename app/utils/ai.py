"""Gemini AI — ovozdan kelgan matnni tahlil qilish (data clean).

STT xom matnni beradi ("menga kechqurun sakkizu nol nolda eslatib yubor..."),
Gemini undan toza eslatma strukturasini chiqaradi. AI ishlamay qolsa
(kvota, tarmoq) — None qaytadi va bot oddiy regex tahlilga o'tadi.
"""
import json
import logging

import aiohttp

from app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)

PROMPT = """Sen eslatma botining tahlilchisisan. Foydalanuvchining og'zaki \
(ovozdan yozib olingan) eslatma so'rovini tahlil qilib, FAQAT JSON qaytar.

Maydonlar:
- "text": eslatma matni — nima haqida, qisqa va toza ("eslat", "menga", "iltimos" kabi so'zlarsiz)
- "freq": "once" | "daily" | "every2" | "weekly" | "monthly" | null (aniqlab bo'lmasa)
- "once_offset": 0 (bugun) | 1 (ertaga) | 2 (indinga) | null — faqat freq="once" bo'lsa
- "weekday": 0-6 (0=dushanba, 6=yakshanba) | null — faqat freq="weekly" bo'lsa
- "monthday": 1-31 | null — faqat freq="monthly" bo'lsa
- "hour": 0-23 | null
- "minute": 0-59 | null

Qoidalar:
- "kechqurun sakkizda" = 20:00, "ertalab sakkizda" = 08:00, "tushdan keyin uchda" = 15:00
- "sakkizu nol nol" = 08:00, "to'qqizu qirq besh" = 09:45, "sakkiz yarim" = 08:30
- "kun ora" = every2, "har kuni" = daily, hafta kuni nomi = weekly
- Aytilmagan narsani taxmin qilma — null qoldir
- STT xatolarini kontekstdan tuzat

So'rov: {input}"""


def ai_available() -> bool:
    return bool(GEMINI_API_KEY)


def _num(value, lo: int, hi: int) -> int | None:
    return value if isinstance(value, int) and lo <= value <= hi else None


def _validate(data) -> dict | None:
    """AI javobini parser formatiga keltiradi. Yaroqsiz bo'lsa None."""
    if not isinstance(data, dict):
        return None
    freq = data.get("freq")
    if freq not in ("once", "daily", "every2", "weekly", "monthly"):
        freq = None
    text = data.get("text")
    text = text.strip() if isinstance(text, str) and text.strip() else None
    if not text:
        return None
    hour = _num(data.get("hour"), 0, 23)
    minute = _num(data.get("minute"), 0, 59)
    if hour is None:
        minute = None
    elif minute is None:
        minute = 0
    return {
        "text": text,
        "freq": freq,
        "once_offset": _num(data.get("once_offset"), 0, 2) if freq == "once" else None,
        "weekday": _num(data.get("weekday"), 0, 6) if freq == "weekly" else None,
        "monthday": _num(data.get("monthday"), 1, 31) if freq == "monthly" else None,
        "hour": hour,
        "minute": minute,
    }


async def ai_parse_reminder(raw: str) -> dict | None:
    """Xom matnni Gemini orqali tahlil qiladi. Xatoda None (fallback: regex)."""
    if not ai_available():
        return None
    body = {
        "contents": [{"parts": [{"text": PROMPT.replace("{input}", raw)}]}],
        "generationConfig": {
            "temperature": 0,
            "response_mime_type": "application/json",
        },
    }
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                GEMINI_URL, headers={"x-goog-api-key": GEMINI_API_KEY}, json=body
            ) as resp:
                payload = await resp.json(content_type=None)
                if resp.status != 200:
                    logger.warning("Gemini xatosi (%s): %s", resp.status,
                                   str(payload)[:300])
                    return None
        answer = payload["candidates"][0]["content"]["parts"][0]["text"]
        result = _validate(json.loads(answer))
        if result:
            logger.info("Gemini tahlili: %s", result)
        return result
    except Exception:
        logger.exception("Gemini so'rovi muvaffaqiyatsiz")
        return None
