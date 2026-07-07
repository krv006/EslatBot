"""APScheduler — eslatmalarni belgilangan vaqtda yuborish."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import TIMEZONE
from app.database import db
from app.keyboards.keyboards import reminder_fired_kb

logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)
scheduler = AsyncIOScheduler(timezone=TZ)


def _job_id(reminder_id: int) -> str:
    return f"rem_{reminder_id}"


async def send_reminder(bot: Bot, reminder_id: int) -> None:
    rem = await db.get_reminder(reminder_id)
    if not rem or not rem["is_active"]:
        return
    try:
        await bot.send_message(
            rem["tg_id"],
            f"🔔 <b>Eslatma!</b>\n\n{rem['text']}",
            reply_markup=reminder_fired_kb(reminder_id),
        )
    except Exception:
        logger.exception("Eslatma yuborilmadi: id=%s", reminder_id)


def first_run_date(hour: int, minute: int) -> datetime:
    """'Kun ora' uchun birinchi yuborish vaqti: bugun (agar hali kelmagan bo'lsa) yoki ertaga."""
    now = datetime.now(TZ)
    first = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if first <= now:
        first += timedelta(days=1)
    return first


def schedule_reminder(bot: Bot, rem: dict) -> None:
    """Bitta eslatmani jadvalga qo'shadi (bor bo'lsa yangilaydi)."""
    freq = rem["freq"]
    if freq == "daily":
        trigger = CronTrigger(hour=rem["hour"], minute=rem["minute"], timezone=TZ)
    elif freq == "every2":
        start = datetime.fromisoformat(rem["start_date"])
        trigger = IntervalTrigger(days=2, start_date=start, timezone=TZ)
    elif freq == "weekly":
        trigger = CronTrigger(
            day_of_week=rem["weekday"], hour=rem["hour"], minute=rem["minute"], timezone=TZ
        )
    elif freq == "monthly":
        trigger = CronTrigger(
            day=rem["monthday"], hour=rem["hour"], minute=rem["minute"], timezone=TZ
        )
    else:
        logger.error("Noma'lum freq: %s", freq)
        return

    scheduler.add_job(
        send_reminder,
        trigger,
        args=[bot, rem["id"]],
        id=_job_id(rem["id"]),
        replace_existing=True,
        misfire_grace_time=3600,
    )


def unschedule_reminder(reminder_id: int) -> None:
    job = scheduler.get_job(_job_id(reminder_id))
    if job:
        job.remove()


def schedule_snooze(bot: Bot, reminder_id: int, minutes: int = 10) -> None:
    """Bir martalik "keyinroq eslat" (snooze)."""
    scheduler.add_job(
        send_reminder,
        "date",
        run_date=datetime.now(TZ) + timedelta(minutes=minutes),
        args=[bot, reminder_id],
    )


async def load_all_reminders(bot: Bot) -> int:
    """Bot qayta ishga tushganda bazadagi barcha faol eslatmalarni jadvalga qaytaradi."""
    reminders = await db.get_all_active_reminders()
    for rem in reminders:
        schedule_reminder(bot, rem)
    logger.info("%d ta eslatma jadvalga yuklandi", len(reminders))
    return len(reminders)
