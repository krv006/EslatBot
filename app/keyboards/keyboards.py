"""Barcha tugmalar (reply va inline klaviaturalar)."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.utils.parser import WEEKDAY_NAMES

BTN_NEW = "➕ Yangi eslatma"
BTN_LIST = "📋 Eslatmalarim"
BTN_PLAN = "📝 Kunlik reja"
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_REFERRAL = "📤 Referal"
BTN_SKIP = "⏭ O'tkazib yuborish"
BTN_SHARE_PHONE = "📱 Raqamni ulashish"

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_LIST)],
        [KeyboardButton(text=BTN_PLAN), KeyboardButton(text=BTN_SETTINGS)],
        [KeyboardButton(text=BTN_REFERRAL)],
    ],
    resize_keyboard=True,
)


def settings_kb(user: dict) -> InlineKeyboardMarkup:
    """Sozlamalar: ertalabki kun rejasi (digest)."""
    dg_on = bool(user.get("digest_enabled"))
    dg_h = user.get("digest_hour") if user.get("digest_hour") is not None else 7
    dg_m = user.get("digest_minute") or 0
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🌅 Ertalabki reja: {'✅' if dg_on else '🔕'}",
                callback_data="dg_toggle",
            ),
             InlineKeyboardButton(
                text=f"🕖 {dg_h:02d}:{dg_m:02d}",
                callback_data="dg_time",
            )],
        ]
    )


BTN_PLAN_DONE = "✅ Tayyor"

plan_done_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_PLAN_DONE)]],
    resize_keyboard=True,
)


def time_quick_kb(prefix: str,
                  after: tuple[int, int] | None = None) -> InlineKeyboardMarkup:
    """Ommabop vaqtlar — bir tegishda tanlash. `prefix` har oqim uchun har xil
    (ntm=yangi, etm=tahrir, dtm=digest, rtm=referal). Foydalanuvchi baribir
    o'zi yozishi ham mumkin. `after` berilsa, o'tib ketgan vaqt tugmalari
    ko'rsatilmaydi ("bugun"ga kech soatda tanlab bo'lmaydigan tugma qolmasin).
    """
    times = [
        (6, 0), (7, 0), (8, 0),
        (9, 0), (12, 0), (15, 0),
        (18, 0), (20, 0), (21, 0),
    ]
    rows, row = [], []
    for h, m in times:
        if after is not None and (h, m) <= after:
            continue
        row.append(InlineKeyboardButton(
            text=f"🕒 {h:02d}:{m:02d}", callback_data=f"{prefix}:{h}:{m}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def name_confirm_kb(tg_name: str) -> ReplyKeyboardMarkup:
    """Ro'yxatdan o'tishda: TG'dagi ismni tasdiqlash yoki yangisini yozish."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"✅ {tg_name}")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Ismingizni yozing yoki tugmani bosing",
    )


phone_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_SHARE_PHONE, request_contact=True)],
        [KeyboardButton(text=BTN_SKIP)],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

freq_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📌 Bir marta", callback_data="freq:once")],
        [InlineKeyboardButton(text="📅 Har kuni", callback_data="freq:daily")],
        [InlineKeyboardButton(text="🔁 Kun ora", callback_data="freq:every2")],
        [InlineKeyboardButton(text="📆 Haftada bir", callback_data="freq:weekly")],
        [InlineKeyboardButton(text="🗓 Oyda bir", callback_data="freq:monthly")],
    ]
)

once_day_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📍 Bugun", callback_data="od:0"),
            InlineKeyboardButton(text="🌅 Ertaga", callback_data="od:1"),
            InlineKeyboardButton(text="⏩ Indinga", callback_data="od:2"),
        ]
    ]
)

weekday_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=WEEKDAY_NAMES[i], callback_data=f"wd:{i}")
         for i in range(0, 4)],
        [InlineKeyboardButton(text=WEEKDAY_NAMES[i], callback_data=f"wd:{i}")
         for i in range(4, 7)],
    ]
)


def reminder_fired_kb(reminder_id: int) -> InlineKeyboardMarkup:
    """Eslatma kelganda chiqadigan tugmalar: bajarildi + moslashuvchan snooze."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"done:{reminder_id}")],
            [
                InlineKeyboardButton(text="⏰ 10 daq", callback_data=f"snz:{reminder_id}:10"),
                InlineKeyboardButton(text="⏰ 30 daq", callback_data=f"snz:{reminder_id}:30"),
                InlineKeyboardButton(text="⏰ 1 soat", callback_data=f"snz:{reminder_id}:60"),
                InlineKeyboardButton(text="🌅 Ertaga", callback_data=f"snz:{reminder_id}:tomorrow"),
            ],
        ]
    )


def reminder_manage_kb(reminder_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton(text="⏸ To'xtatish", callback_data=f"toggle:{reminder_id}:0")
        if is_active
        else InlineKeyboardButton(text="▶️ Yoqish", callback_data=f"toggle:{reminder_id}:1")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit:{reminder_id}"),
             InlineKeyboardButton(text="📤 Referal", callback_data=f"ref:{reminder_id}")],
            [toggle, InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del:{reminder_id}")],
        ]
    )


def referral_share_kb(link: str) -> InlineKeyboardMarkup:
    """Referal linkini Telegram orqali ulashish tugmasi."""
    share_url = f"https://t.me/share/url?url={link}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📨 Telegram orqali ulashish", url=share_url)],
        ]
    )


def referral_received_kb(reminder_id: int) -> InlineKeyboardMarkup:
    """Referal qabul qilingan eslatma ostidagi 'Kerak emas' tugmasi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Kerak emas", callback_data=f"refdel:{reminder_id}")],
        ]
    )


def edit_menu_kb(reminder_id: int) -> InlineKeyboardMarkup:
    """«Tahrirlash» bosilganda: nimani o'zgartirishni tanlash."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Matn", callback_data=f"e_text:{reminder_id}"),
                InlineKeyboardButton(text="🕒 Vaqt", callback_data=f"e_time:{reminder_id}"),
                InlineKeyboardButton(text="🔁 Takror", callback_data=f"e_freq:{reminder_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"e_back:{reminder_id}")],
        ]
    )


# Tahrirlashda takrorlanish turini tanlash (yangi eslatmadagi freq_kb'ning aynan o'zi)
edit_freq_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📌 Bir marta", callback_data="ef:once")],
        [InlineKeyboardButton(text="📅 Har kuni", callback_data="ef:daily")],
        [InlineKeyboardButton(text="🔁 Kun ora", callback_data="ef:every2")],
        [InlineKeyboardButton(text="📆 Haftada bir", callback_data="ef:weekly")],
        [InlineKeyboardButton(text="🗓 Oyda bir", callback_data="ef:monthly")],
    ]
)

edit_once_day_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📍 Bugun", callback_data="eod:0"),
            InlineKeyboardButton(text="🌅 Ertaga", callback_data="eod:1"),
            InlineKeyboardButton(text="⏩ Indinga", callback_data="eod:2"),
        ]
    ]
)

edit_weekday_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=WEEKDAY_NAMES[i], callback_data=f"ewd:{i}")
         for i in range(0, 4)],
        [InlineKeyboardButton(text=WEEKDAY_NAMES[i], callback_data=f"ewd:{i}")
         for i in range(4, 7)],
    ]
)
