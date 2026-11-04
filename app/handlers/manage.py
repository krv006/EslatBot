"""Eslatmalar ro'yxati: ko'rish, to'xtatish/yoqish, o'chirish, bajarildi/snooze."""
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.database import db
from app.keyboards.keyboards import (
    BTN_LIST,
    reminder_manage_kb,
    reminders_list_kb,
)
from app.scheduler.scheduler import (
    TZ,
    schedule_reminder,
    schedule_snooze,
    schedule_snooze_at,
    unschedule_reminder,
)
from app.utils.fmt import esc
from app.utils.guards import get_owned_reminder
from app.utils.habits import compute_streak, is_habit, week_stats
from app.utils.parser import describe

router = Router()


async def _detail_text(rem: dict) -> str:
    """Eslatma tafsiloti. Odat (takror) bo'lsa — streak va haftalik natija qo'shiladi."""
    base = _format_line(rem)
    if not is_habit(rem):
        return base
    logs = await db.get_habit_logs(rem["id"])
    streak = compute_streak(rem, logs)
    done, expected = week_stats(rem, logs)
    fire = f"🔥 Ketma-ket: <b>{streak}</b> kun" if streak else "🔥 Ketma-ketlik: hali yo'q"
    return f"{base}\n\n{fire}\n📅 So'nggi 7 kun: <b>{done}/{expected}</b> bajarildi"


def _format_line(rem: dict) -> str:
    status = "🟢" if rem["is_active"] else "⏸"
    when = describe(rem["freq"], rem["weekday"], rem["monthday"],
                    rem["hour"], rem["minute"], start_date=rem["start_date"])
    return f"{status} <b>{esc(rem['text'])}</b>\n🕒 {when}"


def _list_text(reminders: list[dict]) -> str:
    active = sum(1 for r in reminders if r["is_active"])
    return (
        f"📋 <b>Sizning eslatmalaringiz</b> — {len(reminders)} ta "
        f"(🟢 {active} faol)\n\n"
        "Batafsil ko'rish yoki boshqarish uchun eslatmani tanlang 👇"
    )


@router.message(Command("list"))
@router.message(F.text == BTN_LIST)
async def list_reminders(message: Message, state: FSMContext):
    # Boshqa oqim (masalan referal) chala qolgan bo'lsa — tozalaymiz, aks holda
    # keyingi yozilgan matnni o'sha oqim "o'g'irlab" ketadi
    await state.clear()
    reminders = await db.get_user_reminders(message.from_user.id)
    if not reminders:
        await message.answer(
            "Sizda hali eslatmalar yo'q. 🤷\n"
            "<b>➕ Yangi eslatma</b> tugmasini bosing yoki shunchaki yozing:\n"
            "<i>«har kuni 8 da dori ichishni eslat»</i>"
        )
        return
    # Hammasini bitta xabarda — chat to'lib ketmasin
    await message.answer(
        _list_text(reminders),
        reply_markup=reminders_list_kb(reminders),
    )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("rlist:"))
async def list_page(callback: CallbackQuery):
    """Ro'yxatga qaytish / sahifalar orasida yurish — o'sha xabarni yangilaydi."""
    page = int(callback.data.split(":")[1])
    reminders = await db.get_user_reminders(callback.from_user.id)
    if not reminders:
        await callback.message.edit_text("Sizda eslatmalar qolmadi. 🤷")
        await callback.answer()
        return
    try:
        await callback.message.edit_text(
            _list_text(reminders),
            reply_markup=reminders_list_kb(reminders, page),
        )
    except TelegramBadRequest:
        pass  # "message is not modified" — allaqachon shu sahifada
    await callback.answer()


