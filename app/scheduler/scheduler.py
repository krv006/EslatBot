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


# =====================================================================
# Digest — ertalabki kun rejasi
# =====================================================================

def is_today_reminder(rem: dict, today) -> bool:
    """Eslatma bugungi kunga tegishlimi?"""
    freq = rem["freq"]
    if freq == "daily":
        return True
    if freq == "weekly":
        return rem["weekday"] == today.weekday()
    if freq == "monthly":
        return rem["monthday"] == today.day
    if freq == "every2":
        if not rem["start_date"]:
            return False
        start = datetime.fromisoformat(rem["start_date"]).date()
        return today >= start and (today - start).days % 2 == 0
    return False


def build_digest_text(name: str, reminders: list[dict]) -> str:
    """Kun rejasi matnini tuzadi. Eslatmalar vaqt bo'yicha tartiblanadi."""
    now = datetime.now(TZ)
    if now.hour < 12:
        greeting = "☀️ Xayrli tong"
    elif now.hour < 18:
        greeting = "🌤 Xayrli kun"
    else:
        greeting = "🌙 Xayrli kech"

    count = len(reminders)
    lines = [f"{greeting}, <b>{name}</b>!\n"]
    lines.append(f"Bugun sizda <b>{count} ta</b> reja bor:\n")
    for rem in sorted(reminders, key=lambda r: (r["hour"], r["minute"])):
        lines.append(f"🕒 <b>{rem['hour']:02d}:{rem['minute']:02d}</b> — {rem['text']}")
    lines.append("\nHar birini o'z vaqtida alohida eslataman! 💪")
    return "\n".join(lines)


async def send_digest(bot: Bot, user_db_id: int) -> None:
    """Bitta foydalanuvchiga bugungi kun rejasini yuboradi.

    Bugunga reja bo'lmasa — indamaydi (bekorga bezovta qilmaslik uchun).
    """
    user = await db.get_user_by_id(user_db_id)
    if not user or not user.get("digest_enabled"):
        return
    reminders = await db.get_active_reminders_for_user(user_db_id)
    today = datetime.now(TZ).date()
    todays = [r for r in reminders if is_today_reminder(r, today)]
    if not todays:
        return
    try:
        await bot.send_message(
            user["tg_id"],
            build_digest_text(user.get("name") or "do'stim", todays),
        )
    except Exception:
        logger.exception("Digest yuborilmadi: user_db_id=%s", user_db_id)


def schedule_digest(bot: Bot, user: dict) -> None:
    """Foydalanuvchining shaxsiy digest vaqtiga cron qo'yadi (idempotent)."""
    if not user.get("digest_enabled"):
        unschedule_digest(user["id"])
        return
    hour = user.get("digest_hour")
    minute = user.get("digest_minute")
    scheduler.add_job(
        send_digest,
        CronTrigger(hour=7 if hour is None else hour,
                    minute=0 if minute is None else minute,
                    timezone=TZ),
        args=[bot, user["id"]],
        id=f"digest_{user['id']}",
        replace_existing=True,
        misfire_grace_time=3600,
    )


def unschedule_digest(user_db_id: int) -> None:
    job = scheduler.get_job(f"digest_{user_db_id}")
    if job:
        job.remove()


async def load_all_digests(bot: Bot) -> int:
    """Bot qayta ishga tushganda barcha digestlarni jadvalga qaytaradi."""
    users = await db.get_users_for_digest()
    for user in users:
        schedule_digest(bot, user)
    logger.info("%d ta digest jadvalga yuklandi", len(users))
    return len(users)
