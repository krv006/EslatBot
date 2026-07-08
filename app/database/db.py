"""SQLite bilan ishlash — barcha so'rovlar shu yerda."""
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
    freq TEXT NOT NULL,          -- daily | every2 | weekly | monthly
    weekday INTEGER,             -- 0=dushanba ... 6=yakshanba (weekly uchun)
    monthday INTEGER,            -- 1-31 (monthly uchun)
    hour INTEGER NOT NULL,
    minute INTEGER NOT NULL,
    start_date TEXT,             -- every2 uchun birinchi yuborish vaqti (ISO)
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
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


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        # WAL — bot va admin panel bazani bir vaqtda ishlatishi uchun
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(CREATE_SQL)
        # eski bazada yetishmayotgan ustunlarni qo'shamiz
        cur = await conn.execute("PRAGMA table_info(users)")
        existing = {row[1] for row in await cur.fetchall()}
        for col, col_type in USER_COLUMNS.items():
            if col not in existing:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        await conn.commit()


async def upsert_user(tg_user) -> int:
    """Telegram'dan kelgan barcha ma'lumotni saqlaydi/yangilaydi.

    tg_user — aiogram'ning message.from_user obyekti.
    """
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT id FROM users WHERE tg_id = ?", (tg_user.id,))
        row = await cur.fetchone()
        if row:
            await conn.execute(
                """UPDATE users SET last_name = ?, username = ?, language_code = ?,
                   is_premium = ?, last_seen = ? WHERE tg_id = ?""",
                (tg_user.last_name, tg_user.username, tg_user.language_code,
                 1 if tg_user.is_premium else 0, now, tg_user.id),
            )
            await conn.commit()
            return row[0]
        cur = await conn.execute(
            """INSERT INTO users
               (tg_id, name, last_name, username, language_code, is_premium,
                created_at, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tg_user.id, tg_user.first_name, tg_user.last_name, tg_user.username,
             tg_user.language_code, 1 if tg_user.is_premium else 0, now, now),
        )
        await conn.commit()
        return cur.lastrowid


async def get_user(tg_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_name(tg_id: int, name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET name = ? WHERE tg_id = ?", (name, tg_id))
        await conn.commit()


async def set_phone(tg_id: int, phone: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (phone, tg_id))
        await conn.commit()


async def set_registered(tg_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET registered = 1 WHERE tg_id = ?", (tg_id,))
        await conn.commit()


# --- Digest (ertalabki kun rejasi) ---

async def get_user_by_id(user_db_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE id = ?", (user_db_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_users_for_digest() -> list[dict]:
    """Digest yoqilgan barcha foydalanuvchilar (bot startida jadvalga yuklash uchun)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE digest_enabled = 1")
        return [dict(r) for r in await cur.fetchall()]


async def get_active_reminders_for_user(user_db_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM reminders WHERE user_id = ? AND is_active = 1",
            (user_db_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def set_digest_enabled(tg_id: int, enabled: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET digest_enabled = ? WHERE tg_id = ?",
            (1 if enabled else 0, tg_id),
        )
        await conn.commit()


async def set_digest_time(tg_id: int, hour: int, minute: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET digest_hour = ?, digest_minute = ? WHERE tg_id = ?",
            (hour, minute, tg_id),
        )
        await conn.commit()


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
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO reminders
               (user_id, text, freq, weekday, monthday, hour, minute, start_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, text, freq, weekday, monthday, hour, minute,
             start_date, datetime.now().isoformat()),
        )
        await conn.commit()
        return cur.lastrowid


async def get_reminder(reminder_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT r.*, u.tg_id FROM reminders r
               JOIN users u ON u.id = r.user_id WHERE r.id = ?""",
            (reminder_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_all_active_reminders() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT r.*, u.tg_id FROM reminders r
               JOIN users u ON u.id = r.user_id WHERE r.is_active = 1"""
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_user_reminders(tg_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT r.*, u.tg_id FROM reminders r
               JOIN users u ON u.id = r.user_id
               WHERE u.tg_id = ? ORDER BY r.id""",
            (tg_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def set_reminder_active(reminder_id: int, active: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE reminders SET is_active = ? WHERE id = ?",
            (1 if active else 0, reminder_id),
        )
        await conn.commit()


async def delete_reminder(reminder_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await conn.commit()
