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

main_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_LIST)]],
    resize_keyboard=True,
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
