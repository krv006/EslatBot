"""Materiallar — davomli o'qish/o'rganish (kitob, kurs, Qur'on xatmi).

Joriy nuqta (current) yangilanadi; umumiy hajm (total) ma'lum bo'lsa foiz va
qolgan qism ko'rsatiladi. Umumiy hajmga yetish materialni avtomat yakunlamaydi
(TZ 5.9) — foydalanuvchi o'zi "✅ Yakunlash" bosadi.
"""
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import (
    BTN_MATERIALS,
    MSTATUS_MARK,
    MTYPE_MARK,
    MTYPE_NAME,
    material_manage_kb,
    material_progress_kb,
    material_type_kb,
    materials_list_kb,
)
from app.utils.fmt import esc

router = Router()

_STATUS_NAME = {"active": "Faol", "paused": "Pauzada", "done": "Yakunlangan"}


class NewMaterial(StatesGroup):
    title = State()


class SetValue(StatesGroup):
    progress = State()
    total = State()


async def _owned(callback: CallbackQuery, mid: int) -> dict | None:
    m = await db.get_material(mid)
    if not m or m["tg_id"] != callback.from_user.id:
        await callback.answer("Bu material topilmadi yoki sizga tegishli emas 🤷",
                              show_alert=True)
        return None
    return m


def _list_text(items: list[dict]) -> str:
    active = sum(1 for m in items if m["status"] == "active")
    return (f"📚 <b>Materiallar</b> — {len(items)} ta ({active} faol)\n\n"
            "Ko'rish yoki yangilash uchun tanlang 👇")


def _detail_text(m: dict) -> str:
    tmark = MTYPE_MARK.get(m["mtype"], "📄")
    tname = MTYPE_NAME.get(m["mtype"], m["mtype"])
    smark = MSTATUS_MARK.get(m["status"], "🟢")
    sname = _STATUS_NAME.get(m["status"], m["status"])
    unit = f" {m['unit']}" if m["unit"] else ""
    lines = [
        f"{tmark} <b>{esc(m['title'])}</b>\n",
        f"Tur: {tname}",
        f"Holat: {smark} {sname}",
    ]
    if m["total"]:
        cur = min(m["current"], m["total"])
        pct = int(cur * 100 / m["total"]) if m["total"] else 0
        remaining = max(m["total"] - m["current"], 0)
        bar_full = pct // 10
        bar = "█" * bar_full + "░" * (10 - bar_full)
        lines.append(f"📊 Jarayon: {m['current']}/{m['total']}{unit}  ({pct}%)")
        lines.append(f"{bar}")
        lines.append(f"🔚 Qolgan: {remaining}{unit}")
    else:
        lines.append(f"📍 Joriy: {m['current']}{unit}  (umumiy hajm belgilanmagan)")
    return "\n".join(lines)


async def _show_detail(callback: CallbackQuery, m: dict):
    try:
        await callback.message.edit_text(
            _detail_text(m), reply_markup=material_manage_kb(m["id"], m["status"]))
    except TelegramBadRequest:
        pass


# --- Ro'yxat ---

@router.message(Command("materials"))
@router.message(F.text == BTN_MATERIALS)
async def show_materials(message: Message, state: FSMContext):
    await state.clear()
    items = await db.get_user_materials(message.from_user.id)
    if not items:
        await message.answer(
            "Sizda materiallar yo'q. 📚\nKitob yoki kurs qo'shish uchun tugmani bosing 👇",
            reply_markup=materials_list_kb([]),
        )
        return
    await message.answer(_list_text(items), reply_markup=materials_list_kb(items))


@router.callback_query(F.data == "mlist")
@router.callback_query(F.data.startswith("mpage:"))
async def materials_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0
    items = await db.get_user_materials(callback.from_user.id)
    text = _list_text(items) if items else "Sizda materiallar yo'q. 📚"
    try:
        await callback.message.edit_text(text, reply_markup=materials_list_kb(items, page))
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Yangi material ---

@router.callback_query(F.data == "mnew")
async def material_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewMaterial.title)
    await callback.message.answer(
        "Material nomini yozing 📚\n"
        "<i>(masalan: «Atomic Habits» yoki «Python kursi»)</i>\n\n"
        "Turi va hajmini keyin belgilaysiz. Bekor qilish: /cancel")
    await callback.answer()


@router.message(NewMaterial.title, F.text)
async def material_got_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title or len(title) > 300:
        await message.answer("Iltimos, qisqaroq nom yozing 🙂")
        return
    await state.clear()
    user_id = await db.upsert_user(message.from_user)
    mid = await db.add_material(user_id, title)
    m = await db.get_material(mid)
    await message.answer(
        "✅ Material qo'shildi!\n\n" + _detail_text(m),
        reply_markup=material_manage_kb(mid, m["status"]))


# --- Bitta material ---

@router.callback_query(F.data.startswith("mshow:"))
async def material_show(callback: CallbackQuery):
    mid = int(callback.data.split(":")[1])
    m = await _owned(callback, mid)
    if not m:
        return
    await _show_detail(callback, m)
    await callback.answer()


# --- Jarayonni yangilash ---

