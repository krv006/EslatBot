"""Xabar formatlash yordamchilari."""
from html import escape


def esc(value) -> str:
    """Foydalanuvchi matnini HTML parse_mode uchun xavfsiz qiladi.

    Usersiz kiritilgan matnda < > & bo'lsa, Telegram xabari buzilmaydi
    va HTML-injection oldi olinadi.
    """
    return escape(str(value), quote=False)
