# EslatBot — serverga o'rnatish (Docker)

Butun tizim 3 ta konteynerda ishlaydi:

| Konteyner | Vazifasi |
|---|---|
| `eslatbot_bot` | Telegram bot (aiogram) |
| `eslatbot_adminka` | Django admin panel (gunicorn) |
| `eslatbot_nginx` | Tashqi kirish nuqtasi — 80-port |

Baza (SQLite) `bot_data` nomli docker volume'da saqlanadi — konteynerlarni
o'chirib qayta ko'tarsangiz ham ma'lumotlar yo'qolmaydi.

## Serverda birinchi marta ishga tushirish

```bash
# 1. Docker o'rnatish (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh

# 2. Loyihani yuklab olish
git clone <REPO_MANZILI> eslatbot
cd eslatbot

# 3. Sozlamalar faylini yaratish
cp .env.example .env
nano .env        # BOT_TOKEN, DJANGO_SECRET_KEY, DJANGO_SUPERUSER_PASSWORD ni yozing!

# 4. BITTA BUYRUQ — hammasi ko'tariladi 🚀
docker compose up -d --build
```

Tayyor! Endi:
- Bot Telegram'da ishlayapti
- Adminka: `http://SERVER_IP/admin/` (login/parol — .env dagi DJANGO_SUPERUSER_*)

## Kundalik buyruqlar

```bash
docker compose ps                  # holatni ko'rish
docker compose logs -f bot         # bot loglari (jonli)
docker compose logs -f adminka     # adminka loglari
docker compose restart bot         # faqat botni qayta yuklash
docker compose down                # hammasini to'xtatish (baza saqlanadi)
```

## Yangi kod chiqarish (yangilash)

```bash
git pull
docker compose up -d --build       # o'zgargan qismini o'zi qayta quradi
```

## Bazani zaxiralash (backup)

```bash
docker compose cp bot:/app/data/eslatbot.db ./backup_$(date +%F).db
```

## Domen va HTTPS (ixtiyoriy, keyinroq)

Domen ulasangiz `.env` da:
```
DJANGO_ALLOWED_HOSTS=bot.example.uz
DJANGO_CSRF_TRUSTED_ORIGINS=https://bot.example.uz
```
HTTPS uchun eng oson yo'l — nginx o'rniga [Caddy](https://caddyserver.com)
ishlatish yoki serverda `certbot` bilan sertifikat olish.
