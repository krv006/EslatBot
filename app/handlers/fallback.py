"""Oxirgi chora — hech qaysi handler ushlamagan xabarlar uchun.

Muammo: FSM bosqichida (masalan "material nomini yozing") foydalanuvchi matn
o'rniga PDF/rasm/stiker yuborsa, hech bir handler mos kelmasdi va bot jim qolardi
— oqimda qotib qolinardi. Shu router ENG OXIRIDA registratsiya qilinadi, shuning
uchun u faqat boshqa hech kim ushlamagan xabarni oladi.
"""
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.keyboards.keyboards import main_menu

router = Router()


@router.message()
async def unhandled(message: Message, state: FSMContext):
    # Qandaydir oqim ichidamizmi? (nom/qiymat kutilyapti)
    if await state.get_state() is not None:
        await message.answer(
            "Buni tushunmadim 🙂 Iltimos, so'ralgan ma'lumotni <b>matn</b> bilan "
            "yozing.\n\nBekor qilish uchun /cancel."
        )
        return
    # Oqim tashqarisida — fayl/rasm/stiker kabi qo'llab-quvvatlanmaydigan xabar
    await message.answer(
        "Men hozircha faqat <b>matnli</b> xabarlarni tushunaman 🙂\n"
        "Pastdagi menyudan tanlang yoki yozing 👇",
        reply_markup=main_menu,
    )
