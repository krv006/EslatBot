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

-- Broadcast: adminkadan yuboriladigan ommaviy/yakka xabar.
-- Django faqat 'pending' yozadi; bot o'qib flood-himoyali sender bilan yuboradi.
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,                       -- CKEditor HTML
    target TEXT NOT NULL DEFAULT 'all',       -- all | username | phone
    target_value TEXT,                        -- username yoki telefon (yakka uchun)
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | sending | done | error
    total INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT,
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_broadcast_status ON broadcasts (status);

-- Odat kuzatuvi: takror eslatma (odat) har kungi natijasi.
-- status: 'done' (bajarildi) | 'skipped' (o'tkazib yuborildi).
-- Bir eslatma-bir kun = bitta yozuv (UNIQUE), qayta bosilsa yangilanadi.
CREATE TABLE IF NOT EXISTS habit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id INTEGER NOT NULL REFERENCES reminders (id),
    log_date TEXT NOT NULL,              -- 'YYYY-MM-DD'
    status TEXT NOT NULL,                -- done | skipped
    created_at TEXT,
    UNIQUE (reminder_id, log_date)
);

CREATE INDEX IF NOT EXISTS idx_habit_rem ON habit_logs (reminder_id);

-- Vazifalar: bir martalik ish (eslatmadan farqli). Muddat (deadline), ustuvorlik,
-- bajarilganlik holati bor. Eslatmadek belgilangan vaqtda otilmaydi.
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id),
    title TEXT NOT NULL,
    due_date TEXT,                       -- 'YYYY-MM-DD' | NULL
    priority TEXT NOT NULL DEFAULT 'normal',  -- low | normal | high
    is_done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks (user_id, is_done);

-- Qaydlar: oddiy matnli eslatib qo'yish (loyiha/vazifaga bog'lanmagan).
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id),
    text TEXT NOT NULL,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_notes_user ON notes (user_id);
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


async def touch_last_seen(tg_id: int) -> None:
    """Faollik belgisi — HAR QANDAY interaksiyada (xabar VA tugma bosish) chaqiriladi.
    Yengil UPDATE: user hali yo'q bo'lsa (birinchi /start) 0 qatorga ta'sir qiladi,
    keyin start handleri upsert qiladi. Tugma bosgan userlar ham 'faol' sanaladi."""
    async with _lock:
        await _db().execute(
            "UPDATE users SET last_seen = ? WHERE tg_id = ?",
            (datetime.now().isoformat(), tg_id),
        )
        await _db().commit()


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


# --- Broadcast (adminkadan ommaviy/yakka xabar) ---

async def get_next_pending_broadcast() -> dict | None:
    """Eng eski 'pending' broadcast'ni oladi (bir vaqtda bittasi qayta ishlanadi).
    Jadval hali yaratilmagan bo'lsa (eski baza) — jimgina None."""
    try:
        async with _lock:
            cur = await _db().execute(
                "SELECT * FROM broadcasts WHERE status = 'pending' "
                "ORDER BY id LIMIT 1"
            )
            row = await cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None


async def mark_broadcast_sending(broadcast_id: int, total: int) -> None:
    async with _lock:
        await _db().execute(
            "UPDATE broadcasts SET status = 'sending', total = ?, sent = 0, "
            "failed = 0 WHERE id = ?",
            (total, broadcast_id),
        )
        await _db().commit()


async def update_broadcast_progress(broadcast_id: int, sent: int, failed: int) -> None:
    async with _lock:
        await _db().execute(
            "UPDATE broadcasts SET sent = ?, failed = ? WHERE id = ?",
            (sent, failed, broadcast_id),
        )
        await _db().commit()


async def finish_broadcast(
    broadcast_id: int, sent: int, failed: int,
    status: str = "done", error: str | None = None,
) -> None:
    async with _lock:
        await _db().execute(
            "UPDATE broadcasts SET status = ?, sent = ?, failed = ?, error = ?, "
            "sent_at = ? WHERE id = ?",
            (status, sent, failed, error, datetime.now().isoformat(), broadcast_id),
        )
        await _db().commit()


async def get_all_user_ids() -> list[int]:
    """Barcha foydalanuvchilarning tg_id'lari (broadcast=all uchun)."""
    async with _lock:
        cur = await _db().execute("SELECT tg_id FROM users")
        rows = await cur.fetchall()
    return [r[0] for r in rows]


async def get_user_by_username(username: str) -> dict | None:
    """Username bo'yicha user (bosh '@' va katta-kichik harf farqi hisobga olinadi)."""
    uname = username.strip().lstrip("@").lower()
    if not uname:
        return None
    async with _lock:
        cur = await _db().execute(
            "SELECT * FROM users WHERE LOWER(username) = ?", (uname,)
        )
        row = await cur.fetchone()
    return dict(row) if row else None


