# EslatBot — serverga o'rnatish (Docker)

Butun tizim 3 ta konteynerda ishlaydi:

| Konteyner | Vazifasi |
|---|---|
| `eslatbot_bot` | Telegram bot (aiogram) |
| `eslatbot_adminka` | Django admin panel (gunicorn) |
| `eslatbot_caddy` | Kirish nuqtasi — **HTTPS avtomatik** (Let's Encrypt) |

Baza (SQLite) `bot_data` docker volume'da — konteynerlarni qayta
ko'tarsangiz ham ma'lumotlar yo'qolmaydi.

Domen: **eslat.thesofmebel.uz** → serverning IP'siga A-yozuv qo'yilgan
bo'lishi kerak (DNS'da allaqachon qilingan).

## Serverda birinchi marta ishga tushirish

```bash
# 1. Docker o'rnatish (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh

# 2. Loyihani yuklab olish
git clone https://github.com/krv006/EslatBot.git eslatbot
cd eslatbot

# 3. Sozlamalar faylini yaratish
cp .env.example .env
nano .env
```

`.env` da to'ldirish shart bo'lganlar:

```
BOT_TOKEN=            # BotFather'dan (yangisini oling!)
MOHIR_API_KEY=        # uzbekvoice.ai
GEMINI_API_KEY=       # Google AI Studio
DOMAIN=eslat.thesofmebel.uz
DJANGO_SECRET_KEY=    # python -c "import secrets; print(secrets.token_urlsafe(50))"
DJANGO_ALLOWED_HOSTS=eslat.thesofmebel.uz
DJANGO_CSRF_TRUSTED_ORIGINS=https://eslat.thesofmebel.uz
DJANGO_HTTPS=1
DJANGO_SUPERUSER_USERNAME=   # o'zingiz tanlang
DJANGO_SUPERUSER_PASSWORD=   # KUCHLI parol!
```

```bash
# 4. BITTA BUYRUQ — hammasi ko'tariladi 🚀
docker compose up -d --build
```

Tayyor! 1-2 daqiqada Caddy sertifikat oladi va:
- Bot Telegram'da ishlaydi
- Adminka: **https://eslat.thesofmebel.uz/admin/**

## Kundalik buyruqlar

```bash
docker compose ps                  # holat
docker compose logs -f bot         # bot loglari (jonli)
docker compose logs -f adminka     # adminka loglari
docker compose logs -f caddy       # HTTPS/sertifikat loglari
docker compose restart bot         # faqat botni qayta yuklash
docker compose down                # to'xtatish (baza saqlanadi)
```

## Yangi kod chiqarish

```bash
git pull
docker compose up -d --build
```

## Bazani zaxiralash (backup)

```bash
docker compose cp bot:/app/data/eslatbot.db ./backup_$(date +%F).db
```

## Muammolar

- **Sertifikat olinmayapti** — DNS tarqalishini tekshiring:
  `nslookup eslat.thesofmebel.uz` server IP'sini qaytarishi kerak.
  80 va 443 portlar ochiq bo'lishi shart (firewall/UFW).
- **Adminka CSRF xatosi** — `.env`da `DJANGO_CSRF_TRUSTED_ORIGINS`
  domen bilan `https://` prefiksida yozilganini tekshiring.
