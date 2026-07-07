"""/start va /help buyruqlari."""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.database import db
from app.keyboards.keyboards import main_menu

router = Router()

HELP_TEXT = (
    "Men eslatma botiman — unutmasligingiz uchun yordam beraman! 🧠\n\n"
    "<b>Qanday ishlataman?</b>\n"
    "1️⃣ <b>➕ Yangi eslatma</b> tugmasini bosing — men bosqichma-bosqich so'rayman.\n"
    "2️⃣ Yoki shunchaki <b>erkin yozing</b>, o'zim tushunaman:\n\n"
    "   • <i>har kuni soat 8 da dori ichishni eslat</i>\n"
    "   • <i>kun ora 21:30 kitob o'qish</i>\n"
    "   • <i>har juma 10 da mashg'ulot</i>\n"
    "   • <i>har oyning 15-kuni 9:00 kvartira puli</i>\n\n"
    "📋 <b>Eslatmalarim</b> — ro'yxatni ko'rish, to'xtatish yoki o'chirish."
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name or "do'stim"
    await db.get_or_create_user(message.from_user.id, name)
    await message.answer(
        f"Assalomu alaykum, <b>{name}</b>! 👋\n\n" + HELP_TEXT,
        reply_markup=main_menu,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=main_menu)
