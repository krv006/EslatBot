"""/start, /help va sodda ro'yxatdan o'tish (ism + telefon)."""
from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.database import db
from app.handlers.referral import deliver_referral
from app.keyboards.keyboards import (
    BTN_SKIP,
    main_menu,
    name_confirm_kb,
    phone_kb,
)
from app.scheduler.scheduler import schedule_digest
from app.utils.fmt import esc

router = Router()

HELP_TEXT = (
    "Men eslatma botiman — unutmasligingiz uchun yordam beraman! 🧠\n\n"
    "<b>Qanday ishlataman?</b>\n"
    "1️⃣ <b>➕ Yangi eslatma</b> tugmasini bosing — men bosqichma-bosqich so'rayman.\n"
    "2️⃣ Yoki shunchaki <b>erkin yozing</b>, o'zim tushunaman:\n\n"
    "   • <i>ertaga 15:00 uchrashuv</i>\n"
    "   • <i>har kuni soat 8 da dori ichishni eslat</i>\n"
    "   • <i>kun ora 21:30 kitob o'qish</i>\n"
    "   • <i>har juma 10 da mashg'ulot</i>\n"
    "   • <i>har oyning 15-kuni 9:00 kvartira puli</i>\n\n"
    "🎙 Yozishga erinsangiz — <b>ovozli xabar</b> yuboring, o'zim tushunaman!\n\n"
    "📝 <b>Kunlik reja</b> — bugun/ertaga uchun bir nechta rejani "
    "birdan qatorlab yozasiz.\n"
    "📋 <b>Eslatmalarim</b> — ro'yxatni ko'rish, tahrirlash, to'xtatish yoki o'chirish.\n\n"
    "<b>Komandalar:</b> /new — yangi, /list — ro'yxat, "
    "/cancel — amalni bekor qilish, /help — shu yordam."
)


class Registration(StatesGroup):
    name = State()
    phone = State()


