"""Chiquvchi xabarlar navbati — Telegram flood limitidan himoya (10 000+ user).

Muammo: ertalab 07:00 da minglab digest (yoki mashhur vaqtdagi eslatmalar) bir
vaqtda otiladi. Telegram limiti ~30 xabar/sekund. Throttle bo'lmasa — 429 Flood,
bot qotadi, xabarlar yo'qoladi.

Yechim: barcha OMMAVIY (scheduler) xabarlar shu navbatga tushadi; bitta worker
ularni sekundiga ~RATE tadan yuboradi.
  • TelegramRetryAfter (429) — ko'rsatilgan soniya kutib, qayta uriladi.
  • TelegramForbiddenError (user bloklagan) — user bazada nofaol qilinadi.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.database import db

logger = logging.getLogger(__name__)

RATE = 25  # xabar/sekund (Telegram global limiti ~30 — ehtiyot chegara)


class Sender:
    """Global chiquvchi xabar navbati va uni bir maromda yuboruvchi worker."""

    def __init__(self, rate: int = RATE):
        self._q: asyncio.Queue = asyncio.Queue()
        self._interval = 1.0 / rate
        self._bot: Bot | None = None
        self._task: asyncio.Task | None = None

    async def start(self, bot: Bot) -> None:
        self._bot = bot
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._worker(), name="sender-worker")

    async def enqueue(self, chat_id: int, text: str, reply_markup=None,
                      on_result=None) -> None:
        """Xabarni navbatga qo'yadi (bloklamaydi — navbat cheksiz).

        on_result — ixtiyoriy callback(ok: bool). Xabar yuborilgach chaqiriladi
        (broadcast uchun yetkazilgan/yetmagan sonini aniq sanash imkonini beradi).
        """
        await self._q.put((chat_id, text, reply_markup, on_result))

    def pending(self) -> int:
        return self._q.qsize()

    async def _worker(self) -> None:
        while True:
            chat_id, text, markup, on_result = await self._q.get()
            ok = False
            try:
                ok = await self._send_one(chat_id, text, markup)
            except Exception:
                logger.exception("Sender: kutilmagan xato (chat_id=%s)", chat_id)
            finally:
                self._q.task_done()
                if on_result is not None:
                    try:
                        on_result(ok)
                    except Exception:
                        logger.exception("Sender: on_result callback xatosi")
            # Bir maromda yuborish — flood limitiga urilmaslik uchun
            await asyncio.sleep(self._interval)

    async def _send_one(self, chat_id: int, text: str, markup) -> bool:
        """True — yuborildi; False — yuborilmadi (bloklagan / xato / urinishlar tugadi)."""
        for _ in range(3):
            try:
                await self._bot.send_message(chat_id, text, reply_markup=markup)
                return True
            except TelegramRetryAfter as e:
                logger.warning("Flood limit: %s sek kutamiz (chat=%s)",
                               e.retry_after, chat_id)
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                # User botni bloklagan / chatni o'chirgan — qayta urinmaymiz
                logger.info("Bloklangan user, nofaol qilinadi: chat=%s", chat_id)
                await db.deactivate_user_by_tg(chat_id)
                return False
            except TelegramBadRequest as e:
                logger.warning("Yuborilmadi (BadRequest, chat=%s): %s", chat_id, e)
                return False
        logger.error("3 urinishdan keyin ham yuborilmadi: chat=%s", chat_id)
        return False


# Butun ilova uchun yagona sender (scheduler shundan foydalanadi)
sender = Sender()
