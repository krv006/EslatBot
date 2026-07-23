"""Referal — eslatmani boshqa odamga ulashish.

Oqim:
  1. User menyudagi «📤 Referal» tugmasini bosadi va eslatma matnini SHU YERDA
     yozadi (o'ziga oldindan eslatma yaratish shart emas). Vaqti topilmasa,
     bot faqat vaqtni so'raydi.
  2. Bot shu xabar uchun ulashish linki yaratadi — istalgan odamga yuborsa bo'ladi.
  3. Qabul qiluvchi linkni ochib, ro'yxatdan o'tgach eslatma unga avtomatik
     qo'shiladi (bu qismini start.py deep-link orqali bajaradi).

O'z eslatmasi ostidagi «📤 Referal» tugmasi ham ishlaydi — tayyor eslatmadan
link yasab beradi.
"""
import logging
import secrets
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards.keyboards import (
    BTN_LIST,
    BTN_NEW,
    BTN_PLAN,
    BTN_REFERRAL,
    BTN_SETTINGS,
    referral_received_kb,
    referral_share_kb,
    time_quick_kb,
)
from app.scheduler.scheduler import (
    TZ,
    date_run_date,
    first_run_date,
    next_weekday_run_date,
    once_run_date,
    schedule_digest,
    schedule_reminder,
    unschedule_reminder,
)
from app.utils.fmt import esc
from app.utils.guards import get_owned_reminder
from app.utils.parser import describe, parse_text, parse_time
from app.utils.stt import stt_available, transcribe_voice

logger = logging.getLogger(__name__)

router = Router()

# Menyu tugmalari referal holatida ham ishlayverishi uchun ularni bu router
# ushlamaydi (router ro'yxatda birinchi turadi).
_MENU_BTNS = {BTN_NEW, BTN_LIST, BTN_PLAN, BTN_SETTINGS, BTN_REFERRAL}


class Referral(StatesGroup):
    text = State()   # ulashiladigan eslatma matnini kutish
    time_ = State()  # matnda vaqt topilmasa — vaqtni kutish


def _new_token() -> str:
    return secrets.token_urlsafe(8)


def _when(referral: dict) -> str:
    return describe(referral["freq"], referral["weekday"], referral["monthday"],
                    referral["hour"], referral["minute"], start_date=referral["start_date"])


async def _clone_and_schedule(bot, referral: dict, target_db_id: int) -> tuple[int, bool]:
    """Eslatmani qabul qiluvchi ro'yxatiga qo'shib, jadvalga qo'yadi.

    Qaytaradi: (yangi_reminder_id, passed) — passed=True bo'lsa bir martalik
    eslatma vaqti allaqachon o'tib ketgan.
    """
    rid = await db.add_reminder(
        user_id=target_db_id,
        text=referral["text"],
        freq=referral["freq"],
        hour=referral["hour"],
        minute=referral["minute"],
        weekday=referral["weekday"],
        monthday=referral["monthday"],
        start_date=referral["start_date"],
    )
    passed = False
    if referral["freq"] == "once" and referral["start_date"]:
        try:
            if datetime.fromisoformat(referral["start_date"]) <= datetime.now(TZ):
                passed = True
                await db.set_reminder_active(rid, False)
        except ValueError:
            pass
    if not passed:
        rem = await db.get_reminder(rid)
        schedule_reminder(bot, rem)
    target = await db.get_user_by_id(target_db_id)
    if target:
        schedule_digest(bot, target)
    return rid, passed


