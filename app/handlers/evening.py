"""🌙 Kechki reja — "Ertaga uchun reja qo'shasizmi?" oqimi.

User bir yoki bir nechta qator yozadi (har qatorda vaqt + ish),
har biri ertangi kunga bir martalik eslatma bo'lib saqlanadi.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import BTN_PLAN_DONE, main_menu, plan_done_kb
from app.scheduler.scheduler import once_run_date, schedule_reminder
from app.utils.parser import parse_text

router = Router()


class EveningPlan(StatesGroup):
    items = State()


@router.callback_query(F.data == "ev_skip")
async def ev_skip(callback: CallbackQuery):
    await callback.message.edit_text(
        callback.message.html_text + "\n\n😌 <i>Mayli! Xayrli tun</i> 🌙"
    )
    await callback.answer()


@router.callback_query(F.data == "ev_add")
async def ev_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EveningPlan.items)
    await state.update_data(added=0)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Ertangi rejalaringizni yozing — har birini <b>alohida qatorda</b>, "
        "vaqti bilan:\n\n"
        "<i>09:00 uchrashuv\n"
        "15:30 Alisherga qo'ng'iroq\n"
        "18:00 zal</i>\n\n"
        "Tugatgach <b>✅ Tayyor</b> tugmasini bosing 👇",
        reply_markup=plan_done_kb,
    )
    await callback.answer()


@router.message(EveningPlan.items, F.text == BTN_PLAN_DONE)
async def ev_done(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    count = data.get("added", 0)
    if count:
        await message.answer(
            f"✅ Ertaga uchun <b>{count} ta</b> reja saqlandi!\n"
            f"Ertalab kun rejangizda ko'rasiz, vaqtida alohida eslataman. "
            f"Xayrli tun! 🌙",
            reply_markup=main_menu,
        )
    else:
        await message.answer("Mayli, reja qo'shilmadi. Xayrli tun! 🌙",
                             reply_markup=main_menu)


@router.message(EveningPlan.items, F.text)
async def ev_items(message: Message, state: FSMContext):
    user_db_id = await db.upsert_user(message.from_user)
    added, failed = [], []

    for line in message.text.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = parse_text(line)
        if parsed["hour"] is None or not parsed["text"]:
            failed.append(line)
            continue
        dt = once_run_date(1, parsed["hour"], parsed["minute"])  # ertaga
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
        added.append(f"🕒 {parsed['hour']:02d}:{parsed['minute']:02d} — {parsed['text']}")

    data = await state.get_data()
    await state.update_data(added=data.get("added", 0) + len(added))

    parts = []
    if added:
        parts.append("Qo'shildi:\n" + "\n".join(added))
    if failed:
        parts.append(
            "⚠️ Bularni tushunmadim (vaqtini yozing, masalan «09:00 uchrashuv»):\n"
            + "\n".join(f"• {f}" for f in failed)
        )
    parts.append("Yana yozing yoki <b>✅ Tayyor</b> ni bosing 👇")
    await message.answer("\n\n".join(parts), reply_markup=plan_done_kb)
