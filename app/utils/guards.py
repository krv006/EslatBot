"""Callback xavfsizligi — eslatma egasini tekshirish.

Callback ma'lumoti (masalan "del:5") foydalanuvchi tomonidan soxtalashtirilishi
mumkin. Egalik tekshirilmasa, kimdir boshqa odamning eslatmasini o'chirishi/
o'zgartirishi mumkin. Shu yordamchi har bir eslatma-callback'ida chaqiriladi.
"""
from aiogram.types import CallbackQuery

from app.database import db


async def get_owned_reminder(callback: CallbackQuery, reminder_id: int) -> dict | None:
    """Eslatmani qaytaradi, faqat agar u callback bosgan userga tegishli bo'lsa.

    Aks holda ogohlantirib None qaytaradi (chaqiruvchi darhol return qilishi kerak).
    """
    rem = await db.get_reminder(reminder_id)
    if not rem or rem["tg_id"] != callback.from_user.id:
        await callback.answer(
            "Bu eslatma topilmadi yoki sizga tegishli emas 🤷", show_alert=True
        )
        return None
    return rem
