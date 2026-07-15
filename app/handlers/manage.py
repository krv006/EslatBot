"""Eslatmalar ro'yxati: ko'rish, to'xtatish/yoqish, o'chirish, bajarildi/snooze."""
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import BTN_LIST, reminder_manage_kb
from app.scheduler.scheduler import (
    TZ,
    schedule_reminder,
    schedule_snooze,
    schedule_snooze_at,
    unschedule_reminder,
)
from app.utils.fmt import esc
from app.utils.parser import describe

router = Router()


def _format_line(rem: dict) -> str:
    status = "🟢" if rem["is_active"] else "⏸"
    when = describe(rem["freq"], rem["weekday"], rem["monthday"],
                    rem["hour"], rem["minute"], start_date=rem["start_date"])
    return f"{status} <b>{esc(rem['text'])}</b>\n🕒 {when}"


@router.message(F.text == BTN_LIST)
async def list_reminders(message: Message):
    reminders = await db.get_user_reminders(message.from_user.id)
    if not reminders:
        await message.answer(
            "Sizda hali eslatmalar yo'q. 🤷\n"
            "<b>➕ Yangi eslatma</b> tugmasini bosing yoki shunchaki yozing:\n"
            "<i>«har kuni 8 da dori ichishni eslat»</i>"
        )
        return
    await message.answer(f"📋 Sizning eslatmalaringiz ({len(reminders)} ta):")
    for rem in reminders:
        await message.answer(
            _format_line(rem),
            reply_markup=reminder_manage_kb(rem["id"], bool(rem["is_active"])),
        )


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_reminder(callback: CallbackQuery):
    _, rid, active = callback.data.split(":")
    rid, active = int(rid), active == "1"
    await db.set_reminder_active(rid, active)
    rem = await db.get_reminder(rid)
    if not rem:
        await callback.answer("Eslatma topilmadi", show_alert=True)
        return
    if active:
        schedule_reminder(callback.bot, rem)
    else:
        unschedule_reminder(rid)
    await callback.message.edit_text(
        _format_line(rem),
        reply_markup=reminder_manage_kb(rid, active),
    )
    await callback.answer("▶️ Yoqildi" if active else "⏸ To'xtatildi")


@router.callback_query(F.data.startswith("del:"))
async def del_reminder(callback: CallbackQuery):
    rid = int(callback.data.split(":")[1])
    unschedule_reminder(rid)
    await db.delete_reminder(rid)
    await callback.message.edit_text("🗑 Eslatma o'chirildi.")
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def done_reminder(callback: CallbackQuery):
    await callback.message.edit_text(
        callback.message.html_text + "\n\n✅ <i>Bajarildi!</i>"
    )
    await callback.answer("Barakalla! 💪")


_SNOOZE_LABELS = {10: "10 daqiqa", 30: "30 daqiqa", 60: "1 soat"}


@router.callback_query(F.data.startswith("snz:"))
async def snooze_flexible(callback: CallbackQuery):
    _, rid, val = callback.data.split(":")
    rid = int(rid)
    rem = await db.get_reminder(rid)
    # Bir martalik eslatma yuborilgach o'chadi — snooze uchun qayta yoqamiz
    if rem and rem["freq"] == "once" and not rem["is_active"]:
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
    rem = await db.get_reminder(rid)
    if rem and rem["freq"] == "once" and not rem["is_active"]:
        await db.set_reminder_active(rid, True)
    schedule_snooze(callback.bot, rid, minutes=10)
    await callback.message.edit_text(
        callback.message.html_text + "\n\n⏰ <i>10 daqiqadan keyin yana eslataman.</i>"
    )
    await callback.answer("10 daqiqaga qoldirildi")
