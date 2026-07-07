"""Yangi eslatma yaratish oqimi (FSM) + erkin matnni avtomatik tushunish."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import BTN_NEW, freq_kb, main_menu, weekday_kb
from app.scheduler.scheduler import first_run_date, schedule_reminder
from app.utils.parser import describe, parse_text, parse_time

router = Router()


class NewReminder(StatesGroup):
    text = State()
    freq = State()
    weekday = State()
    monthday = State()
    time_ = State()


async def ask_next(message: Message, state: FSMContext):
    """Yetishmayotgan birinchi ma'lumotni so'raydi, hammasi bo'lsa saqlaydi."""
    data = await state.get_data()
    if data.get("freq") is None:
        await state.set_state(NewReminder.freq)
        await message.answer("Qanchalik tez-tez eslatay? 👇", reply_markup=freq_kb)
    elif data["freq"] == "weekly" and data.get("weekday") is None:
        await state.set_state(NewReminder.weekday)
        await message.answer("Haftaning qaysi kuni? 👇", reply_markup=weekday_kb)
    elif data["freq"] == "monthly" and data.get("monthday") is None:
        await state.set_state(NewReminder.monthday)
        await message.answer("Oyning qaysi kuni? Raqam yozing (1-31):")
    elif data.get("hour") is None:
        await state.set_state(NewReminder.time_)
        await message.answer("Soat nechada eslatay? Masalan: <b>09:00</b> yoki <b>21:30</b>")
    else:
        await finalize(message, state)


async def finalize(message: Message, state: FSMContext):
    """Eslatmani bazaga yozib, jadvalga qo'shadi."""
    data = await state.get_data()
    await state.clear()

    user_id = await db.get_or_create_user(
        message.from_user.id, message.from_user.first_name or ""
    )
    start_date = None
    if data["freq"] == "every2":
        start_date = first_run_date(data["hour"], data["minute"]).isoformat()

    reminder_id = await db.add_reminder(
        user_id=user_id,
        text=data["text"],
        freq=data["freq"],
        hour=data["hour"],
        minute=data["minute"],
        weekday=data.get("weekday"),
        monthday=data.get("monthday"),
        start_date=start_date,
    )
    rem = await db.get_reminder(reminder_id)
    schedule_reminder(message.bot, rem)

    when = describe(data["freq"], data.get("weekday"), data.get("monthday"),
                    data["hour"], data["minute"])
    await message.answer(
        f"✅ Eslatma saqlandi!\n\n"
        f"📝 <b>{data['text']}</b>\n"
        f"🕒 {when}\n\n"
        f"Vaqti kelganda albatta eslataman! 😉",
        reply_markup=main_menu,
    )


# --- Oqim boshlanishi ---

@router.message(F.text == BTN_NEW)
async def new_reminder(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewReminder.text)
    await message.answer(
        "Nimani eslatay? ✍️\n\n"
        "<i>Maslahat: vaqtini ham qo'shib yozsangiz bo'ladi, masalan:\n"
        "«har kuni 8:00 da dori ichish»</i>"
    )


@router.message(NewReminder.text, F.text)
async def got_text(message: Message, state: FSMContext):
    await _handle_parsed(message, state, message.text)


# --- Tugmalar orqali javoblar ---

@router.callback_query(NewReminder.freq, F.data.startswith("freq:"))
async def got_freq(callback: CallbackQuery, state: FSMContext):
    freq = callback.data.split(":")[1]
    await state.update_data(freq=freq)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await ask_next(callback.message, state)


@router.callback_query(NewReminder.weekday, F.data.startswith("wd:"))
async def got_weekday(callback: CallbackQuery, state: FSMContext):
    await state.update_data(weekday=int(callback.data.split(":")[1]))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await ask_next(callback.message, state)


@router.message(NewReminder.monthday, F.text)
async def got_monthday(message: Message, state: FSMContext):
    raw = message.text.strip().rstrip("-kuni").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 31:
        await message.answer("Iltimos, 1 dan 31 gacha raqam yozing. Masalan: <b>15</b>")
        return
    day = int(raw)
    if day > 28:
        await message.answer(
            f"⚠️ Eslatib o'taman: ba'zi oylarda {day}-kun yo'q, "
            f"bunday oylarda eslatma kelmaydi."
        )
    await state.update_data(monthday=day)
    await ask_next(message, state)


@router.message(NewReminder.time_, F.text)
async def got_time(message: Message, state: FSMContext):
    parsed = parse_time(message.text)
    if parsed is None:
        await message.answer(
            "Vaqtni tushunmadim 😅 Iltimos, shunday yozing: <b>09:00</b> yoki <b>21:30</b>"
        )
        return
    await state.update_data(hour=parsed[0], minute=parsed[1])
    await ask_next(message, state)


# --- Erkin matn (menyu tashqarisida yozilgan har qanday xabar) ---
# DIQQAT: bu handler routerlar ro'yxatida oxirida turishi kerak.

@router.message(F.text)
async def free_text(message: Message, state: FSMContext):
    await _handle_parsed(message, state, message.text)


async def _handle_parsed(message: Message, state: FSMContext, raw: str):
    """Matnni parser orqali o'tkazib, yetishmagan qismlarini so'raydi."""
    parsed = parse_text(raw)
    text = parsed["text"] or raw.strip()
    await state.update_data(
        text=text,
        freq=parsed["freq"],
        weekday=parsed["weekday"],
        monthday=parsed["monthday"],
        hour=parsed["hour"],
        minute=parsed["minute"],
    )
    found = []
    if parsed["freq"]:
        found.append("takrorlanishni")
    if parsed["hour"] is not None:
        found.append("vaqtni")
    if found:
        await message.answer(f"👍 Matndan {' va '.join(found)} avtomatik aniqladim!")
    await ask_next(message, state)
