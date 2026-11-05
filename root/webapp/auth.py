"""Telegram Mini App — initData'ni tekshirish (xavfsizlik).

Telegram WebApp ochilganda brauzerga imzolangan `initData` qatorini beradi.
Uni bot tokeni bilan HMAC-SHA256 orqali tekshiramiz — shunda so'rov haqiqatan
ham o'sha foydalanuvchidan, Telegram orqali kelganiga ishonch hosil qilamiz.
Parol/token kiritish shart emas — imzo o'zi autentifikatsiya.

Algoritm (Telegram hujjatlari):
  secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)
  data_check_string — 'hash'dan boshqa barcha kalit=qiymat juftlari alifbo
  tartibida '\n' bilan birlashtirilgan.
"""
import hashlib
import hmac
import json
import time
from functools import wraps
from urllib.parse import parse_qsl

from django.conf import settings
from django.http import JsonResponse

# initData shuncha soniyadan eski bo'lsa — rad etiladi (takroriy hujumga qarshi)
MAX_AGE_SECONDS = 24 * 60 * 60


def _err(message: str, status: int = 401) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """initData to'g'ri imzolangan bo'lsa — Telegram foydalanuvchi dict'ini,
    aks holda None qaytaradi."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs)
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calc_hash, received_hash):
        return None

    # Eskirganini rad etamiz
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if auth_date and (time.time() - auth_date) > MAX_AGE_SECONDS:
        return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user


def _extract_init_data(request) -> str:
    """initData'ni sarlavhadan oladi: 'Authorization: tma <initData>'.
    Ishlab chiqishda query/post orqali ham qabul qilinadi (DEBUG)."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("tma "):
        return auth[4:]
    # Zaxira: ba'zi klientlar X-sarlavha yuboradi
    x = request.headers.get("X-Telegram-Init-Data")
    if x:
        return x
    if settings.DEBUG:
        return request.GET.get("initData") or request.POST.get("initData") or ""
    return ""


def require_tma(view):
    """Dekorator: initData'ni tekshiradi, BotUser'ni topadi/yaratadi va
    request.bot_user / request.tg_user ga qo'yadi."""
    from panel.models import BotUser  # kech import (ilova yuklangach)

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        init_data = _extract_init_data(request)
        tg_user = validate_init_data(init_data, settings.BOT_TOKEN)
        if not tg_user:
            return _err("Autentifikatsiya amalga oshmadi (initData yaroqsiz).")

        tg_id = int(tg_user["id"])
        bot_user = BotUser.objects.filter(tg_id=tg_id).first()
        if bot_user is None:
            # Botni /start qilmagan bo'lsa ham Mini App ishlashi uchun yaratamiz
            from django.utils import timezone
            bot_user = BotUser.objects.create(
                tg_id=tg_id,
                name=tg_user.get("first_name") or "",
                last_name=tg_user.get("last_name") or "",
                username=tg_user.get("username") or "",
                language_code=tg_user.get("language_code") or "",
                is_premium=bool(tg_user.get("is_premium")),
                registered=True,
                created_at=timezone.localtime().replace(tzinfo=None),
            )
        request.bot_user = bot_user
        request.tg_user = tg_user
        return view(request, *args, **kwargs)

    return wrapper