async def _apply_ref_token(bot, token: str, tg_id: int) -> None:
    """Deep-link orqali kelgan referalni foydalanuvchiga yetkazadi."""
    referral = await db.get_referral_by_token(token)
    if not referral:
        return
    target = await db.get_user(tg_id)
    if not target:
        return
    status = await deliver_referral(bot, referral, target["id"], notify_referrer=True)
    if status == "self":
        await bot.send_message(
            tg_id,
            "🙂 Bu sizning o'z referal havolangiz — uni boshqa odamga yuboring.",
        )
    elif status == "used":
        await bot.send_message(
            tg_id,
            "⚠️ Bu referal havolasi allaqachon ishlatilgan — u bir martalik edi. "
            "Eslatma egasidan yangi havola so'rang.",
        )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    await db.upsert_user(message.from_user)
    user = await db.get_user(message.from_user.id)
    tg_name = message.from_user.first_name or "do'stim"

    # Deep-link: t.me/bot?start=ref_<token>
    payload = command.args or ""
    ref_token = payload[4:] if payload.startswith("ref_") else None

    # Avval ro'yxatdan o'tgan bo'lsa — to'g'ridan-to'g'ri menyu
    if user and user.get("registered"):
        await message.answer(
            f"Yana xush kelibsiz, <b>{esc(user.get('name') or tg_name)}</b>! 👋\n\n"
            + HELP_TEXT,
            reply_markup=main_menu,
        )
        if ref_token:
            await _apply_ref_token(message.bot, ref_token, message.from_user.id)
        return

    # Sodda ro'yxatdan o'tish: 1) ism  2) telefon
    await state.set_state(Registration.name)
    if ref_token:
        # Ro'yxatdan o'tib bo'lgach referalni qo'llash uchun eslab qolamiz
        await state.update_data(pending_ref_token=ref_token)
    await message.answer(
        f"Assalomu alaykum, <b>{esc(tg_name)}</b>! 👋\n"
        f"Men <b>EslatBot</b>man — muhim ishlaringizni unutmasligingizga yordam beraman.\n\n"
        f"Avval qisqa tanishib olaylik. <b>Ismingiz nima?</b>\n"
        f"Yozing yoki pastdagi tugmani bosing 👇",
        reply_markup=name_confirm_kb(tg_name),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Istalgan bosqichdagi amalni bekor qilib, menyuga qaytaradi."""
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.answer("Bekor qiladigan amal yo'q 🙂", reply_markup=main_menu)
    else:
        await message.answer(
            "❌ Bekor qilindi. Bosh menyudasiz — yangi eslatma qo'shishingiz mumkin 👇",
            reply_markup=main_menu,
        )


@router.message(Registration.name, F.text)
async def reg_name(message: Message, state: FSMContext):
    name = message.text.strip().removeprefix("✅").strip()
    if not name or len(name) > 100:
        await message.answer("Iltimos, ismingizni yozing 😊")
        return
    await db.set_name(message.from_user.id, name)
    await state.set_state(Registration.phone)
    await message.answer(
        f"Juda yaxshi, <b>{esc(name)}</b>! 🤝\n\n"
        f"Endi telefon raqamingizni ulashsangiz bo'ladi "
        f"(ixtiyoriy — o'tkazib yuborishingiz ham mumkin) 👇",
        reply_markup=phone_kb,
    )


@router.message(Registration.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    # Faqat o'zining raqamini qabul qilamiz
    if message.contact.user_id != message.from_user.id:
        await message.answer(
            "Bu boshqa odamning kontakti 🙂 Iltimos, tugma orqali "
            "o'zingizning raqamingizni yuboring yoki o'tkazib yuboring.",
            reply_markup=phone_kb,
        )
        return
    await db.set_phone(message.from_user.id, message.contact.phone_number)
    await _finish_registration(message, state, phone_saved=True)


@router.message(Registration.phone, F.text == BTN_SKIP)
async def reg_skip_phone(message: Message, state: FSMContext):
    await _finish_registration(message, state, phone_saved=False)


@router.message(Registration.phone)
async def reg_phone_other(message: Message):
    await message.answer(
        "Iltimos, pastdagi <b>📱 Raqamni ulashish</b> tugmasini bosing "
        "yoki <b>⏭ O'tkazib yuborish</b>ni tanlang 👇",
        reply_markup=phone_kb,
    )


async def _finish_registration(message: Message, state: FSMContext, phone_saved: bool):
    # State tozalanishidan oldin kutilayotgan referal tokenini olamiz
    data = await state.get_data()
    ref_token = data.get("pending_ref_token")

    await db.set_registered(message.from_user.id)
    await state.clear()

    # Ertalabki kun rejasini jadvalga qo'shamiz
    user = await db.get_user(message.from_user.id)
    if user:
        schedule_digest(message.bot, user)

    extra = "📱 Raqamingiz saqlandi!\n\n" if phone_saved else ""
    await message.answer(
        f"✅ <b>Ro'yxatdan o'tdingiz!</b> {extra}\n" + HELP_TEXT + "\n\n"
        "🌅 <b>Bonus:</b> har kuni ertalab <b>07:00</b> da bugungi rejalaringizni "
        "bitta xabarda yuboraman (vaqtini <b>⚙️ Sozlamalar</b>dan o'zgartirasiz).",
        reply_markup=main_menu,
    )

    # Link orqali kelgan bo'lsa — referal eslatmasini endi qo'shamiz
    if ref_token:
        await _apply_ref_token(message.bot, ref_token, message.from_user.id)


# Ro'yxatdan o'tib bo'lgach ham kontakt yuborsa — saqlab qo'yamiz
@router.message(F.contact)
async def any_contact(message: Message):
    if message.contact.user_id == message.from_user.id:
        await db.set_phone(message.from_user.id, message.contact.phone_number)
        await message.answer("📱 Raqamingiz saqlandi!", reply_markup=main_menu)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=main_menu)