# --- Odat kuzatuvi (habit tracking) ---

async def log_habit(reminder_id: int, status: str, log_date: str | None = None) -> None:
    """Odatning bugungi (yoki berilgan) natijasini yozadi/yangilaydi.
    status: 'done' yoki 'skipped'."""
    from datetime import date
    ld = log_date or date.today().isoformat()
    async with _lock:
        await _db().execute(
            """INSERT INTO habit_logs (reminder_id, log_date, status, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(reminder_id, log_date)
               DO UPDATE SET status=excluded.status, created_at=excluded.created_at""",
            (reminder_id, ld, status, datetime.now().isoformat()),
        )
        await _db().commit()


async def get_habit_status_today(reminder_id: int, log_date: str | None = None) -> str | None:
    """Bugungi (yoki berilgan sana) natijasi: 'done' | 'skipped' | None."""
    from datetime import date
    ld = log_date or date.today().isoformat()
    async with _lock:
        cur = await _db().execute(
            "SELECT status FROM habit_logs WHERE reminder_id = ? AND log_date = ?",
            (reminder_id, ld),
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def get_habit_logs(reminder_id: int, limit: int = 400) -> list[dict]:
    """Odatning so'nggi natijalari (yangi -> eski)."""
    async with _lock:
        cur = await _db().execute(
            "SELECT log_date, status FROM habit_logs WHERE reminder_id = ? "
            "ORDER BY log_date DESC LIMIT ?",
            (reminder_id, limit),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- Vazifalar (tasks) ---

async def add_task(user_id: int, title: str, due_date: str | None = None,
                   priority: str = "normal") -> int:
    async with _lock:
        cur = await _db().execute(
            """INSERT INTO tasks (user_id, title, due_date, priority, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, title, due_date, priority, datetime.now().isoformat()),
        )
        await _db().commit()
        return cur.lastrowid


async def get_user_tasks(tg_id: int, include_done: bool = False) -> list[dict]:
    """Foydalanuvchi vazifalari. include_done=False — faqat bajarilmaganlar."""
    q = ("SELECT t.* FROM tasks t JOIN users u ON u.id = t.user_id "
         "WHERE u.tg_id = ?")
    if not include_done:
        q += " AND t.is_done = 0"
    q += " ORDER BY t.is_done, (t.due_date IS NULL), t.due_date, t.id DESC"
    async with _lock:
        cur = await _db().execute(q, (tg_id,))
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_task(task_id: int) -> dict | None:
    async with _lock:
        cur = await _db().execute(
            "SELECT t.*, u.tg_id FROM tasks t JOIN users u ON u.id = t.user_id "
            "WHERE t.id = ?", (task_id,),
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def set_task_done(task_id: int, done: bool) -> None:
    async with _lock:
        await _db().execute(
            "UPDATE tasks SET is_done = ?, done_at = ? WHERE id = ?",
            (1 if done else 0, datetime.now().isoformat() if done else None, task_id),
        )
        await _db().commit()


async def update_task(task_id: int, **fields) -> None:
    allowed = {"title", "due_date", "priority"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    async with _lock:
        await _db().execute(f"UPDATE tasks SET {cols} WHERE id = ?",
                            list(fields.values()) + [task_id])
        await _db().commit()


async def delete_task(task_id: int) -> None:
    async with _lock:
        await _db().execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await _db().commit()


# --- Qaydlar (notes) ---

async def add_note(user_id: int, text: str) -> int:
    async with _lock:
        cur = await _db().execute(
            "INSERT INTO notes (user_id, text, created_at) VALUES (?, ?, ?)",
            (user_id, text, datetime.now().isoformat()),
        )
        await _db().commit()
        return cur.lastrowid


async def get_user_notes(tg_id: int, query: str | None = None) -> list[dict]:
    """Foydalanuvchi qaydlari (yangi -> eski). query berilsa — matn bo'yicha qidiradi."""
    q = ("SELECT n.* FROM notes n JOIN users u ON u.id = n.user_id "
         "WHERE u.tg_id = ?")
    params: list = [tg_id]
    if query:
        q += " AND n.text LIKE ?"
        params.append(f"%{query}%")
    q += " ORDER BY n.id DESC"
    async with _lock:
        cur = await _db().execute(q, params)
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_note(note_id: int) -> dict | None:
    async with _lock:
        cur = await _db().execute(
            "SELECT n.*, u.tg_id FROM notes n JOIN users u ON u.id = n.user_id "
            "WHERE n.id = ?", (note_id,),
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def delete_note(note_id: int) -> None:
    async with _lock:
        await _db().execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await _db().commit()
