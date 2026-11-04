"""Vazifalar (tasks) — bir martalik ishlar: muddat, ustuvorlik, bajarildi.

Eslatmadan farqli: vazifa belgilangan vaqtda otilmaydi; u ro'yxatda turadi,
muddati (deadline) va ustuvorligi bo'ladi, bajarilgach belgilanadi.
"""
from datetime import timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import (
    BTN_TASKS,
    PRIORITY_MARK,
    PRIORITY_NAME,
    main_menu,
    task_due_kb,
    task_manage_kb,
    task_priority_kb,
    tasks_list_kb,
)
from app.scheduler.scheduler import TZ
from app.utils.fmt import esc

router = Router()


class NewTask(StatesGroup):
    title = State()


async def _owned_task(callback: CallbackQuery, task_id: int) -> dict | None:
    task = await db.get_task(task_id)
    if not task or task["tg_id"] != callback.from_user.id:
        await callback.answer("Bu vazifa topilmadi yoki sizga tegishli emas 🤷",
                              show_alert=True)
        return None
    return task


def _due_label(due: str | None) -> str:
    if not due:
        return "sanasiz"
    today = _today()
    from datetime import date
    d = date.fromisoformat(due)
    delta = (d - today).days
    if delta < 0:
        return f"{due} — ⚠️ muddati o'tgan ({-delta} kun)"
    if delta == 0:
        return f"{due} — bugun"
    if delta == 1:
        return f"{due} — ertaga"
    return f"{due} — {delta} kundan keyin"


def _today():
    from datetime import datetime
    return datetime.now(TZ).date()


def _list_text(tasks: list[dict]) -> str:
    today = _today()
    from datetime import date
    overdue = today_c = upcoming = nodate = 0
    for t in tasks:
        if not t["due_date"]:
            nodate += 1
        else:
            d = date.fromisoformat(t["due_date"])
            if d < today:
                overdue += 1
            elif d == today:
                today_c += 1
            else:
                upcoming += 1
    return (
        f"✅ <b>Vazifalar</b> — {len(tasks)} ta bajarilmagan\n\n"
        f"⚠️ Muddati o'tgan: <b>{overdue}</b>  ·  📅 Bugun: <b>{today_c}</b>\n"
        f"🔜 Keyingi: <b>{upcoming}</b>  ·  🗓 Sanasiz: <b>{nodate}</b>\n\n"
        "Ko'rish yoki belgilash uchun vazifani tanlang 👇"
    )


def _detail_text(task: dict) -> str:
    status = "✅ Bajarilgan" if task["is_done"] else "⬜ Bajarilmagan"
    prio = f"{PRIORITY_MARK.get(task['priority'], '🟡')} {PRIORITY_NAME.get(task['priority'], task['priority'])}"
    return (
        f"{'✅' if task['is_done'] else '📌'} <b>{esc(task['title'])}</b>\n\n"
        f"Holat: {status}\n"
        f"⭐ Ustuvorlik: {prio}\n"
        f"📅 Muddat: {_due_label(task['due_date'])}"
    )


# --- Ro'yxat ---

@router.message(Command("tasks"))
@router.message(F.text == BTN_TASKS)
async def show_tasks(message: Message, state: FSMContext):
    await state.clear()
    tasks = await db.get_user_tasks(message.from_user.id)
    if not tasks:
        await message.answer(
            "Sizda bajarilmagan vazifa yo'q. 🎉\n"
            "Yangi vazifa qo'shish uchun pastdagi tugmani bosing 👇",
            reply_markup=tasks_list_kb([]),
        )
        return
    await message.answer(_list_text(tasks), reply_markup=tasks_list_kb(tasks))


@router.callback_query(F.data == "tlist")
@router.callback_query(F.data.startswith("tpage:"))
async def task_list_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0
    tasks = await db.get_user_tasks(callback.from_user.id)
    text = _list_text(tasks) if tasks else "Sizda bajarilmagan vazifa yo'q. 🎉"
    try:
        await callback.message.edit_text(text, reply_markup=tasks_list_kb(tasks, page))
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Yangi vazifa (tnew -> nom so'raymiz) ---

@router.callback_query(F.data == "tnew")
async def task_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTask.title)
    await callback.message.answer(
        "Yangi vazifa nomini yozing ✍️\n"
        "<i>(muddat va ustuvorlikni keyin qo'shasiz)</i>\n\n"
        "Bekor qilish uchun /cancel"
    )
    await callback.answer()


