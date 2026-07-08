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

## Kirish rejimini tanlash

**A) Server bo'sh (80/443 hech kim ishlatmaydi)** — `.env` da:
```
COMPOSE_PROFILES=caddy
DOMAIN=eslat.thesofmebel.uz
```
Caddy o'zi HTTPS sertifikat oladi. Tayyor: https://eslat.thesofmebel.uz/admin/

**B) Serverda boshqa sayt(lar) bor (80-port band, nginx ishlayapti)** —
`.env` da `COMPOSE_PROFILES` va `DOMAIN` ni bo'sh qoldiring.
Adminka 127.0.0.1:8001 da turadi, tashqi nginx unga proxy qiladi:

```bash
# nginx sayt konfigi
cat > /etc/nginx/sites-available/eslat <<'EOF'
server {
    listen 80;
    server_name eslat.thesofmebel.uz;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
ln -s /etc/nginx/sites-available/eslat /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# HTTPS sertifikat (bepul, avto-yangilanadi)
apt install -y certbot python3-certbot-nginx
certbot --nginx -d eslat.thesofmebel.uz
```

Tayyor: **https://eslat.thesofmebel.uz/admin/**
(static fayllarni Django o'zi beradi — whitenoise, alohida sozlash kerak emas)

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
