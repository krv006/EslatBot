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
    BTN_PLAN_DONE,
    BTN_REFERRAL,
    BTN_SETTINGS,
    BTN_SKIP,
    referral_received_kb,
    referral_share_kb,
    time_quick_kb,
)
from app.scheduler.scheduler import (
    TZ,
    first_run_date,
    once_start,
    schedule_digest,
    schedule_reminder,
    unschedule_reminder,
)
from app.utils.ai import ai_available, ai_parse_reminder
from app.utils.fmt import esc
from app.utils.guards import get_owned_reminder
from app.utils.parser import WEEKDAY_NAMES, describe, parse_text, parse_time
from app.utils.stt import voice_to_text

logger = logging.getLogger(__name__)

router = Router()

# Bu router ro'yxatda birinchi turadi, shuning uchun referal holatida ham
# menyu tugmalari va buyruqlar o'z handlerlariga yetib borishi kerak:
#  - _PASS_BTNS — boshqa oqimlarning reply-tugmalari (shu jumladan boshqa
#    klaviaturalardan qolgan ⏭/✅ tugmalari) referal matni bo'lib qolmasin;
#  - _KNOWN_CMDS — botda mavjud buyruqlar (/cancel start.py'da tozalaydi).
_PASS_BTNS = {BTN_NEW, BTN_LIST, BTN_PLAN, BTN_SETTINGS, BTN_REFERRAL,
              BTN_SKIP, BTN_PLAN_DONE}
_KNOWN_CMDS = {"/start", "/new", "/list", "/help", "/cancel"}
_PLAIN_TEXT = (F.text, ~F.text.startswith("/"), ~F.text.in_(_PASS_BTNS))


def _is_known_cmd(text: str) -> bool:
    """'/start ref_x' yoki '/cancel@EslatBot' ko'rinishlarini ham taniydi."""
    return text.split()[0].split("@")[0] in _KNOWN_CMDS


class Referral(StatesGroup):
    text = State()   # ulashiladigan eslatma matnini kutish
    time_ = State()  # matnda vaqt topilmasa — vaqtni kutish


async def _not_registering(message: Message, state: FSMContext) -> bool:
    """Ro'yxatdan o'tish tugamagan userni bu oqim «o'g'irlab» ketmasin —
    aks holda start.py'dagi Registration holati (va deep-link'dan kelgan
    pending_ref_token) yo'qolib qoladi."""
    current = await state.get_state()
    return not (current or "").startswith("Registration")


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


async def _send_link(message: Message, ref: dict, note: str = "") -> None:
    """Referal yozuvini yaratib, ulashish linkini yuboradi."""
    token = _new_token()
    await db.create_referral(ref["from_user_id"], ref, token)
    me = await message.bot.me()  # keshlangan — har safar API'ga bormaydi
    link = f"https://t.me/{me.username}?start=ref_{token}"

    await message.answer(
        "📤 <b>Referal tayyor!</b>\n\n"
        f"📝 <b>{esc(ref['text'])}</b>\n🕒 {_when(ref)}\n\n"
        f"🔗 <b>Ulashish linki:</b>\n<code>{link}</code>\n\n"
        "Linkni <b>bitta</b> odamga yuboring — u ochishi bilan eslatma unga "
        "avtomatik qo'shiladi. <i>(Havola bir martalik: bir kishi qabul "
        f"qilgach kuchini yo'qotadi.)</i>{note}",
        reply_markup=referral_share_kb(link),
    )


async def _finalize(message: Message, state: FSMContext) -> None:
    """State'dagi ma'lumotlardan referal yasaydi; 'once' vaqti o'tgan bo'lsa qayta so'raydi."""
    data = await state.get_data()

    freq = data["freq"]
    weekday = data.get("weekday")
    monthday = data.get("monthday")
    start_date = None
    note = ""
    now = datetime.now(TZ)

    if freq == "once":
        dt = once_start(data)
        if dt <= now:
            await state.set_state(Referral.time_)
            await message.answer(
                "⚠️ Bu vaqt allaqachon o'tib ketdi 😅\n"
                "Hozirdan keyingi vaqtni tanlang yoki yozing (masalan <b>21:30</b>), "
                "bekor qilish uchun /cancel 👇",
                reply_markup=time_quick_kb("rtm", after=(now.hour, now.minute)),
            )
            return
        start_date = dt.isoformat()
    elif freq == "every2":
        start_date = first_run_date(data["hour"], data["minute"]).isoformat()
    elif freq == "weekly" and weekday is None:
        weekday = now.weekday()
        note = (f"\n\nℹ️ Hafta kuni aytilmagani uchun <b>{WEEKDAY_NAMES[weekday].lower()}</b> "
                "tanlandi. Boshqa kun kerak bo'lsa, matnda yozing (masalan «har juma»).")
    elif freq == "monthly" and monthday is None:
        monthday = now.day
        note = (f"\n\nℹ️ Oy kuni aytilmagani uchun <b>{monthday}-kun</b> tanlandi. "
                "Boshqa kun kerak bo'lsa, matnda yozing (masalan «har oyning 15-kuni»).")

    if freq == "monthly" and monthday is not None and monthday > 28:
        note += (f"\n\n⚠️ Ba'zi oylarda {monthday}-kun yo'q — bunday oylarda "
                 "eslatma kelmaydi.")

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
    }, note=note)


