"""Faollik middleware'i — har qanday interaksiyada last_seen'ni yangilaydi.

Muhim: eski usulda last_seen faqat MATNLI xabarlarда (upsert_user) yangilanardi.
Lekin "oyda bir"/"bir marta" eslatma qo'ygan user ko'pincha faqat TUGMA bosadi
(✅ Bajarildi, ⏰ Snooze) — bu callback, matn emas. Shu middleware har update'da
(xabar ham, tugma ham) last_seen'ni yangilaydi, shuning uchun tugma bosib
turadigan userlar ham to'g'ri "faol" deb hisoblanadi.
"""
import logging

from aiogram import BaseMiddleware

from app.database import db

logger = logging.getLogger(__name__)


class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # event_from_user odatda data'da bo'ladi; update darajasidagi outer
        # middleware'da hali to'ldirilmagan bo'lishi mumkin — o'shanda Update
        # ichidagi haqiqiy event'dan (message/callback) olamiz.
        user = data.get("event_from_user")
        if user is None:
            inner = getattr(event, "event", None)
            user = getattr(inner, "from_user", None)
        if user is not None:
            try:
                await db.touch_last_seen(user.id)
            except Exception:
                logger.exception("last_seen yangilanmadi (tg_id=%s)", user.id)
        return await handler(event, data)
