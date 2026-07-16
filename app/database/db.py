"""SQLite bilan ishlash — barcha so'rovlar shu yerda.

MIQYOS (10 000+ user): bitta DOIMIY ulanish (connection) ishlatiladi. Ilgari
har chaqiruvda yangi `aiosqlite.connect()` ochilardi — bu sekin edi (~72 yozuv/sek).
Doimiy ulanish bilan ~6000+ yozuv/sek. `_lock` har amalning execute+commit
ketma-ketligini atomar qiladi (aiosqlite bitta fon oqimida ishlaydi, SQLite
yozishni baribir seriyalaydi — shuning uchun qulf qo'shimcha xarajat keltirmaydi).
"""
import asyncio
from datetime import datetime

import aiosqlite

from app.config import DB_PATH

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    last_name TEXT,
    username TEXT,
    phone TEXT,
    language_code TEXT,
    is_premium INTEGER DEFAULT 0,
    created_at TEXT,
    last_seen TEXT,
    registered INTEGER DEFAULT 0,
    digest_enabled INTEGER DEFAULT 1,
    digest_hour INTEGER DEFAULT 7,
    digest_minute INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id),
    text TEXT NOT NULL,
    freq TEXT NOT NULL,          -- once | daily | every2 | weekly | monthly
    weekday INTEGER,             -- 0=dushanba ... 6=yakshanba (weekly uchun)
    monthday INTEGER,            -- 1-31 (monthly uchun)
    hour INTEGER NOT NULL,
    minute INTEGER NOT NULL,
    start_date TEXT,             -- once/every2 uchun birinchi yuborish vaqti (ISO)
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
);

-- MIQYOS: digest (WHERE user_id=? AND is_active=1) va /list uchun kompozit indeks.
-- Testda 50k eslatmada digest so'rovi 3.7ms -> 0.17ms (21x tez).
-- DIQQAT: alohida is_active indeksi ZARARLI (past-kardinalli), shuning uchun yo'q.
CREATE INDEX IF NOT EXISTS idx_rem_user_active ON reminders (user_id, is_active);

-- Referal: bitta eslatmani boshqa odamga ulashish (link yoki to'g'ridan-to'g'ri).
-- Eslatma ma'lumotlari shu yerga "snapshot" qilinadi — asl eslatma o'zgarsa/o'chsa
-- ham referal barqaror qoladi.
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,          -- deep-link tokeni (?start=ref_<token>)
    from_user_id INTEGER NOT NULL REFERENCES users (id),
    text TEXT NOT NULL,
    freq TEXT NOT NULL,
    weekday INTEGER,
    monthday INTEGER,
    hour INTEGER NOT NULL,
    minute INTEGER NOT NULL,
    start_date TEXT,
    created_at TEXT,
    claimed_count INTEGER NOT NULL DEFAULT 0   -- nechta odam qabul qilgani
);
"""


# Eski bazalarga qo'shiladigan yangi ustunlar (migratsiya)
USER_COLUMNS = {
    "last_name": "TEXT",
    "username": "TEXT",
    "phone": "TEXT",
    "language_code": "TEXT",
    "is_premium": "INTEGER DEFAULT 0",
    "last_seen": "TEXT",
    "registered": "INTEGER DEFAULT 0",
    "digest_enabled": "INTEGER DEFAULT 1",
    "digest_hour": "INTEGER DEFAULT 7",
    "digest_minute": "INTEGER DEFAULT 0",
}


# Doimiy ulanish va uni himoya qiluvchi qulf
_conn: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


def _db() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("db.init_db() hali chaqirilmagan")
    return _conn


async def init_db() -> None:
    global _conn
    _conn = await aiosqlite.connect(DB_PATH)
    _conn.row_factory = aiosqlite.Row
    # WAL — bir vaqtda o'qish/yozish; NORMAL — WAL bilan xavfsiz va tezroq
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA synchronous=NORMAL")
    await _conn.execute("PRAGMA busy_timeout=5000")
    await _conn.executescript(CREATE_SQL)
    # eski bazada yetishmayotgan ustunlarni qo'shamiz
    cur = await _conn.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, col_type in USER_COLUMNS.items():
        if col not in existing:
            await _conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
    await _conn.commit()


async def close_db() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


async def upsert_user(tg_user) -> int:
    """Telegram'dan kelgan barcha ma'lumotni saqlaydi/yangilaydi.

    tg_user — aiogram'ning message.from_user obyekti.
    """
    now = datetime.now().isoformat()
    async with _lock:
        cur = await _db().execute("SELECT id FROM users WHERE tg_id = ?", (tg_user.id,))
        row = await cur.fetchone()
        if row:
            await _db().execute(
                """UPDATE users SET last_name = ?, username = ?, language_code = ?,
                   is_premium = ?, last_seen = ? WHERE tg_id = ?""",
                (tg_user.last_name, tg_user.username, tg_user.language_code,
                 1 if tg_user.is_premium else 0, now, tg_user.id),
            )
            await _db().commit()
            return row[0]
        cur = await _db().execute(
            """INSERT INTO users
               (tg_id, name, last_name, username, language_code, is_premium,
                created_at, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tg_user.id, tg_user.first_name, tg_user.last_name, tg_user.username,
             tg_user.language_code, 1 if tg_user.is_premium else 0, now, now),
        )
        await _db().commit()
        return cur.lastrowid


