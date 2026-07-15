"""Mavjud eslatmani tahrirlash: matn / vaqt / takrorlanish."""
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import (
    edit_freq_kb,
    edit_menu_kb,
    edit_once_day_kb,
    edit_weekday_kb,
    reminder_manage_kb,
)
from app.scheduler.scheduler import (
    TZ,
    first_run_date,
    once_run_date,
    schedule_reminder,
)
from app.utils.fmt import esc
from app.utils.parser import describe, parse_time

router = Router()


class EditReminder(StatesGroup):
    text = State()      # yangi matnni kutish
    time_ = State()     # yangi vaqtni kutish (faqat vaqt)
    monthday = State()  # takror=oyda bir uchun oy kunini kutish


def _format_line(rem: dict) -> str:
    status = "🟢" if rem["is_active"] else "⏸"
    when = describe(rem["freq"], rem["weekday"], rem["monthday"],
                    rem["hour"], rem["minute"], start_date=rem["start_date"])
    return f"{status} <b>{esc(rem['text'])}</b>\n🕒 {when}"


async def _confirm(message: Message, rem_id: int, note: str):
    """Yangilangandan keyin eslatmani jadvalga qaytarib, tasdiq yuboradi."""
    rem = await db.get_reminder(rem_id)
    if not rem:
        await message.answer("Eslatma topilmadi 🤷")
        return
    schedule_reminder(message.bot, rem)
    await message.answer(
        f"✅ {note}\n\n{_format_line(rem)}",
        reply_markup=reminder_manage_kb(rem["id"], bool(rem["is_active"])),
    )


# --- Tahrirlash menyusi ---

@router.callback_query(F.data.startswith("edit:"))
async def edit_open(callback: CallbackQuery):
    rid = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=edit_menu_kb(rid))
    await callback.answer("Nimani o'zgartiramiz?")


@router.callback_query(F.data.startswith("e_back:"))
async def edit_back(callback: CallbackQuery):
    rid = int(callback.data.split(":")[1])
    rem = await db.get_reminder(rid)
    if rem:
        await callback.message.edit_reply_markup(
            reply_markup=reminder_manage_kb(rid, bool(rem["is_active"]))
        )
    await callback.answer()


# --- 1) Matn ---

@router.callback_query(F.data.startswith("e_text:"))
async def edit_text_ask(callback: CallbackQuery, state: FSMContext):
    rid = int(callback.data.split(":")[1])
    await state.set_state(EditReminder.text)
    await state.update_data(edit_id=rid)
    await callback.message.answer("✍️ Yangi matnni yozing:")
    await callback.answer()


