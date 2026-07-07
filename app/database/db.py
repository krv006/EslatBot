"""SQLite bilan ishlash — barcha so'rovlar shu yerda."""
from datetime import datetime

import aiosqlite

from app.config import DB_PATH

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    created_at TEXT
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


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        # WAL — bot va admin panel bazani bir vaqtda ishlatishi uchun
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(CREATE_SQL)
        await conn.commit()


async def get_or_create_user(tg_id: int, name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        if row:
            return row[0]
        cur = await conn.execute(
            "INSERT INTO users (tg_id, name, created_at) VALUES (?, ?, ?)",
            (tg_id, name, datetime.now().isoformat()),
        )
        await conn.commit()
        return cur.lastrowid


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
