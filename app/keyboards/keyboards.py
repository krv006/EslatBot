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
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_SKIP = "⏭ O'tkazib yuborish"
BTN_SHARE_PHONE = "📱 Raqamni ulashish"

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_LIST)],
        [KeyboardButton(text=BTN_SETTINGS)],
    ],
    resize_keyboard=True,
)


def digest_settings_kb(enabled: bool, hour: int, minute: int) -> InlineKeyboardMarkup:
    """Ertalabki reja (digest) sozlamalari."""
    toggle_text = "🔕 O'chirish" if enabled else "🔔 Yoqish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="dg_toggle")],
            [InlineKeyboardButton(
                text=f"🕖 Vaqtini o'zgartirish ({hour:02d}:{minute:02d})",
                callback_data="dg_time",
            )],
        ]
    )


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
        [InlineKeyboardButton(text="📅 Har kuni", callback_data="freq:daily")],
        [InlineKeyboardButton(text="🔁 Kun ora", callback_data="freq:every2")],
        [InlineKeyboardButton(text="📆 Haftada bir", callback_data="freq:weekly")],
        [InlineKeyboardButton(text="🗓 Oyda bir", callback_data="freq:monthly")],
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
    """Eslatma kelganda chiqadigan tugmalar."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"done:{reminder_id}"),
                InlineKeyboardButton(text="⏰ +10 daqiqa", callback_data=f"snooze:{reminder_id}"),
            ]
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
            [toggle, InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del:{reminder_id}")]
        ]
    )
