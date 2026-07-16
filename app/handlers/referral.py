"""Referal — eslatmani boshqa odamga ulashish.

Oqim:
  1. User o'z eslatmasi ostidagi «📤 Referal» tugmasini bosadi (yoki menyudagi
     «📤 Referal» bo'limidan eslatma tanlaydi).
  2. Bot ulashish linki beradi (istalgan odamga yuborsa bo'ladi) + kontakt so'raydi.
  3. Agar user qabul qiluvchining kontaktini yuborsa va u BAZAMIZDA bo'lsa —
     eslatma unga to'g'ridan-to'g'ri avtomatik qo'shiladi va u xabardor qilinadi.
  4. Agar bazada bo'lmasa — link orqali ochib, ro'yxatdan o'tgach avtomatik qo'shiladi
     (bu qismini start.py deep-link orqali bajaradi).
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
    BTN_REFERRAL,
    main_menu,
    referral_list_kb,
    referral_received_kb,
    referral_share_kb,
)
from app.scheduler.scheduler import (
    TZ,
    schedule_digest,
    schedule_reminder,
    unschedule_reminder,
)
from app.utils.fmt import esc
from app.utils.parser import describe

logger = logging.getLogger(__name__)

router = Router()


class Referral(StatesGroup):
    target = State()  # qabul qiluvchi kontaktini kutish (ixtiyoriy)


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


# --- Referalni boshlash (eslatma ostidagi yoki menyudagi tugma) ---

@router.callback_query(F.data.startswith("ref:"))
async def start_referral(callback: CallbackQuery, state: FSMContext):
    rid = int(callback.data.split(":")[1])
    rem = await db.get_reminder(rid)
    if not rem or rem["tg_id"] != callback.from_user.id:
        await callback.answer("Eslatma topilmadi", show_alert=True)
        return

    token = _new_token()
    await db.create_referral(rem["user_id"], rem, token)
    me = await callback.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{token}"

    await state.set_state(Referral.target)
    await state.update_data(ref_token=token)

    when = describe(rem["freq"], rem["weekday"], rem["monthday"],
                    rem["hour"], rem["minute"], start_date=rem["start_date"])
    await callback.message.answer(
        "📤 <b>Referal</b>\n\n"
        f"📝 <b>{esc(rem['text'])}</b>\n🕒 {when}\n\n"
        "Bu eslatmani boshqa odamga yuborishingiz mumkin 👇\n\n"
        f"🔗 <b>Ulashish linki:</b>\n<code>{link}</code>\n\n"
        "Linkni <b>bitta</b> odamga yuboring — u ochib, ro'yxatga qo'shilgach "
        "eslatma unga avtomatik qo'shiladi. <i>(Havola bir martalik: bir kishi "
        "qabul qilgach kuchini yo'qotadi.)</i>\n\n"
        "📱 <b>Yoki</b> qabul qiluvchining <b>kontaktini yuboring</b> "
        "(📎 → Kontakt): agar u allaqachon botimizda bo'lsa, eslatma unga "
        "shu zahoti to'g'ridan-to'g'ri boradi.",
        reply_markup=referral_share_kb(link),
    )
    await callback.answer()


@router.message(F.text == BTN_REFERRAL)
async def referral_menu(message: Message, state: FSMContext):
    await state.clear()
    reminders = await db.get_user_reminders(message.from_user.id)
    if not reminders:
        await message.answer(
            "📤 <b>Referal</b> — eslatmangizni boshqa odamga yuborish imkoni.\n\n"
            "Avval o'zingizga bitta eslatma yarating (<b>➕ Yangi eslatma</b>), "
            "so'ngra shu yerdan yoki ro'yxatdagi <b>📤 Referal</b> tugmasi orqali ulashing.",
            reply_markup=main_menu,
        )
        return
    await message.answer(
        "📤 <b>Referal</b>\n\nQaysi eslatmani ulashamiz? Ro'yxatdan tanlang 👇",
        reply_markup=referral_list_kb(reminders),
    )


# --- Qabul qiluvchi kontakti yuborilganda (to'g'ridan-to'g'ri yuborish) ---

@router.message(Referral.target, F.contact)
async def got_target_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data.get("ref_token")
    await state.clear()

    referral = await db.get_referral_by_token(token) if token else None
    if not referral:
        await message.answer(
            "Referal topilmadi 😅 Qaytadan urinib ko'ring.", reply_markup=main_menu
        )
        return

    contact = message.contact
    target = None
    if contact.user_id:
        target = await db.get_user(contact.user_id)
    if not target and contact.phone_number:
        target = await db.get_user_by_phone(contact.phone_number)

    if not target:
        name = contact.first_name or "Bu odam"
        await message.answer(
            f"🔍 <b>{esc(name)}</b> hali botimizda yo'q.\n\n"
            "Unga yuqoridagi <b>ulashish linkini</b> yuboring — u botni ochib, "
            "ro'yxatdan o'tgach eslatma avtomatik qo'shiladi. 👆",
            reply_markup=main_menu,
        )
        return

    status = await deliver_referral(message.bot, referral, target["id"],
                                    notify_referrer=False)
    if status == "self":
        await message.answer(
            "🙂 Bu eslatma allaqachon o'zingizda bor — o'zingizga referal qila olmaysiz.",
            reply_markup=main_menu,
        )
        return
    if status == "used":
        await message.answer(
            "⚠️ Bu referal allaqachon ishlatilgan (bir martalik). "
            "Qaytadan yubormoqchi bo'lsangiz, eslatma ostidagi <b>📤 Referal</b> "
            "tugmasini yana bosing.",
            reply_markup=main_menu,
        )
        return

    tname = target.get("name") or contact.first_name or "Foydalanuvchi"
    await message.answer(
        f"✅ Referal yuborildi! <b>{esc(tname)}</b> eslatmani oldi va "
        f"ro'yxatiga qo'shildi. 🎉",
        reply_markup=main_menu,
    )


# --- Qabul qiluvchi «Kerak emas» desa ---

@router.callback_query(F.data.startswith("refdel:"))
async def referral_decline(callback: CallbackQuery):
    rid = int(callback.data.split(":")[1])
    unschedule_reminder(rid)
    await db.delete_reminder(rid)
    await callback.message.edit_text("🗑 Eslatma o'chirildi — ro'yxatingizga qo'shilmadi.")
    await callback.answer("O'chirildi")