@router.callback_query(F.data.startswith("mupd:"))
async def material_upd_menu(callback: CallbackQuery):
    mid = int(callback.data.split(":")[1])
    if not await _owned(callback, mid):
        return
    await callback.message.edit_text(
        "Qancha oldinga siljidingiz? Tugmadan tanlang yoki aniq sonni kiriting 👇",
        reply_markup=material_progress_kb(mid))
    await callback.answer()


@router.callback_query(F.data.startswith("minc:"))
async def material_inc(callback: CallbackQuery):
    _, mid, step = callback.data.split(":")
    mid = int(mid)
    m = await _owned(callback, mid)
    if not m:
        return
    new_cur = max(m["current"] + int(step), 0)
    await db.update_material(mid, current=new_cur)
    m = await db.get_material(mid)
    await _show_detail(callback, m)
    done_hint = ""
    if m["total"] and new_cur >= m["total"]:
        done_hint = " — hajmga yetdingiz! «✅ Yakunlash»ni bosishingiz mumkin"
    await callback.answer(f"📈 {new_cur}{done_hint}")


@router.callback_query(F.data.startswith("mexact:"))
async def material_exact_ask(callback: CallbackQuery, state: FSMContext):
    mid = int(callback.data.split(":")[1])
    if not await _owned(callback, mid):
        return
    await state.set_state(SetValue.progress)
    await state.update_data(mid=mid)
    await callback.message.answer("Joriy nuqtani raqam bilan yozing (masalan 120):\n\n/cancel")
    await callback.answer()


@router.message(SetValue.progress, F.text)
async def material_exact_set(message: Message, state: FSMContext):
    m = re.search(r"\d+", message.text)
    if not m:
        await message.answer("Iltimos, raqam yozing (masalan 120).")
        return
    data = await state.get_data()
    await state.clear()
    mid = data["mid"]
    await db.update_material(mid, current=int(m.group()))
    mat = await db.get_material(mid)
    await message.answer(_detail_text(mat), reply_markup=material_manage_kb(mid, mat["status"]))


# --- Umumiy hajm (total) ---

@router.callback_query(F.data.startswith("mtotal:"))
async def material_total_ask(callback: CallbackQuery, state: FSMContext):
    mid = int(callback.data.split(":")[1])
    if not await _owned(callback, mid):
        return
    await state.set_state(SetValue.total)
    await state.update_data(mid=mid)
    await callback.message.answer(
        "Umumiy hajmni raqam bilan yozing (masalan 320 bet).\n"
        "Bilmasangiz 0 yozing — hajmsiz yuritiladi.\n\n/cancel")
    await callback.answer()


@router.message(SetValue.total, F.text)
async def material_total_set(message: Message, state: FSMContext):
    m = re.search(r"\d+", message.text)
    if not m:
        await message.answer("Iltimos, raqam yozing (masalan 320).")
        return
    data = await state.get_data()
    await state.clear()
    mid = data["mid"]
    total = int(m.group())
    await db.update_material(mid, total=total if total > 0 else None)
    mat = await db.get_material(mid)
    await message.answer(_detail_text(mat), reply_markup=material_manage_kb(mid, mat["status"]))


# --- Tur ---

@router.callback_query(F.data.startswith("mtype:"))
async def material_type_menu(callback: CallbackQuery):
    mid = int(callback.data.split(":")[1])
    if not await _owned(callback, mid):
        return
    await callback.message.edit_text("Material turini tanlang:", reply_markup=material_type_kb(mid))
    await callback.answer()


@router.callback_query(F.data.startswith("msett:"))
async def material_set_type(callback: CallbackQuery):
    _, mid, mtype = callback.data.split(":")
    mid = int(mid)
    if not await _owned(callback, mid):
        return
    await db.update_material(mid, mtype=mtype)
    m = await db.get_material(mid)
    await _show_detail(callback, m)
    await callback.answer("📚 Tur yangilandi")


# --- Holat (pauza / faollashtirish / yakunlash) ---

@router.callback_query(F.data.startswith("mstatus:"))
async def material_set_status(callback: CallbackQuery):
    _, mid, status = callback.data.split(":")
    mid = int(mid)
    if not await _owned(callback, mid):
        return
    await db.update_material(mid, status=status)
    m = await db.get_material(mid)
    await _show_detail(callback, m)
    labels = {"active": "▶️ Faollashtirildi", "paused": "⏸ Pauzaga qo'yildi",
              "done": "✅ Yakunlandi! Tabriklaymiz 🎉"}
    await callback.answer(labels.get(status, "Yangilandi"))


@router.callback_query(F.data.startswith("mdel:"))
async def material_delete(callback: CallbackQuery):
    mid = int(callback.data.split(":")[1])
    if not await _owned(callback, mid):
        return
    await db.delete_material(mid)
    items = await db.get_user_materials(callback.from_user.id)
    if items:
        await callback.message.edit_text(_list_text(items), reply_markup=materials_list_kb(items))
    else:
        await callback.message.edit_text("🗑 O'chirildi. Materiallar qolmadi.")
    await callback.answer("🗑 O'chirildi")