async def deliver_referral(bot, referral: dict, target_db_id: int,
                           notify_referrer: bool = True) -> str:
    """Referalni qabul qiluvchiga yetkazadi (avtomatik qo'shadi + xabar beradi).

    Qaytaradi: 'self' (o'ziga) | 'used' (link allaqachon ishlatilgan) | 'delivered'.
    """
    if target_db_id == referral["from_user_id"]:
        return "self"

    # Bir martalik: atomar band qilamiz. Band qilib bo'lmasa — allaqachon ishlatilgan.
    if not await db.try_claim_referral(referral["id"]):
        return "used"

    rid, passed = await _clone_and_schedule(bot, referral, target_db_id)
    target = await db.get_user_by_id(target_db_id)
    from_user = await db.get_user_by_id(referral["from_user_id"])
    from_name = (from_user.get("name") if from_user else None) or "Kimdir"

    note = ("\n\n⚠️ Bu vaqt allaqachon o'tib ketgan — kerak bo'lsa <b>📋 Eslatmalarim</b>dan "
            "yangilang."
            if passed else
            "\n\n✅ Ro'yxatingizga qo'shildi — vaqti kelganda albatta eslataman! 😉")

    if target:
        try:
            await bot.send_message(
                target["tg_id"],
                f"🎁 Sizga <b>{esc(from_name)}</b> eslatma yubordi!\n\n"
                f"📝 <b>{esc(referral['text'])}</b>\n🕒 {_when(referral)}{note}",
                reply_markup=referral_received_kb(rid),
            )
        except Exception:
            logger.exception("Referal qabul qiluvchiga yuborilmadi: rid=%s", rid)

    if notify_referrer and from_user:
        tname = (target.get("name") if target else None) or "Foydalanuvchi"
        try:
            await bot.send_message(
                from_user["tg_id"],
                f"🎉 <b>{esc(tname)}</b> sizning referalingizni qabul qildi!",
            )
        except Exception:
            pass

    return "delivered"


async def _send_link(message: Message, ref: dict) -> None:
    """Referal yozuvini yaratib, ulashish linkini yuboradi."""
    token = _new_token()
    await db.create_referral(ref["from_user_id"], ref, token)
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{token}"

    await message.answer(
        "📤 <b>Referal tayyor!</b>\n\n"
        f"📝 <b>{esc(ref['text'])}</b>\n🕒 {_when(ref)}\n\n"
        f"🔗 <b>Ulashish linki:</b>\n<code>{link}</code>\n\n"
        "Linkni <b>bitta</b> odamga yuboring — u ochishi bilan eslatma unga "
        "avtomatik qo'shiladi. <i>(Havola bir martalik: bir kishi qabul "
        "qilgach kuchini yo'qotadi.)</i>",
        reply_markup=referral_share_kb(link),
    )


async def _finalize(message: Message, state: FSMContext) -> None:
    """State'dagi ma'lumotlardan referal yasaydi; 'once' vaqti o'tgan bo'lsa qayta so'raydi."""
    data = await state.get_data()

    freq = data["freq"]
    weekday = data.get("weekday")
    monthday = data.get("monthday")
    start_date = None
    now = datetime.now(TZ)

    if freq == "once":
        if data.get("once_date") is not None:
            dt = date_run_date(data["once_date"], data["hour"], data["minute"])
        elif data.get("once_weekday") is not None:
            dt = next_weekday_run_date(data["once_weekday"], data["hour"], data["minute"])
        elif data.get("once_offset") is not None:
            dt = once_run_date(data["once_offset"], data["hour"], data["minute"])
        else:
            # Kun aytilmagan: bugun (vaqti kelmagan bo'lsa) yoki ertaga
            dt = first_run_date(data["hour"], data["minute"])
        if dt <= now:
            await state.set_state(Referral.time_)
            await state.update_data(hour=None, minute=None)
            await message.answer(
                "⚠️ Bu vaqt allaqachon o'tib ketdi 😅\n"
                "Boshqa vaqt tanlang yoki yozing (masalan <b>21:30</b>) 👇",
                reply_markup=time_quick_kb("rtm"),
            )
            return
        start_date = dt.isoformat()
    elif freq == "every2":
        start_date = first_run_date(data["hour"], data["minute"]).isoformat()
    elif freq == "weekly" and weekday is None:
        weekday = now.weekday()
    elif freq == "monthly" and monthday is None:
        monthday = now.day

    await state.clear()
    await _send_link(message, {
        "from_user_id": data["user_db_id"],
        "text": data["text"],
        "freq": freq,
        "weekday": weekday,
        "monthday": monthday,
        "hour": data["hour"],
        "minute": data["minute"],
        "start_date": start_date,
    })


# --- Menyudagi «📤 Referal»: xabarni shu yerda yozish ---

@router.message(F.text == BTN_REFERRAL)
async def referral_menu(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Referral.text)
    await message.answer(
        "📤 <b>Referal</b> — eslatmani boshqa odamga yuborish.\n\n"
        "Nimani eslatishim kerakligini shu yerga yozing ✍️\n\n"
        "<i>Maslahat: vaqtini ham qo'shib yozsangiz bo'ladi, masalan:\n"
        "«ertaga 10:00 da uchrashuv» yoki «har kuni 21:00 da dori ichish»</i>\n\n"
        "Bekor qilish uchun /cancel yozing."
    )


