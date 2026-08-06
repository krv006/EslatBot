"""Django sozlamalari — faqat admin panel uchun.

Bot bilan bitta bazadan (eslatbot.db) foydalanadi:
bot jadvallari (users, reminders) Django tomonidan boshqarilmaydi (managed=False),
Django faqat o'zining auth/session jadvallarini qo'shadi.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# root/config/settings.py -> loyiha ildizi (EslatBot/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# Serverda .env orqali DJANGO_DEBUG=0 qilinadi
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-faqat-lokal-dev-uchun"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY .env faylida yo'q! Production'da majburiy."
        )

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = [
    o for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

# --- Xavfsizlik ---
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 soat

# HTTPS orqasida ishlaganda .env da DJANGO_HTTPS=1 qilinadi
if os.getenv("DJANGO_HTTPS", "0") == "1":
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    # jazzmin django.contrib.admin'dan OLDIN turishi shart (admin mavzusi)
    "jazzmin",
    # panel — o'zining maxsus shablonlari (dashboard: eslat_index.html) uchun
    "panel",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Whitenoise — static fayllarni Django o'zi beradi (tashqi serverga bog'liq emas)
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": PROJECT_ROOT / os.getenv("DB_NAME", "eslatbot.db"),
    }
}

LANGUAGE_CODE = "uz"
TIME_ZONE = os.getenv("TIMEZONE", "Asia/Tashkent")
USE_I18N = True
USE_TZ = False  # bot vaqtlarni mahalliy vaqtda saqlaydi

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =====================================================================
# Jazzmin — admin panel ko'rinishi (mavzu)
# =====================================================================
JAZZMIN_SETTINGS = {
    "site_title": "EslatBot",
    "site_header": "EslatBot",
    "site_brand": "🔔 EslatBot",
    "site_logo": None,
    "site_icon": "panel/favicon.png",
    "welcome_sign": "EslatBot — Boshqaruv paneli",
    "copyright": "EslatBot",
    "search_model": ["panel.BotUser", "panel.Reminder"],
    # Yuqori menyu
    "topmenu_links": [
        {"name": "Bosh sahifa", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"model": "panel.BotUser"},
    ],
    # Chap menyu tartibi va ikonkalari
    "order_with_respect_to": ["panel", "auth"],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "panel.BotUser": "fas fa-user-friends",
        "panel.Reminder": "fas fa-bell",
        "panel.Referral": "fas fa-share-nodes",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "show_ui_builder": False,
}

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "dark_mode_theme": "darkly",
    "navbar": "navbar-dark",
    "navbar_small_text": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_flat_style": True,
    "actions_sticky_top": True,
}
