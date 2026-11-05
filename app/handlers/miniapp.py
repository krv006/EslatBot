"""Mini App ochish — /app komandasi va inline tugma.

WEBAPP_URL berilgan bo'lsa (domen sozlangan), foydalanuvchiga Mini App'ni
ochadigan tugma yuboradi. Asosiy kirish — chatdagi "menyu" tugmasi (input
yonida), u main.py da o'rnatiladi.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.config import WEBAPP_URL

router = Router()


def webapp_kb() -> InlineKeyboardMarkup | None:
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Mini App'ni ochish",
                             web_app=WebAppInfo(url=WEBAPP_URL)),
    ]])


@router.message(Command("app"))
async def cmd_app(message: Message):
    kb = webapp_kb()
    if not kb:
        await message.answer(
            "Mini App hozircha sozlanmagan. (Administrator: .env da DOMAIN yoki "
            "WEBAPP_URL ni to'ldiring.)"
        )
        return
    await message.answer(
        "📱 <b>EslatBot Mini App</b>\n\n"
        "Eslatma, vazifa, qayd va materiallaringizni qulay ilovada boshqaring — "
        "pastdagi tugmani bosing yoki chatdagi <b>menyu</b> tugmasidan oching 👇",
        reply_markup=kb,
    )
