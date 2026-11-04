"""Odat statistikasi — streak (ketma-ketlik) va haftalik natija.

Odat = takror eslatma (daily/weekly/every2/monthly). "once" odat emas.
Streak: kutilgan kunlar bo'yicha orqaga yurib, ketma-ket 'done' kunlar soni.
Kutilmagan kunlar (masalan haftalik odatda boshqa kunlar) streakni buzmaydi.
"""
from datetime import date, timedelta

from app.scheduler.scheduler import is_today_reminder

RECURRING = {"daily", "weekly", "every2", "monthly"}


def is_habit(rem: dict) -> bool:
    return rem.get("freq") in RECURRING


def _logs_sets(logs: list[dict]) -> tuple[set, set]:
    done = {l["log_date"] for l in logs if l["status"] == "done"}
    skipped = {l["log_date"] for l in logs if l["status"] == "skipped"}
    return done, skipped


def compute_streak(rem: dict, logs: list[dict]) -> int:
    """Kutilgan kunlar bo'yicha orqaga yurib ketma-ket 'done' sonini qaytaradi.
    Bugun kutilgan, lekin hali belgilanmagan bo'lsa — streak buzilmaydi (kun tugamagan)."""
    done, skipped = _logs_sets(logs)
    today = date.today()
    streak = 0
    d = today
    for _ in range(730):  # ~2 yil chegara
        if is_today_reminder(rem, d):
            ds = d.isoformat()
            if ds in done:
                streak += 1
            elif ds in skipped:
                break
            elif d == today:
                pass  # bugun hali tugamagan — buzmaymiz
            else:
                break  # o'tmishdagi kutilgan kun belgilanmagan — streak uzildi
        d -= timedelta(days=1)
    return streak


def week_stats(rem: dict, logs: list[dict]) -> tuple[int, int]:
    """(bajarilgan, kutilgan) — so'nggi 7 kun ichida."""
    done, _ = _logs_sets(logs)
    today = date.today()
    expected = completed = 0
    for i in range(7):
        d = today - timedelta(days=i)
        if is_today_reminder(rem, d):
            expected += 1
            if d.isoformat() in done:
                completed += 1
    return completed, expected
