"""Mini App backend — JSON API + bitta sahifali ilova (SPA) qobig'i.

Har bir API so'rovi `require_tma` bilan himoyalangan: Telegram initData imzosi
tekshiriladi, foydalanuvchi aniqlanadi. Hamma yozuv faqat o'sha foydalanuvchining
ma'lumotlariga tegishli bo'ladi (begona ma'lumotga kirib bo'lmaydi).
"""
import json

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from panel.models import (
    HabitLog,
    Material,
    Note,
    Reminder,
    Task,
)

from .auth import require_tma
from .logic import compute_start_date, compute_streak, is_habit, now_local

# --- Yorliqlar (model choices bilan mos) ---
FREQ_LABELS = {
    "once": "📌 Bir marta", "daily": "📅 Har kuni", "every2": "🔁 Kun ora",
    "weekly": "📆 Haftada bir", "monthly": "🗓 Oyda bir",
}
PRIORITY_LABELS = {"high": "🔴 Yuqori", "normal": "🟡 O'rta", "low": "⚪ Past"}
MTYPE_LABELS = {
    "book": "📖 Kitob", "course": "🎓 Kurs", "quran": "☪️ Qur'on", "other": "📄 Boshqa",
}
MSTATUS_LABELS = {"active": "🟢 Faol", "paused": "⏸ Pauzada", "done": "✅ Yakunlangan"}
WEEKDAY_NAMES = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba",
                 "Juma", "Shanba", "Yakshanba"]


# =====================================================================
# Yordamchilar
# =====================================================================
def _body(request) -> dict:
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return {}


def _enqueue_sync(kind: str, ref_id: int) -> None:
    """Bot jarayoniga 'jadvalni yangila' ishini yozadi (scheduler_sync)."""
    with connection.cursor() as c:
        c.execute(
            "INSERT INTO scheduler_sync (kind, ref_id, processed, created_at) "
            "VALUES (%s, %s, 0, %s)",
            [kind, ref_id, now_local().replace(tzinfo=None).isoformat()],
        )


def _clamp(v, lo, hi, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


# =====================================================================
# Serializatsiya
# =====================================================================
def reminder_dict(r: Reminder, streak=None) -> dict:
    return {
        "id": r.id,
        "text": r.text,
        "freq": r.freq,
        "freq_label": FREQ_LABELS.get(r.freq, r.freq),
        "weekday": r.weekday,
        "weekday_label": WEEKDAY_NAMES[r.weekday] if r.weekday is not None else None,
        "monthday": r.monthday,
        "hour": r.hour,
        "minute": r.minute,
        "time": f"{r.hour:02d}:{r.minute:02d}",
        "is_active": bool(r.is_active),
        "is_habit": is_habit(r.freq),
        "streak": streak,
    }


def task_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "priority": t.priority,
        "priority_label": PRIORITY_LABELS.get(t.priority, t.priority),
        "due_date": t.due_date,
        "is_done": bool(t.is_done),
    }


