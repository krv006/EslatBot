"""⚙️ Sozlamalar — ertalabki digest va kechki reja so'rovi boshqaruvi."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import BTN_SETTINGS, main_menu, settings_kb
from app.scheduler.scheduler import (
    schedule_digest,
    schedule_evening,
    unschedule_digest,
    unschedule_evening,
)
from app.utils.parser import parse_time

router = Router()


class DigestTime(StatesGroup):
    time_ = State()


class EveningTime(StatesGroup):
    time_ = State()


def _settings_text(user: dict) -> str:
    dg_on = bool(user.get("digest_enabled"))
    ev_on = bool(user.get("evening_enabled"))
    dg_h = user.get("digest_hour") if user.get("digest_hour") is not None else 7
    dg_m = user.get("digest_minute") or 0
    ev_h = user.get("evening_hour") if user.get("evening_hour") is not None else 21
    ev_m = user.get("evening_minute") or 0
    dg_status = f"✅ har kuni <b>{dg_h:02d}:{dg_m:02d}</b> da" if dg_on else "🔕 o'chirilgan"
    ev_status = f"✅ har kuni <b>{ev_h:02d}:{ev_m:02d}</b> da" if ev_on else "🔕 o'chirilgan"
    return (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"🌅 <b>Ertalabki kun rejasi</b> — {dg_status}\n"
        "<i>Har tong xayrli tong tilab, bugungi rejalaringizni yuboraman.</i>\n\n"
        f"🌙 <b>Kechki reja so'rovi</b> — {ev_status}\n"
        "<i>Har kech «ertaga uchun reja qo'shasizmi?» deb so'rayman.</i>\n\n"
        "Tugma bosib yoqing/o'chiring, vaqtini o'zgartiring 👇"
    )


async def _refresh(callback: CallbackQuery, user: dict):
    await callback.message.edit_text(
        _settings_text(user), reply_markup=settings_kb(user)
    )


@router.message(F.text == BTN_SETTINGS)
async def show_settings(message: Message, state: FSMContext):
    await state.clear()
    await db.upsert_user(message.from_user)
    user = await db.get_user(message.from_user.id)
    await message.answer(_settings_text(user), reply_markup=settings_kb(user))


# --- Ertalabki digest ---

@router.callback_query(F.data == "dg_toggle")
async def toggle_digest(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Avval /start bosing", show_alert=True)
        return
    new_state = not bool(user.get("digest_enabled"))
    await db.set_digest_enabled(callback.from_user.id, new_state)
    user["digest_enabled"] = 1 if new_state else 0
    if new_state:
        schedule_digest(callback.bot, user)
    else:
        unschedule_digest(user["id"])
    await _refresh(callback, user)
    await callback.answer("🌅 Yoqildi" if new_state else "🌅 O'chirildi")


@router.callback_query(F.data == "dg_time")
async def ask_digest_time(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DigestTime.time_)
    await callback.message.answer(
        "🌅 Ertalabki reja soat nechada kelsin?\n"
        "Masalan: <b>07:00</b> yoki <b>06:30</b>"
    )
    await callback.answer()


@router.message(DigestTime.time_, F.text)
async def got_digest_time(message: Message, state: FSMContext):
    parsed = parse_time(message.text)
    if parsed is None:
        await message.answer(
            "Vaqtni tushunmadim 😅 Shunday yozing: <b>07:00</b> yoki <b>06:30</b>"
        )
        return
    hour, minute = parsed
    await state.clear()
    await db.set_digest_time(message.from_user.id, hour, minute)
    await db.set_digest_enabled(message.from_user.id, True)
    user = await db.get_user(message.from_user.id)
    schedule_digest(message.bot, user)
    await message.answer(
        f"✅ Endi har kuni <b>{hour:02d}:{minute:02d}</b> da "
        f"kun rejangizni yuboraman! 🌅",
        reply_markup=main_menu,
    )


# --- Kechki reja so'rovi ---

@router.callback_query(F.data == "ev_toggle")
async def toggle_evening(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Avval /start bosing", show_alert=True)
        return
    new_state = not bool(user.get("evening_enabled"))
    await db.set_evening_enabled(callback.from_user.id, new_state)
    user["evening_enabled"] = 1 if new_state else 0
    if new_state:
        schedule_evening(callback.bot, user)
    else:
        unschedule_evening(user["id"])
    await _refresh(callback, user)
    await callback.answer("🌙 Yoqildi" if new_state else "🌙 O'chirildi")


@router.callback_query(F.data == "ev_time")
async def ask_evening_time(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EveningTime.time_)
    await callback.message.answer(
        "🌙 Kechki so'rov soat nechada kelsin?\n"
        "Masalan: <b>21:00</b> yoki <b>22:30</b>"
    )
    await callback.answer()


@router.message(EveningTime.time_, F.text)
async def got_evening_time(message: Message, state: FSMContext):
    parsed = parse_time(message.text)
    if parsed is None:
        await message.answer(
            "Vaqtni tushunmadim 😅 Shunday yozing: <b>21:00</b> yoki <b>22:30</b>"
        )
        return
    hour, minute = parsed
    await state.clear()
    await db.set_evening_time(message.from_user.id, hour, minute)
    await db.set_evening_enabled(message.from_user.id, True)
    user = await db.get_user(message.from_user.id)
    schedule_evening(message.bot, user)
    await message.answer(
        f"✅ Endi har kuni kechqurun <b>{hour:02d}:{minute:02d}</b> da "
        f"ertangi rejangizni so'rayman! 🌙",
        reply_markup=main_menu,
    )