# --- Menyudagi «📤 Referal»: xabarni shu yerda yozish ---

@router.message(F.text == BTN_REFERRAL, _not_registering)
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


@router.message(Referral.text, *_PLAIN_TEXT)
async def got_referral_text(message: Message, state: FSMContext):
    await _handle_referral_text(message, state, message.text)


@router.message(Referral.text, F.voice)
async def got_referral_voice(message: Message, state: FSMContext):
    """Ovozli xabar — matnga aylantirib, xuddi yozilgandek qayta ishlaymiz."""
    text = await voice_to_text(message)
    if not text:
        return
    # AI (Gemini) bilan chuqur tahlil; ishlamasa oddiy regex'ga o'tadi
    parsed = await ai_parse_reminder(text) if ai_available() else None
    await _handle_referral_text(message, state, text, parsed=parsed)


async def _handle_referral_text(message: Message, state: FSMContext, raw: str,
                                parsed: dict | None = None):
    if parsed is None:
        parsed = parse_text(raw)
    if not parsed["text"]:
        # Faqat vaqt yozilgan ("ertaga soat 10 da") — matnsiz eslatma bo'lmaydi
        await message.answer(
            "Eslatma matnini ham yozing ✍️ Masalan:\n"
            "<i>«ertaga 10:00 da uchrashuv»</i>"
        )
        return
    user_db_id = await db.upsert_user(message.from_user)
    await state.update_data(
        user_db_id=user_db_id,
        text=parsed["text"],
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


@router.message(Referral.time_, *_PLAIN_TEXT)
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


# Holat allaqachon tugagan (bekor qilingan/yakunlangan) bo'lsa, eski xabarda
# qolgan 🕒 tugma "aylanib" turmasin
@router.callback_query(F.data.startswith("rtm:"))
async def stale_time_btn(callback: CallbackQuery):
    await callback.answer("Bu tugma eskirgan 😅 Qaytadan 📤 Referal bosing.")


# Referal holatida noma'lum buyruq yoki matn bo'lmagan kontent (rasm, stiker,
# kontakt...) kelsa — jim qolmaymiz, yo'l ko'rsatamiz
@router.message(Referral.text, F.text.startswith("/"), ~F.text.func(_is_known_cmd))
@router.message(Referral.time_, F.text.startswith("/"), ~F.text.func(_is_known_cmd))
async def referral_unknown_cmd(message: Message):
    await message.answer(
        "Bunday buyruqni bilmayman 😅 Referalni bekor qilish uchun /cancel yozing."
    )


@router.message(Referral.text, ~F.text)
@router.message(Referral.time_, ~F.text)
async def referral_other_content(message: Message):
    await message.answer(
        "Iltimos, yozib yuboring ✍️ (ovozli xabar ham bo'ladi)\n"
        "Bekor qilish uchun /cancel yozing."
    )


# --- Tayyor eslatma ostidagi «📤 Referal» tugmasi ---

@router.callback_query(F.data.startswith("ref:"))
async def start_referral(callback: CallbackQuery, state: FSMContext):
    rid = int(callback.data.split(":")[1])
    rem = await get_owned_reminder(callback, rid)
    if not rem:
        return

    # Vaqti o'tib ketgan bir martalik eslatmani ulashishdan foyda yo'q —
    # qabul qiluvchiga darhol "o'chirilgan" eslatma borar edi
    if rem["freq"] == "once" and rem["start_date"]:
        try:
            if datetime.fromisoformat(rem["start_date"]) <= datetime.now(TZ):
                await callback.answer(
                    "Bu eslatmaning vaqti o'tib ketgan — avval ✏️ Tahrirlash "
                    "orqali vaqtini yangilang.",
                    show_alert=True,
                )
                return
        except ValueError:
            pass

    await state.clear()
    await _send_link(callback.message, {**rem, "from_user_id": rem["user_id"]})
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