def note_dict(n: Note) -> dict:
    return {
        "id": n.id,
        "text": n.text,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def material_dict(m: Material) -> dict:
    percent = None
    if m.total:
        percent = min(100, round((m.current or 0) * 100 / m.total))
    return {
        "id": m.id,
        "title": m.title,
        "mtype": m.mtype,
        "mtype_label": MTYPE_LABELS.get(m.mtype, m.mtype),
        "unit": m.unit,
        "total": m.total,
        "current": m.current or 0,
        "status": m.status,
        "status_label": MSTATUS_LABELS.get(m.status, m.status),
        "percent": percent,
    }


def _habit_streaks(reminders) -> dict:
    """{reminder_id: streak} — faqat odat (takror) eslatmalar uchun."""
    habit_ids = [r.id for r in reminders if is_habit(r.freq)]
    if not habit_ids:
        return {}
    logs = HabitLog.objects.filter(reminder_id__in=habit_ids).values(
        "reminder_id", "log_date", "status")
    by_rem: dict[int, tuple[set, set]] = {i: (set(), set()) for i in habit_ids}
    for lg in logs:
        done, skipped = by_rem[lg["reminder_id"]]
        (done if lg["status"] == "done" else skipped).add(lg["log_date"])
    out = {}
    for r in reminders:
        if is_habit(r.freq):
            done, skipped = by_rem[r.id]
            out[r.id] = compute_streak(
                r.freq, r.weekday, r.monthday, r.start_date, done, skipped)
    return out


# =====================================================================
# Sahifa (SPA)
# =====================================================================
def index(request):
    return render(request, "webapp/index.html")


# =====================================================================
# Bootstrap — bosh sahifa uchun hammasi bitta so'rovda
# =====================================================================
@csrf_exempt
@require_tma
@require_http_methods(["GET"])
def bootstrap(request):
    u = request.bot_user
    reminders = list(Reminder.objects.filter(user=u))
    today = now_local().date()

    from .logic import is_day_reminder
    todays = [
        r for r in reminders
        if r.is_active and is_day_reminder(
            r.freq, r.weekday, r.monthday, r.start_date, today)
    ]
    todays.sort(key=lambda r: (r.hour, r.minute))

    tasks_open = Task.objects.filter(user=u, is_done=False).count()
    materials_active = Material.objects.filter(user=u, status="active").count()
    habits_today = HabitLog.objects.filter(
        reminder__user=u, log_date=today.isoformat(), status="done").count()

    return JsonResponse({
        "ok": True,
        "user": {
            "name": u.name or request.tg_user.get("first_name") or "do'stim",
            "username": u.username,
        },
        "settings": {
            "digest_enabled": bool(u.digest_enabled),
            "digest_hour": u.digest_hour if u.digest_hour is not None else 7,
            "digest_minute": u.digest_minute or 0,
        },
        "counts": {
            "reminders_active": sum(1 for r in reminders if r.is_active),
            "reminders_total": len(reminders),
            "today": len(todays),
            "tasks_open": tasks_open,
            "materials_active": materials_active,
            "habits_today": habits_today,
        },
        "today_plan": [reminder_dict(r) for r in todays],
    })


# =====================================================================
# Eslatmalar
# =====================================================================
@csrf_exempt
@require_tma
@require_http_methods(["GET", "POST"])
def reminders(request):
    u = request.bot_user
    if request.method == "GET":
        items = list(Reminder.objects.filter(user=u).order_by(
            "-is_active", "hour", "minute"))
        streaks = _habit_streaks(items)
        return JsonResponse({
            "ok": True,
            "items": [reminder_dict(r, streaks.get(r.id)) for r in items],
        })

    # POST — yangi eslatma
    d = _body(request)
    text = (d.get("text") or "").strip()
    freq = d.get("freq")
    if not text:
        return JsonResponse({"ok": False, "error": "Matn bo'sh."}, status=400)
    if freq not in FREQ_LABELS:
        return JsonResponse({"ok": False, "error": "Takror turi noto'g'ri."}, status=400)
    hour = _clamp(d.get("hour"), 0, 23, None)
    minute = _clamp(d.get("minute"), 0, 59, None)
    if hour is None or minute is None:
        return JsonResponse({"ok": False, "error": "Vaqt noto'g'ri."}, status=400)

    weekday = monthday = None
    if freq == "weekly":
        weekday = _clamp(d.get("weekday"), 0, 6, None)
        if weekday is None:
            return JsonResponse({"ok": False, "error": "Hafta kunini tanlang."}, status=400)
    if freq == "monthly":
        monthday = _clamp(d.get("monthday"), 1, 31, None)
        if monthday is None:
            return JsonResponse({"ok": False, "error": "Oy kunini tanlang."}, status=400)

    start_date = compute_start_date(
        freq, hour, minute,
        once_date=d.get("once_date"),
        once_weekday=_clamp(d.get("weekday"), 0, 6, None) if freq == "once" else None,
    )

    r = Reminder.objects.create(
        user=u, text=text[:1000], freq=freq, weekday=weekday, monthday=monthday,
        hour=hour, minute=minute, start_date=start_date, is_active=True,
        created_at=now_local().replace(tzinfo=None),
    )
    _enqueue_sync("reminder", r.id)
    return JsonResponse({"ok": True, "item": reminder_dict(r)})


@csrf_exempt
@require_tma
@require_http_methods(["POST", "DELETE"])
def reminder_detail(request, pk: int):
    u = request.bot_user
    r = Reminder.objects.filter(user=u, pk=pk).first()
    if not r:
        return JsonResponse({"ok": False, "error": "Topilmadi."}, status=404)

    if request.method == "DELETE":
        rid = r.id
        HabitLog.objects.filter(reminder_id=rid).delete()
        r.delete()
        _enqueue_sync("reminder", rid)  # bot jadvaldan o'chiradi
        return JsonResponse({"ok": True})

    # POST — toggle faol/to'xtatilgan
    action = _body(request).get("action")
    if action == "toggle":
        r.is_active = not r.is_active
        r.save(update_fields=["is_active"])
        _enqueue_sync("reminder", r.id)
        return JsonResponse({"ok": True, "item": reminder_dict(r)})
    return JsonResponse({"ok": False, "error": "Noma'lum amal."}, status=400)


# =====================================================================
# Vazifalar
# =====================================================================
@csrf_exempt
@require_tma
@require_http_methods(["GET", "POST"])
def tasks(request):
    u = request.bot_user
    if request.method == "GET":
        flt = request.GET.get("filter", "open")
        qs = Task.objects.filter(user=u)
        if flt == "open":
            qs = qs.filter(is_done=False)
        elif flt == "done":
            qs = qs.filter(is_done=True)
        qs = qs.order_by("is_done", "due_date", "-id")
        return JsonResponse({"ok": True, "items": [task_dict(t) for t in qs]})

    d = _body(request)
    title = (d.get("title") or "").strip()
    if not title:
        return JsonResponse({"ok": False, "error": "Vazifa matni bo'sh."}, status=400)
    priority = d.get("priority") if d.get("priority") in PRIORITY_LABELS else "normal"
    due_date = (d.get("due_date") or "").strip() or None
    t = Task.objects.create(
        user=u, title=title[:500], priority=priority, due_date=due_date,
        is_done=False, created_at=now_local().replace(tzinfo=None),
    )
    return JsonResponse({"ok": True, "item": task_dict(t)})


@csrf_exempt
@require_tma
@require_http_methods(["POST", "DELETE"])
def task_detail(request, pk: int):
    u = request.bot_user
    t = Task.objects.filter(user=u, pk=pk).first()
    if not t:
        return JsonResponse({"ok": False, "error": "Topilmadi."}, status=404)
    if request.method == "DELETE":
        t.delete()
        return JsonResponse({"ok": True})

    d = _body(request)
    action = d.get("action")
    if action == "toggle":
        t.is_done = not t.is_done
        t.done_at = now_local().replace(tzinfo=None) if t.is_done else None
        t.save(update_fields=["is_done", "done_at"])
        return JsonResponse({"ok": True, "item": task_dict(t)})
    if action == "update":
        if d.get("priority") in PRIORITY_LABELS:
            t.priority = d["priority"]
        if "due_date" in d:
            t.due_date = (d.get("due_date") or "").strip() or None
        if (d.get("title") or "").strip():
            t.title = d["title"].strip()[:500]
        t.save()
        return JsonResponse({"ok": True, "item": task_dict(t)})
    return JsonResponse({"ok": False, "error": "Noma'lum amal."}, status=400)


# =====================================================================
# Qaydlar
# =====================================================================
@csrf_exempt
@require_tma
@require_http_methods(["GET", "POST"])
def notes(request):
    u = request.bot_user
    if request.method == "GET":
        qs = Note.objects.filter(user=u)
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(text__icontains=q)
        qs = qs.order_by("-id")
        return JsonResponse({"ok": True, "items": [note_dict(n) for n in qs]})

    text = (_body(request).get("text") or "").strip()
    if not text:
        return JsonResponse({"ok": False, "error": "Qayd bo'sh."}, status=400)
    n = Note.objects.create(
        user=u, text=text[:4000], created_at=now_local().replace(tzinfo=None))
    return JsonResponse({"ok": True, "item": note_dict(n)})


@csrf_exempt
@require_tma
@require_http_methods(["DELETE"])
def note_detail(request, pk: int):
    n = Note.objects.filter(user=request.bot_user, pk=pk).first()
    if not n:
        return JsonResponse({"ok": False, "error": "Topilmadi."}, status=404)
    n.delete()
    return JsonResponse({"ok": True})


# =====================================================================
# Materiallar
# =====================================================================
@csrf_exempt
@require_tma
@require_http_methods(["GET", "POST"])
def materials(request):
    u = request.bot_user
    if request.method == "GET":
        order = {"active": 0, "paused": 1, "done": 2}
        items = sorted(
            Material.objects.filter(user=u),
            key=lambda m: (order.get(m.status, 3), -m.id))
        return JsonResponse({"ok": True, "items": [material_dict(m) for m in items]})

    d = _body(request)
    title = (d.get("title") or "").strip()
    if not title:
        return JsonResponse({"ok": False, "error": "Nomi bo'sh."}, status=400)
    mtype = d.get("mtype") if d.get("mtype") in MTYPE_LABELS else "book"
    total = _clamp(d.get("total"), 1, 10_000_000, None) if d.get("total") else None
    m = Material.objects.create(
        user=u, title=title[:500], mtype=mtype, unit=(d.get("unit") or "").strip() or None,
        total=total, current=0, status="active",
        created_at=now_local().replace(tzinfo=None),
    )
    return JsonResponse({"ok": True, "item": material_dict(m)})


@csrf_exempt
@require_tma
@require_http_methods(["POST", "DELETE"])
def material_detail(request, pk: int):
    u = request.bot_user
    m = Material.objects.filter(user=u, pk=pk).first()
    if not m:
        return JsonResponse({"ok": False, "error": "Topilmadi."}, status=404)
    if request.method == "DELETE":
        m.delete()
        return JsonResponse({"ok": True})

    d = _body(request)
    if "current" in d:
        m.current = _clamp(d.get("current"), 0, 1_000_000_000, m.current or 0)
    if "total" in d:
        m.total = _clamp(d.get("total"), 1, 1_000_000_000, None) if d.get("total") else None
    if d.get("status") in MSTATUS_LABELS:
        m.status = d["status"]
    if (d.get("title") or "").strip():
        m.title = d["title"].strip()[:500]
    if d.get("mtype") in MTYPE_LABELS:
        m.mtype = d["mtype"]
    m.save()
    return JsonResponse({"ok": True, "item": material_dict(m)})


# =====================================================================
# Sozlamalar (ertalabki digest)
# =====================================================================
@csrf_exempt
@require_tma
@require_http_methods(["POST"])
def settings_view(request):
    u = request.bot_user
    d = _body(request)
    if "digest_enabled" in d:
        u.digest_enabled = bool(d["digest_enabled"])
    if "digest_hour" in d:
        u.digest_hour = _clamp(d.get("digest_hour"), 0, 23, u.digest_hour or 7)
    if "digest_minute" in d:
        u.digest_minute = _clamp(d.get("digest_minute"), 0, 59, u.digest_minute or 0)
    u.save(update_fields=["digest_enabled", "digest_hour", "digest_minute"])
    _enqueue_sync("digest", u.id)
    return JsonResponse({"ok": True, "settings": {
        "digest_enabled": bool(u.digest_enabled),
        "digest_hour": u.digest_hour if u.digest_hour is not None else 7,
        "digest_minute": u.digest_minute or 0,
    }})
