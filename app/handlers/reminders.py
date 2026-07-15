"""Yangi eslatma yaratish oqimi (FSM) + erkin matnni avtomatik tushunish."""
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from datetime import datetime

from app.database import db
from app.keyboards.keyboards import (
    BTN_NEW,
    freq_kb,
    main_menu,
    once_day_kb,
    weekday_kb,
)
from app.scheduler.scheduler import (
    TZ,
    first_run_date,
    next_weekday_run_date,
    once_run_date,
    schedule_digest,
    schedule_reminder,
)
from app.utils.ai import ai_available, ai_parse_reminder
from app.utils.fmt import esc
from app.utils.parser import describe, parse_text, parse_time
from app.utils.stt import stt_available, transcribe_voice

router = Router()


class NewReminder(StatesGroup):
    text = State()
    freq = State()
    once_day = State()
    weekday = State()
    monthday = State()
    time_ = State()


async def ask_next(message: Message, state: FSMContext):
    """Yetishmayotgan birinchi ma'lumotni so'raydi, hammasi bo'lsa saqlaydi."""
    data = await state.get_data()
    if data.get("freq") is None:
        await state.set_state(NewReminder.freq)
        await message.answer("Qanchalik tez-tez eslatay? 👇", reply_markup=freq_kb)
    elif (data["freq"] == "once" and data.get("once_offset") is None
          and data.get("once_weekday") is None):
        await state.set_state(NewReminder.once_day)
        await message.answer("Qaysi kunga? 👇", reply_markup=once_day_kb)
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

    start_date = None
    if data["freq"] == "once":
        if data.get("once_weekday") is not None:
            # "dushanba kuni 10 da" — eng yaqin keladigan dushanba, o'tib ketmaydi
            dt = next_weekday_run_date(data["once_weekday"], data["hour"], data["minute"])
        else:
            dt = once_run_date(data.get("once_offset") or 0, data["hour"], data["minute"])
        if dt <= datetime.now(TZ):
            # "Bugun"ga tanlangan vaqt allaqachon o'tib ketgan
            await state.set_state(NewReminder.time_)
            await state.update_data(hour=None, minute=None)
            await message.answer(
                "⚠️ Bu vaqt bugun allaqachon o'tib ketdi 😅\n"
                "Boshqa vaqt yozing (masalan <b>21:30</b>) yoki /start bilan qaytadan boshlang."
            )
            return
        start_date = dt.isoformat()
    elif data["freq"] == "every2":
        start_date = first_run_date(data["hour"], data["minute"]).isoformat()

    await state.clear()

    # user_db_id oqim boshida saqlangan — callback orqali kelganda
    # message.from_user bot bo'lib qolishi mumkin, shuning uchun undan olmaymiz
    user_id = data["user_db_id"]

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

    # User /start siz (erkin matn orqali) kelgan bo'lsa ham digestini yoqamiz
    user = await db.get_user_by_id(user_id)
    if user:
        schedule_digest(message.bot, user)

    when = describe(data["freq"], data.get("weekday"), data.get("monthday"),
                    data["hour"], data["minute"], start_date=start_date)
    await message.answer(
        f"✅ Eslatma saqlandi!\n\n"
        f"📝 <b>{esc(data['text'])}</b>\n"
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


@router.callback_query(NewReminder.once_day, F.data.startswith("od:"))
async def got_once_day(callback: CallbackQuery, state: FSMContext):
    await state.update_data(once_offset=int(callback.data.split(":")[1]))
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
    m = re.search(r"\d{1,2}", message.text)
    if not m or not 1 <= int(m.group()) <= 31:
        await message.answer("Iltimos, 1 dan 31 gacha raqam yozing. Masalan: <b>15</b>")
        return
    day = int(m.group())
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


# --- Ovozli xabar: matnga aylantirib, xuddi yozilgandek qayta ishlaymiz ---

@router.message(F.voice)
async def voice_message(message: Message, state: FSMContext):
    if not stt_available():
        await message.answer(
            "Ovozli xabarlarni hozircha tushunmayman 😅 Iltimos, yozib yuboring."
        )
        return

    # Ro'yxatdan o'tish kabi boshqa bosqichlarda ovoz qabul qilmaymiz
    current = await state.get_state()
    if current is not None and not current.startswith("NewReminder"):
        await message.answer("Iltimos, bu bosqichda yozib javob bering 😊")
        return

    if message.voice.duration > 120:
        await message.answer(
            "Ovozli xabar juda uzun (2 daqiqagacha qabul qilaman) 😅"
        )
        return

    wait_msg = await message.answer("🎙 Eshityapman...")
    text = await transcribe_voice(message.bot, message.voice.file_id)
    if not text:
        await wait_msg.edit_text(
            "Ovozni tushuna olmadim 😔 Qaytadan urinib ko'ring yoki yozib yuboring."
        )
        return
    await wait_msg.edit_text(f"🎙 Eshitdim: <i>«{esc(text)}»</i>")

    # AI (Gemini) bilan chuqur tahlil; ishlamasa oddiy regex'ga o'tadi
    parsed = await ai_parse_reminder(text) if ai_available() else None
    await _handle_parsed(message, state, text, parsed=parsed)


# --- Erkin matn (menyu tashqarisida yozilgan har qanday xabar) ---
# DIQQAT: bu handler routerlar ro'yxatida oxirida turishi kerak.

@router.message(F.text)
async def free_text(message: Message, state: FSMContext):
    await _handle_parsed(message, state, message.text)


async def _handle_parsed(message: Message, state: FSMContext, raw: str,
                         parsed: dict | None = None):
    """Matnni tahlil qilib (AI yoki regex), yetishmagan qismlarini so'raydi."""
    user_db_id = await db.upsert_user(message.from_user)
    if parsed is None:
        parsed = parse_text(raw)
    text = parsed["text"] or raw.strip()
    await state.update_data(
        user_db_id=user_db_id,
        text=text,
        freq=parsed["freq"],
        weekday=parsed["weekday"],
        monthday=parsed["monthday"],
        hour=parsed["hour"],
        minute=parsed["minute"],
        once_offset=parsed["once_offset"],
        once_weekday=parsed.get("once_weekday"),
    )
    found = []
    if parsed["freq"] == "once" and (parsed["once_offset"] is not None
                                     or parsed.get("once_weekday") is not None):
        found.append("kunni")
    elif parsed["freq"]:
        found.append("takrorlanishni")
    if parsed["hour"] is not None:
        found.append("vaqtni")
    if found:
        await message.answer(f"👍 Matndan {' va '.join(found)} avtomatik aniqladim!")
    await ask_next(message, state)
