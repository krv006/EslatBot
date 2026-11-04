"""Qaydlar (notes) — oddiy matnli eslatib qo'yish, qidirish bilan."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.database import db
from app.keyboards.keyboards import BTN_NOTES, note_manage_kb, notes_list_kb
from app.utils.fmt import esc

router = Router()


class NewNote(StatesGroup):
    text = State()


class FindNote(StatesGroup):
    query = State()


async def _owned_note(callback: CallbackQuery, note_id: int) -> dict | None:
    note = await db.get_note(note_id)
    if not note or note["tg_id"] != callback.from_user.id:
        await callback.answer("Bu qayd topilmadi yoki sizga tegishli emas 🤷",
                              show_alert=True)
        return None
    return note


def _list_text(notes: list[dict], query: str | None = None) -> str:
    if query is not None:
        return f"🔍 «{esc(query)}» bo'yicha <b>{len(notes)}</b> ta qayd topildi:"
    return (f"🗒 <b>Qaydlar</b> — {len(notes)} ta\n\n"
            "Ko'rish uchun tanlang yoki yangi qayd qo'shing 👇")


@router.message(Command("notes"))
@router.message(F.text == BTN_NOTES)
async def show_notes(message: Message, state: FSMContext):
    await state.clear()
    notes = await db.get_user_notes(message.from_user.id)
    if not notes:
        await message.answer(
            "Sizda qaydlar yo'q. ✍️\nYangi qayd qo'shish uchun tugmani bosing 👇",
            reply_markup=notes_list_kb([]),
        )
        return
    kb = notes_list_kb(notes)
    # Qidiruv tugmasini qo'shamiz (ro'yxatning tepasiga, "Yangi qayd" yonidan keyin)
    kb.inline_keyboard.insert(1, [InlineKeyboardButton(
        text="🔍 Qidirish", callback_data="nfind")])
    await message.answer(_list_text(notes), reply_markup=kb)


@router.callback_query(F.data == "nlist")
@router.callback_query(F.data.startswith("npage:"))
async def notes_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0
    notes = await db.get_user_notes(callback.from_user.id)
    text = _list_text(notes) if notes else "Sizda qaydlar yo'q. ✍️"
    try:
        await callback.message.edit_text(text, reply_markup=notes_list_kb(notes, page))
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Yangi qayd ---

@router.callback_query(F.data == "nnew")
async def note_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewNote.text)
    await callback.message.answer(
        "Qaydni yozing ✍️\n\nBekor qilish uchun /cancel")
    await callback.answer()


@router.message(NewNote.text, F.text)
async def note_got_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Bo'sh qayd saqlanmaydi 🙂")
        return
    await state.clear()
    user_id = await db.upsert_user(message.from_user)
    await db.add_note(user_id, text)
    await message.answer("✅ Qayd saqlandi!")
    notes = await db.get_user_notes(message.from_user.id)
    await message.answer(_list_text(notes), reply_markup=notes_list_kb(notes))


# --- Qidirish ---

@router.callback_query(F.data == "nfind")
async def note_find(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FindNote.query)
    await callback.message.answer("Qidiruv so'zini yozing 🔍\n\nBekor qilish: /cancel")
    await callback.answer()


@router.message(FindNote.query, F.text)
async def note_do_find(message: Message, state: FSMContext):
    await state.clear()
    query = message.text.strip()
    notes = await db.get_user_notes(message.from_user.id, query=query)
    if not notes:
        await message.answer(f"«{esc(query)}» bo'yicha qayd topilmadi 🤷")
        return
    await message.answer(_list_text(notes, query=query), reply_markup=notes_list_kb(notes))


# --- Bitta qayd ---

@router.callback_query(F.data.startswith("nshow:"))
async def note_show(callback: CallbackQuery):
    nid = int(callback.data.split(":")[1])
    note = await _owned_note(callback, nid)
    if not note:
        return
    try:
        await callback.message.edit_text(
            f"🗒 <b>Qayd</b>\n\n{esc(note['text'])}", reply_markup=note_manage_kb(nid))
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("ndel:"))
async def note_delete(callback: CallbackQuery):
    nid = int(callback.data.split(":")[1])
    if not await _owned_note(callback, nid):
        return
    await db.delete_note(nid)
    notes = await db.get_user_notes(callback.from_user.id)
    if notes:
        await callback.message.edit_text(_list_text(notes), reply_markup=notes_list_kb(notes))
    else:
        await callback.message.edit_text("🗑 O'chirildi. Qaydlar qolmadi.")
    await callback.answer("🗑 O'chirildi")
