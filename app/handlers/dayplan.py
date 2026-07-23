"""📝 Kunlik reja — user xohlagan payt bugun/ertaga uchun rejalar qo'shadi.

Har bir qator = bitta bir martalik eslatma (vaqt + ish).
"""
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.database import db
from app.keyboards.keyboards import BTN_PLAN, BTN_PLAN_DONE, main_menu, plan_done_kb
from app.scheduler.scheduler import TZ, once_run_date, schedule_reminder
from app.utils.fmt import esc
from app.utils.parser import parse_text
from app.utils.stt import voice_to_text

router = Router()


class DayPlan(StatesGroup):
    items = State()


plan_day_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📍 Bugunga", callback_data="pd:0"),
            InlineKeyboardButton(text="🌅 Ertagaga", callback_data="pd:1"),
        ]
    ]
)


@router.message(F.text == BTN_PLAN)
async def plan_start(message: Message, state: FSMContext):
    await state.clear()
    await db.upsert_user(message.from_user)
    await message.answer("Qaysi kunga reja qo'shasiz? 👇", reply_markup=plan_day_kb)


@router.callback_query(F.data.startswith("pd:"))
async def plan_day_chosen(callback: CallbackQuery, state: FSMContext):
    offset = int(callback.data.split(":")[1])
    await state.set_state(DayPlan.items)
    await state.update_data(day_offset=offset, added=0)
    day_word = "Bugungi" if offset == 0 else "Ertangi"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"{day_word} rejalaringizni yozing — har birini <b>alohida qatorda</b>, "
        f"vaqti bilan:\n\n"
        f"<i>09:00 uchrashuv\n"
        f"15:30 Alisherga qo'ng'iroq\n"
        f"18:00 zal</i>\n\n"
        f"Tugatgach <b>✅ Tayyor</b> tugmasini bosing 👇",
        reply_markup=plan_done_kb,
    )
    await callback.answer()


@router.message(DayPlan.items, F.text == BTN_PLAN_DONE)
async def plan_done(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    count = data.get("added", 0)
    day_word = "bugun" if data.get("day_offset") == 0 else "ertaga"
    if count:
        await message.answer(
            f"✅ <b>{count} ta</b> reja saqlandi ({day_word} uchun)!\n"
            f"Har birini o'z vaqtida eslataman. 💪",
            reply_markup=main_menu,
        )
    else:
        await message.answer("Reja qo'shilmadi.", reply_markup=main_menu)


@router.message(DayPlan.items, F.voice)
async def plan_items_voice(message: Message, state: FSMContext):
    text = await voice_to_text(message)
    if not text:
        return
    await _process_plan_text(message, state, text)


@router.message(DayPlan.items, F.text)
async def plan_items(message: Message, state: FSMContext):
    await _process_plan_text(message, state, message.text)


async def _process_plan_text(message: Message, state: FSMContext, raw: str):
    data = await state.get_data()
    offset = data.get("day_offset", 1)
    user_db_id = await db.upsert_user(message.from_user)
    now = datetime.now(TZ)
    added, failed, passed = [], [], []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = parse_text(line)
        if parsed["hour"] is None or not parsed["text"]:
            failed.append(line)
            continue
        dt = once_run_date(offset, parsed["hour"], parsed["minute"])
        if dt <= now:
            passed.append(line)
            continue
        reminder_id = await db.add_reminder(
            user_id=user_db_id,
            text=parsed["text"],
            freq="once",
            hour=parsed["hour"],
            minute=parsed["minute"],
            start_date=dt.isoformat(),
        )
        rem = await db.get_reminder(reminder_id)
        schedule_reminder(message.bot, rem)
        added.append(
            f"🕒 {parsed['hour']:02d}:{parsed['minute']:02d} — {esc(parsed['text'])}"
        )

    await state.update_data(added=data.get("added", 0) + len(added))

    parts = []
    if added:
        parts.append("Qo'shildi:\n" + "\n".join(added))
    if passed:
        parts.append(
            "⚠️ Bu vaqtlar bugun allaqachon o'tib ketgan:\n"
            + "\n".join(f"• {esc(p)}" for p in passed)
        )
    if failed:
        parts.append(
            "⚠️ Bularni tushunmadim (vaqtini yozing, masalan «09:00 uchrashuv»):\n"
            + "\n".join(f"• {esc(f)}" for f in failed)
        )
    parts.append("Yana yozing yoki <b>✅ Tayyor</b> ni bosing 👇")
    await message.answer("\n\n".join(parts), reply_markup=plan_done_kb)