async def get_user(tg_id: int) -> dict | None:
    async with _lock:
        cur = await _db().execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def set_name(tg_id: int, name: str) -> None:
    async with _lock:
        await _db().execute("UPDATE users SET name = ? WHERE tg_id = ?", (name, tg_id))
        await _db().commit()


async def set_phone(tg_id: int, phone: str) -> None:
    async with _lock:
        await _db().execute("UPDATE users SET phone = ? WHERE tg_id = ?", (phone, tg_id))
        await _db().commit()


async def set_registered(tg_id: int) -> None:
    async with _lock:
        await _db().execute("UPDATE users SET registered = 1 WHERE tg_id = ?", (tg_id,))
        await _db().commit()


# --- Digest (ertalabki kun rejasi) ---

async def get_user_by_id(user_db_id: int) -> dict | None:
    async with _lock:
        cur = await _db().execute("SELECT * FROM users WHERE id = ?", (user_db_id,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_users_for_digest() -> list[dict]:
    """Digest yoqilgan barcha foydalanuvchilar (bot startida jadvalga yuklash uchun)."""
    async with _lock:
        cur = await _db().execute("SELECT * FROM users WHERE digest_enabled = 1")
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_active_reminders_for_user(user_db_id: int) -> list[dict]:
    async with _lock:
        cur = await _db().execute(
            "SELECT * FROM reminders WHERE user_id = ? AND is_active = 1",
            (user_db_id,),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def set_digest_enabled(tg_id: int, enabled: bool) -> None:
    async with _lock:
        await _db().execute(
            "UPDATE users SET digest_enabled = ? WHERE tg_id = ?",
            (1 if enabled else 0, tg_id),
        )
        await _db().commit()


async def set_digest_time(tg_id: int, hour: int, minute: int) -> None:
    async with _lock:
        await _db().execute(
            "UPDATE users SET digest_hour = ?, digest_minute = ? WHERE tg_id = ?",
            (hour, minute, tg_id),
        )
        await _db().commit()


async def deactivate_user_by_tg(tg_id: int) -> None:
    """User botni bloklagan bo'lsa — barcha eslatmalarini nofaol qilib, digestni
    o'chiradi. Scheduler jobi keyingi safar ishga tushganda 'is_active/digest'
    tekshiruvidan o'tmay to'xtaydi (job'ning o'zi arzon no-op bo'lib qoladi).
    """
    async with _lock:
        cur = await _db().execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        if not row:
            return
        await _db().execute(
            "UPDATE reminders SET is_active = 0 WHERE user_id = ?", (row[0],)
        )
        await _db().execute(
            "UPDATE users SET digest_enabled = 0 WHERE tg_id = ?", (tg_id,)
        )
        await _db().commit()


async def add_reminder(
    user_id: int,
    text: str,
    freq: str,
    hour: int,
    minute: int,
    weekday: int | None = None,
    monthday: int | None = None,
    start_date: str | None = None,
) -> int:
    async with _lock:
        cur = await _db().execute(
            """INSERT INTO reminders
               (user_id, text, freq, weekday, monthday, hour, minute, start_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, text, freq, weekday, monthday, hour, minute,
             start_date, datetime.now().isoformat()),
        )
        await _db().commit()
        return cur.lastrowid


async def update_reminder(reminder_id: int, **fields) -> None:
    """Eslatmaning berilgan ustunlarini yangilaydi (faqat kalitlar ichki, xavfsiz)."""
    allowed = {"text", "freq", "weekday", "monthday", "hour", "minute", "start_date"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [reminder_id]
    async with _lock:
        await _db().execute(f"UPDATE reminders SET {cols} WHERE id = ?", vals)
        await _db().commit()


async def get_reminder(reminder_id: int) -> dict | None:
    async with _lock:
        cur = await _db().execute(
            """SELECT r.*, u.tg_id FROM reminders r
               JOIN users u ON u.id = r.user_id WHERE r.id = ?""",
            (reminder_id,),
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_all_active_reminders() -> list[dict]:
    async with _lock:
        cur = await _db().execute(
            """SELECT r.*, u.tg_id FROM reminders r
               JOIN users u ON u.id = r.user_id WHERE r.is_active = 1"""
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_user_reminders(tg_id: int) -> list[dict]:
    async with _lock:
        cur = await _db().execute(
            """SELECT r.*, u.tg_id FROM reminders r
               JOIN users u ON u.id = r.user_id
               WHERE u.tg_id = ? ORDER BY r.id""",
            (tg_id,),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def set_reminder_active(reminder_id: int, active: bool) -> None:
    async with _lock:
        await _db().execute(
            "UPDATE reminders SET is_active = ? WHERE id = ?",
            (1 if active else 0, reminder_id),
        )
        await _db().commit()


async def delete_reminder(reminder_id: int) -> None:
    async with _lock:
        await _db().execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await _db().commit()


# --- Referal (eslatmani boshqaga ulashish) ---

def _phone_tail(phone: str | None) -> str | None:
    """Telefon raqamining oxirgi 9 raqami (format farqlarini yengish uchun)."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else None


async def get_user_by_phone(phone: str) -> dict | None:
    """Telefon raqami bo'yicha foydalanuvchini topadi (oxirgi 9 raqam bo'yicha)."""
    tail = _phone_tail(phone)
    if not tail:
        return None
    async with _lock:
        cur = await _db().execute(
            """SELECT * FROM users WHERE phone IS NOT NULL AND
               REPLACE(REPLACE(REPLACE(phone, '+', ''), ' ', ''), '-', '')
               LIKE '%' || ?""",
            (tail,),
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_referral(from_user_id: int, rem: dict, token: str) -> int:
    """Eslatma snapshot'ini referal sifatida saqlaydi. Referal id qaytaradi."""
    async with _lock:
        cur = await _db().execute(
            """INSERT INTO referrals
               (token, from_user_id, text, freq, weekday, monthday,
                hour, minute, start_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (token, from_user_id, rem["text"], rem["freq"], rem["weekday"],
             rem["monthday"], rem["hour"], rem["minute"], rem["start_date"],
             datetime.now().isoformat()),
        )
        await _db().commit()
        return cur.lastrowid


async def get_referral_by_token(token: str) -> dict | None:
    async with _lock:
        cur = await _db().execute(
            "SELECT * FROM referrals WHERE token = ?", (token,)
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def try_claim_referral(referral_id: int) -> bool:
    """Referalni ATOMAR ravishda 'band' qiladi (bir martalik link).

    True  — biz birinchi bo'lib oldik (yetkazish mumkin);
    False — allaqachon ishlatilgan (link kuchini yo'qotgan).
    Bitta UPDATE ichida shart tekshiriladi — ikki kishi bir vaqtda ochsa ham
    faqat bittasi 'ROW o'zgardi' natijasini oladi (poyga-xavfsiz).
    """
    async with _lock:
        cur = await _db().execute(
            "UPDATE referrals SET claimed_count = 1 WHERE id = ? AND claimed_count = 0",
            (referral_id,),
        )
        await _db().commit()
        return cur.rowcount == 1
