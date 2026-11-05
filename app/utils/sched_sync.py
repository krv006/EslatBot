"""Mini App (Django) o'zgartirgan eslatma/digestlarni APScheduler bilan sinxronlaydi.

Bot va Mini App alohida jarayonlar, bitta SQLite bazani baham ko'radi. Mini App
eslatma qo'shsa/o'chirsa/to'xtatsa yoki digest vaqtini o'zgartirsa — bazadagi
`scheduler_sync` jadvaliga "ish" yozadi. Bu poller uni o'qib, botning jonli
APScheduler jadvalini yangilaydi (broadcast poller bilan bir xil yondashuv).
"""
import asyncio
import logging

from aiogram import Bot

from app.database import db
from app.scheduler.scheduler import (
    schedule_digest,
    schedule_reminder,
    unschedule_reminder,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 4  # sekundda bir marta tekshiriladi


async def _apply_reminder(bot: Bot, reminder_id: int) -> None:
    """Eslatma holatiga qarab jadvalga qo'shadi/yangilaydi yoki olib tashlaydi."""
    rem = await db.get_reminder(reminder_id)
    if rem and rem["is_active"]:
        schedule_reminder(bot, rem)
    else:
        # o'chirilgan yoki to'xtatilgan — jadvaldan olib tashlaymiz
        unschedule_reminder(reminder_id)


async def _apply_digest(bot: Bot, user_db_id: int) -> None:
    user = await db.get_user_by_id(user_db_id)
    if user:
        schedule_digest(bot, user)  # ichida yoqilgan/o'chirilganini o'zi hal qiladi


async def _process(bot: Bot, jobs: list[dict]) -> None:
    done_ids: list[int] = []
    for job in jobs:
        try:
            if job["kind"] == "reminder":
                await _apply_reminder(bot, job["ref_id"])
            elif job["kind"] == "digest":
                await _apply_digest(bot, job["ref_id"])
            done_ids.append(job["id"])
        except Exception:
            logger.exception("Sched-sync ish #%s bajarilmadi", job.get("id"))
            done_ids.append(job["id"])  # qayta-qayta urinmaslik uchun belgilaymiz
    await db.mark_scheduler_sync_done(done_ids)


async def scheduler_sync_worker(bot: Bot) -> None:
    """Doimiy tsikl: Mini App yozgan jadval o'zgarishlarini qo'llaydi."""
    logger.info("Scheduler-sync worker ishga tushdi (interval=%ss)", POLL_INTERVAL)
    while True:
        try:
            jobs = await db.get_pending_scheduler_sync()
            if jobs:
                logger.info("Mini App'dan %d ta jadval o'zgarishi qabul qilindi",
                            len(jobs))
                await _process(bot, jobs)
                continue  # darhol keyingisini tekshiramiz
        except Exception:
            logger.exception("Scheduler-sync worker: kutilmagan xato")
        await asyncio.sleep(POLL_INTERVAL)