@router.message(NewTask.title, F.text)
async def task_got_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title or len(title) > 500:
        await message.answer("Iltimos, qisqaroq nom yozing 🙂")
        return
    await state.clear()
    user_id = await db.upsert_user(message.from_user)
    tid = await db.add_task(user_id, title)
    task = await db.get_task(tid)
    await message.answer(
        "✅ Vazifa qo'shildi!\n\n" + _detail_text(task),
        reply_markup=task_manage_kb(tid, False),
    )


# --- Bitta vazifa ---

@router.callback_query(F.data.startswith("tshow:"))
async def task_show(callback: CallbackQuery):
    tid = int(callback.data.split(":")[1])
    task = await _owned_task(callback, tid)
    if not task:
        return
    try:
        await callback.message.edit_text(
            _detail_text(task), reply_markup=task_manage_kb(tid, bool(task["is_done"])))
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("tdone:"))
async def task_done(callback: CallbackQuery):
    _, tid, val = callback.data.split(":")
    tid, done = int(tid), val == "1"
    if not await _owned_task(callback, tid):
        return
    await db.set_task_done(tid, done)
    task = await db.get_task(tid)
    await callback.message.edit_text(
        _detail_text(task), reply_markup=task_manage_kb(tid, done))
    await callback.answer("✅ Bajarildi!" if done else "↩️ Qaytarildi")


@router.callback_query(F.data.startswith("tdel:"))
async def task_delete(callback: CallbackQuery):
    tid = int(callback.data.split(":")[1])
    if not await _owned_task(callback, tid):
        return
    await db.delete_task(tid)
    tasks = await db.get_user_tasks(callback.from_user.id)
    if tasks:
        await callback.message.edit_text(_list_text(tasks), reply_markup=tasks_list_kb(tasks))
    else:
        await callback.message.edit_text("🗑 O'chirildi. Bajarilmagan vazifa qolmadi. 🎉")
    await callback.answer("🗑 O'chirildi")


# --- Ustuvorlik ---

@router.callback_query(F.data.startswith("tprio:"))
async def task_prio_menu(callback: CallbackQuery):
    tid = int(callback.data.split(":")[1])
    if not await _owned_task(callback, tid):
        return
    await callback.message.edit_text(
        "Ustuvorlikni tanlang:", reply_markup=task_priority_kb(tid))
    await callback.answer()


@router.callback_query(F.data.startswith("tsetp:"))
async def task_set_prio(callback: CallbackQuery):
    _, tid, prio = callback.data.split(":")
    tid = int(tid)
    if not await _owned_task(callback, tid):
        return
    await db.update_task(tid, priority=prio)
    task = await db.get_task(tid)
    await callback.message.edit_text(
        _detail_text(task), reply_markup=task_manage_kb(tid, bool(task["is_done"])))
    await callback.answer("⭐ Ustuvorlik yangilandi")


# --- Muddat ---

@router.callback_query(F.data.startswith("tdue:"))
async def task_due_menu(callback: CallbackQuery):
    tid = int(callback.data.split(":")[1])
    if not await _owned_task(callback, tid):
        return
    await callback.message.edit_text(
        "Muddatni tanlang:", reply_markup=task_due_kb(tid))
    await callback.answer()


@router.callback_query(F.data.startswith("tsetd:"))
async def task_set_due(callback: CallbackQuery):
    _, tid, token = callback.data.split(":")
    tid = int(tid)
    if not await _owned_task(callback, tid):
        return
    due = None if token == "none" else (_today() + timedelta(days=int(token))).isoformat()
    await db.update_task(tid, due_date=due)
    task = await db.get_task(tid)
    await callback.message.edit_text(
        _detail_text(task), reply_markup=task_manage_kb(tid, bool(task["is_done"])))
    await callback.answer("📅 Muddat yangilandi")
