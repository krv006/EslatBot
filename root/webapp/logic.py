"""Mini App uchun mustaqil yordamchi mantiq (botning `app` paketiga bog'liq emas).

Django jarayoni botning kodini import qilmaydi, shuning uchun bu yerda:
  • eslatma bugungi kungami (digest/streak uchun),
  • streak (odat ketma-ketligi),
  • yangi eslatma uchun start_date hisoblash —
botdagi mantiqning aynan nusxasi (bir xil natija berishi uchun).
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings

TZ = ZoneInfo(settings.TIME_ZONE)
RECURRING = {"daily", "weekly", "every2", "monthly"}


def now_local() -> datetime:
    return datetime.now(TZ)


def is_habit(freq: str) -> bool:
    return freq in RECURRING


def is_day_reminder(freq, weekday, monthday, start_date, day: date) -> bool:
    """Eslatma `day` kuniga tegishlimi? (botdagi is_today_reminder bilan bir xil)."""
    if freq == "once":
        if not start_date:
            return False
        return datetime.fromisoformat(start_date).date() == day
    if freq == "daily":
        return True
    if freq == "weekly":
        return weekday == day.weekday()
    if freq == "monthly":
        return monthday == day.day
    if freq == "every2":
        if not start_date:
            return False
        start = datetime.fromisoformat(start_date).date()
        return day >= start and (day - start).days % 2 == 0
    return False


def compute_streak(freq, weekday, monthday, start_date,
                   done: set, skipped: set) -> int:
    """Kutilgan kunlar bo'yicha orqaga yurib ketma-ket 'done' sonini qaytaradi."""
    today = now_local().date()
    streak = 0
    d = today
    for _ in range(730):
        if is_day_reminder(freq, weekday, monthday, start_date, d):
            ds = d.isoformat()
            if ds in done:
                streak += 1
            elif ds in skipped:
                break
            elif d == today:
                pass  # bugun hali tugamagan
            else:
                break
        d -= timedelta(days=1)
    return streak


def compute_start_date(freq, hour, minute, once_date=None,
                       once_weekday=None) -> str | None:
    """Yangi eslatma uchun start_date (ISO). Botdagi hisoblash bilan mos."""
    now = now_local()
    if freq == "once":
        if once_date:
            d = datetime.fromisoformat(once_date)
            return d.replace(hour=hour, minute=minute, second=0,
                             microsecond=0, tzinfo=TZ).isoformat()
        if once_weekday is not None:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = (once_weekday - now.weekday()) % 7
            if days_ahead == 0 and target <= now:
                days_ahead = 7
            return (target + timedelta(days=days_ahead)).isoformat()
        first = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if first <= now:
            first += timedelta(days=1)
        return first.isoformat()
    if freq == "every2":
        first = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if first <= now:
            first += timedelta(days=1)
        return first.isoformat()
    # daily / weekly / monthly — start_date kerak emas
    return None