@router.message(Referral.text, F.text, ~F.text.startswith("/"),
                ~F.text.in_(_MENU_BTNS))
async def got_referral_text(message: Message, state: FSMContext):
    await _handle_referral_text(message, state, message.text)


@router.message(Referral.text, F.voice)
async def got_referral_voice(message: Message, state: FSMContext):
    """Ovozli xabar — matnga aylantirib, xuddi yozilgandek qayta ishlaymiz."""
    if not stt_available():
        await message.answer(
            "Ovozli xabarlarni hozircha tushunmayman 😅 Iltimos, yozib yuboring."
        )
        return
    if message.voice.duration > 120:
        await message.answer("Ovozli xabar juda uzun (2 daqiqagacha qabul qilaman) 😅")
        return
    wait_msg = await message.answer("🎙 Eshityapman...")
    text = await transcribe_voice(message.bot, message.voice.file_id)
    if not text:
        await wait_msg.edit_text(
            "Ovozni tushuna olmadim 😔 Qaytadan urinib ko'ring yoki yozib yuboring."
        )
        return
    await wait_msg.edit_text(f"🎙 Eshitdim: <i>«{esc(text)}»</i>")
    await _handle_referral_text(message, state, text)


async def _handle_referral_text(message: Message, state: FSMContext, raw: str):
    user_db_id = await db.upsert_user(message.from_user)
    parsed = parse_text(raw)
    await state.update_data(
        user_db_id=user_db_id,
        text=parsed["text"] or raw.strip(),
        # Takrorlanish aytilmagan bo'lsa — bir martalik deb olamiz (eng ko'p holat)
        freq=parsed["freq"] or "once",
        weekday=parsed["weekday"],
        monthday=parsed["monthday"],
        hour=parsed["hour"],
        minute=parsed["minute"],
        once_offset=parsed["once_offset"],
        once_weekday=parsed.get("once_weekday"),
        once_date=parsed.get("once_date"),
    )
    if parsed["hour"] is None:
        await state.set_state(Referral.time_)
        await message.answer(
            "Soat nechada eslatay? Tugmadan tanlang yoki o'zingiz yozing "
            "(masalan <b>07:30</b>) 👇",
            reply_markup=time_quick_kb("rtm"),
        )
        return
    await _finalize(message, state)


@router.message(Referral.time_, F.text, ~F.text.startswith("/"),
                ~F.text.in_(_MENU_BTNS))
async def got_referral_time(message: Message, state: FSMContext):
    parsed = parse_time(message.text)
    if parsed is None:
        await message.answer(
            "Vaqtni tushunmadim 😅 Tugmadan tanlang yoki shunday yozing: "
            "<b>09:00</b> yoki <b>21:30</b>",
            reply_markup=time_quick_kb("rtm"),
        )
        return
    await state.update_data(hour=parsed[0], minute=parsed[1])
    await _finalize(message, state)


@router.callback_query(Referral.time_, F.data.startswith("rtm:"))
async def got_referral_time_btn(callback: CallbackQuery, state: FSMContext):
    _, h, m = callback.data.split(":")
    await state.update_data(hour=int(h), minute=int(m))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finalize(callback.message, state)


# --- Tayyor eslatma ostidagi «📤 Referal» tugmasi ---

@router.callback_query(F.data.startswith("ref:"))
async def start_referral(callback: CallbackQuery, state: FSMContext):
    rid = int(callback.data.split(":")[1])
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return
    await state.clear()
    await _send_link(callback.message, {
        "from_user_id": rem["user_id"],
        "text": rem["text"],
        "freq": rem["freq"],
        "weekday": rem["weekday"],
        "monthday": rem["monthday"],
        "hour": rem["hour"],
        "minute": rem["minute"],
        "start_date": rem["start_date"],
    })
    await callback.answer()


# --- Qabul qiluvchi «Kerak emas» desa ---

@router.callback_query(F.data.startswith("refdel:"))
async def referral_decline(callback: CallbackQuery):
    rid = int(callback.data.split(":")[1])
    if not await get_owned_reminder(callback, rid):
        return
    unschedule_reminder(rid)
    await db.delete_reminder(rid)
    await callback.message.edit_text("🗑 Eslatma o'chirildi — ro'yxatingizga qo'shilmadi.")
    await callback.answer("O'chirildi")