@router.message(EditReminder.text, F.text)
async def edit_text_save(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text or len(text) > 500:
        await message.answer("Iltimos, qisqaroq matn yozing 😊")
        return
    data = await state.get_data()
    await state.clear()
    await db.update_reminder(data["edit_id"], text=text)
    await _confirm(message, data["edit_id"], "Matn yangilandi!")


# --- 2) Vaqt (faqat soat, takror o'zgarmaydi) ---

@router.callback_query(F.data.startswith("e_time:"))
async def edit_time_ask(callback: CallbackQuery, state: FSMContext):
    rid = int(callback.data.split(":")[1])
    await state.set_state(EditReminder.time_)
    await state.update_data(edit_id=rid)
    await callback.message.answer(
        "🕒 Yangi vaqtni yozing. Masalan: <b>09:00</b> yoki <b>21:30</b>"
    )
    await callback.answer()


@router.message(EditReminder.time_, F.text)
async def edit_time_save(message: Message, state: FSMContext):
    parsed = parse_time(message.text)
    if parsed is None:
        await message.answer(
            "Vaqtni tushunmadim 😅 Shunday yozing: <b>09:00</b> yoki <b>21:30</b>"
        )
        return
    hour, minute = parsed
    data = await state.get_data()
    rem = await db.get_reminder(data["edit_id"])
    if not rem:
        await state.clear()
        await message.answer("Eslatma topilmadi 🤷")
        return

    fields = {"hour": hour, "minute": minute}
    # Bir martalik va "kun ora"da start_date ham vaqtga bog'liq — qayta hisoblaymiz
    if rem["freq"] == "once":
        base = (datetime.fromisoformat(rem["start_date"])
                if rem["start_date"] else datetime.now(TZ))
        if base.tzinfo is None:
            base = base.replace(tzinfo=TZ)
        dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt <= datetime.now(TZ):
            await message.answer(
                "⚠️ Bu vaqt o'tib ketgan 😅 Boshqa vaqt yozing yoki "
                "🔁 <b>Takror</b> orqali kunini o'zgartiring."
            )
            return
        fields["start_date"] = dt.isoformat()
    elif rem["freq"] == "every2":
        fields["start_date"] = first_run_date(hour, minute).isoformat()

    await state.clear()
    await db.update_reminder(data["edit_id"], **fields)
    await _confirm(message, data["edit_id"], "Vaqt yangilandi!")


# --- 3) Takrorlanish (vaqt eski qoladi) ---

@router.callback_query(F.data.startswith("e_freq:"))
async def edit_freq_ask(callback: CallbackQuery, state: FSMContext):
    rid = int(callback.data.split(":")[1])
    await state.update_data(edit_id=rid)
    await callback.message.answer(
        "🔁 Qanchalik tez-tez eslatay? 👇\n"
        "<i>(vaqti o'zgarmaydi — uni «🕒 Vaqt»dan alohida o'zgartirasiz)</i>",
        reply_markup=edit_freq_kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ef:"))
async def edit_freq_chosen(callback: CallbackQuery, state: FSMContext):
    freq = callback.data.split(":")[1]
    await state.update_data(new_freq=freq)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    if freq == "once":
        await callback.message.answer("Qaysi kunga? 👇", reply_markup=edit_once_day_kb)
    elif freq == "weekly":
        await callback.message.answer("Haftaning qaysi kuni? 👇",
                                      reply_markup=edit_weekday_kb)
    elif freq == "monthly":
        await state.set_state(EditReminder.monthday)
        await callback.message.answer("Oyning qaysi kuni? Raqam yozing (1-31):")
    else:  # daily / every2 — qo'shimcha savol yo'q
        await _finalize_freq(callback.message, state,
                             once_offset=None, weekday=None, monthday=None)


@router.callback_query(F.data.startswith("eod:"))
async def edit_freq_once_day(callback: CallbackQuery, state: FSMContext):
    offset = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finalize_freq(callback.message, state,
                         once_offset=offset, weekday=None, monthday=None)


@router.callback_query(F.data.startswith("ewd:"))
async def edit_freq_weekday(callback: CallbackQuery, state: FSMContext):
    wd = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finalize_freq(callback.message, state,
                         once_offset=None, weekday=wd, monthday=None)


@router.message(EditReminder.monthday, F.text)
async def edit_freq_monthday(message: Message, state: FSMContext):
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
    await _finalize_freq(message, state,
                         once_offset=None, weekday=None, monthday=day)


async def _finalize_freq(message: Message, state: FSMContext,
                         once_offset, weekday, monthday):
    """Yangi takrorlanishni saqlaydi — vaqt eski eslatmadan olinadi."""
    data = await state.get_data()
    rid = data.get("edit_id")
    freq = data.get("new_freq")
    await state.clear()
    if rid is None or freq is None:
        await message.answer("⚠️ Sessiya eskirdi. Iltimos, 📋 Eslatmalarim'dan qaytadan boshlang.")
        return
    rem = await db.get_reminder(rid)
    if not rem:
        await message.answer("Eslatma topilmadi 🤷")
        return
    hour, minute = rem["hour"], rem["minute"]

    start_date = None
    if freq == "once":
        dt = once_run_date(once_offset or 0, hour, minute)
        if dt <= datetime.now(TZ):
            await message.answer(
                "⚠️ Tanlangan kun va eski vaqt allaqachon o'tib ketgan 😅\n"
                "Avval 🕒 <b>Vaqt</b>ni o'zgartiring, keyin takrorni."
            )
            return
        start_date = dt.isoformat()
    elif freq == "every2":
        start_date = first_run_date(hour, minute).isoformat()

    await db.update_reminder(
        rid, freq=freq, weekday=weekday, monthday=monthday,
        hour=hour, minute=minute, start_date=start_date,
    )
    await _confirm(message, rid, "Takrorlanish yangilandi!")