@router.callback_query(F.data.startswith("rshow:"))
async def show_reminder(callback: CallbackQuery):
    """Ro'yxatdan bitta eslatma tanlandi — o'sha xabarda tafsilotni ochamiz."""
    rid = int(callback.data.split(":")[1])
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return
    await callback.message.edit_text(
        await _detail_text(rem),
        reply_markup=reminder_manage_kb(rid, bool(rem["is_active"]), is_habit(rem)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_reminder(callback: CallbackQuery):
    _, rid, active = callback.data.split(":")
    rid, active = int(rid), active == "1"
    # Avval egalikni tekshiramiz — keyin o'zgartiramiz
    if not await get_owned_reminder(callback, rid):
        return
    await db.set_reminder_active(rid, active)
    rem = await db.get_reminder(rid)
    if active:
        schedule_reminder(callback.bot, rem)
    else:
        unschedule_reminder(rid)
    await callback.message.edit_text(
        await _detail_text(rem),
        reply_markup=reminder_manage_kb(rid, active, is_habit(rem)),
    )
    await callback.answer("▶️ Yoqildi" if active else "⏸ To'xtatildi")


@router.callback_query(F.data.startswith("del:"))
async def del_reminder(callback: CallbackQuery):
    rid = int(callback.data.split(":")[1])
    if not await get_owned_reminder(callback, rid):
        return
    unschedule_reminder(rid)
    await db.delete_reminder(rid)
    reminders = await db.get_user_reminders(callback.from_user.id)
    if reminders:
        # O'chgach ro'yxatga qaytamiz — foydalanuvchi qolganini ko'radi
        await callback.message.edit_text(
            _list_text(reminders),
            reply_markup=reminders_list_kb(reminders),
        )
    else:
        await callback.message.edit_text("🗑 O'chirildi. Sizda boshqa eslatma yo'q.")
    await callback.answer("🗑 O'chirildi")


@router.callback_query(F.data.startswith("done:"))
async def done_reminder(callback: CallbackQuery):
    rid = int(callback.data.split(":")[1])
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return
    note, toast = "✅ <i>Bajarildi!</i>", "Barakalla! 💪"
    # Takror odat bo'lsa — bugungi natijani yozamiz va streakni ko'rsatamiz
    if is_habit(rem):
        await db.log_habit(rid, "done")
        streak = compute_streak(rem, await db.get_habit_logs(rid))
        if streak >= 2:
            note = f"✅ <i>Bajarildi! 🔥 {streak} kun ketma-ket!</i>"
            toast = f"🔥 {streak} kun ketma-ket!"
    await callback.message.edit_text(callback.message.html_text + f"\n\n{note}")
    await callback.answer(toast)


@router.callback_query(F.data.startswith("skip:"))
async def skip_habit(callback: CallbackQuery):
    """Takror odatni bugun ongli ravishda o'tkazib yuborish."""
    rid = int(callback.data.split(":")[1])
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return
    await db.log_habit(rid, "skipped")
    await callback.message.edit_text(
        callback.message.html_text + "\n\n⏭ <i>Bugun o'tkazib yuborildi.</i>")
    await callback.answer("Bugun o'tkazildi")


@router.callback_query(F.data.startswith("hstat:"))
async def habit_stats(callback: CallbackQuery):
    """Odat statistikasi: streak, haftalik natija, so'nggi kunlar jadvali."""
    rid = int(callback.data.split(":")[1])
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return
    logs = await db.get_habit_logs(rid)
    done_set = {l["log_date"] for l in logs if l["status"] == "done"}
    skip_set = {l["log_date"] for l in logs if l["status"] == "skipped"}
    streak = compute_streak(rem, logs)
    done7, exp7 = week_stats(rem, logs)
    total_done = len(done_set)

    # So'nggi kutilgan ~14 kun jadvali (eski -> yangi): ✅ bajarildi, ⏭ o'tkazildi,
    # ❌ qoldirilgan, ⬜ bugun (hali belgilanmagan)
    from datetime import date
    from app.utils.habits import is_today_reminder
    today = date.today()
    marks, d, steps = [], today, 0
    while len(marks) < 14 and steps < 200:
        if is_today_reminder(rem, d):
            ds = d.isoformat()
            if ds in done_set:
                marks.append("✅")
            elif ds in skip_set:
                marks.append("⏭")
            elif d == today:
                marks.append("⬜")
            else:
                marks.append("❌")
        d -= timedelta(days=1)
        steps += 1
    grid = "".join(reversed(marks)) or "— hali natija yo'q"

    fire = f"🔥 Ketma-ket: <b>{streak}</b> kun" if streak else "🔥 Ketma-ketlik: hali yo'q"
    text = (
        f"📊 <b>Statistika</b>\n{_format_line(rem)}\n\n"
        f"{fire}\n"
        f"📅 So'nggi 7 kun: <b>{done7}/{exp7}</b>\n"
        f"🏆 Jami bajarilgan: <b>{total_done}</b> marta\n\n"
        f"So'nggi kunlar (eskidan yangiga):\n{grid}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"rshow:{rid}")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer()


_SNOOZE_LABELS = {10: "10 daqiqa", 30: "30 daqiqa", 60: "1 soat"}


@router.callback_query(F.data.startswith("snz:"))
async def snooze_flexible(callback: CallbackQuery):
    _, rid, val = callback.data.split(":")
    rid = int(rid)
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return
    # Bir martalik eslatma yuborilgach o'chadi — snooze uchun qayta yoqamiz
    if rem["freq"] == "once" and not rem["is_active"]:
        await db.set_reminder_active(rid, True)

    if val == "tomorrow":
        h = rem["hour"] if rem else 9
        m = rem["minute"] if rem else 0
        run = (datetime.now(TZ) + timedelta(days=1)).replace(
            hour=h, minute=m, second=0, microsecond=0
        )
        schedule_snooze_at(callback.bot, rid, run)
        note = f"🌅 Ertaga soat {h:02d}:{m:02d} da yana eslataman."
        toast = "Ertaga eslataman 🌅"
    else:
        minutes = int(val)
        schedule_snooze(callback.bot, rid, minutes=minutes)
        label = _SNOOZE_LABELS.get(minutes, f"{minutes} daqiqa")
        note = f"⏰ {label}dan keyin yana eslataman."
        toast = f"{label}ga qoldirildi"

    await callback.message.edit_text(callback.message.html_text + f"\n\n<i>{note}</i>")
    await callback.answer(toast)


@router.callback_query(F.data.startswith("snooze:"))
async def snooze_reminder(callback: CallbackQuery):
    """Eski (deploydan oldin yuborilgan) xabarlardagi "+10 daqiqa" tugmasi uchun."""
    rid = int(callback.data.split(":")[1])
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return
    if rem["freq"] == "once" and not rem["is_active"]:
        await db.set_reminder_active(rid, True)
    schedule_snooze(callback.bot, rid, minutes=10)
    await callback.message.edit_text(
        callback.message.html_text + "\n\n⏰ <i>10 daqiqadan keyin yana eslataman.</i>"
    )
    await callback.answer("10 daqiqaga qoldirildi")
