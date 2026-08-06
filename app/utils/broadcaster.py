"""Adminkadan yozilgan broadcast'larni yuboruvchi fon-jarayoni.

Django adminka bazaga 'pending' broadcast yozadi; shu poller uni o'qib
qabul qiluvchilarni aniqlaydi va flood-himoyali `sender` navbatiga qo'yadi.
Shunday qilib ommaviy xabar ham bot eslatmalari kabi bir maromda, Telegram
limitiga urilmasdan yuboriladi.
"""
import asyncio
import logging

from app.database import db
from app.utils.sender import sender
from app.utils.tg_html import html_to_telegram

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # sekundda bir marta 'pending' broadcast tekshiriladi
PROGRESS_STEP = 25  # har shuncha xabardan keyin progress bazaga yoziladi


async def _resolve_recipients(bc: dict) -> tuple[list[int], str | None]:
    """(tg_id ro'yxati, xato_izohi). Xato bo'lsa ro'yxat bo'sh, izoh to'ladi."""
    target = bc.get("target") or "all"
    val = (bc.get("target_value") or "").strip()
    if target == "all":
        return await db.get_all_user_ids(), None
    if target == "username":
        user = await db.get_user_by_username(val)
        if not user:
            return [], f"@{val.lstrip('@')} — bunday user topilmadi."
        return [user["tg_id"]], None
    if target == "phone":
        user = await db.get_user_by_phone(val)
        if not user:
            return [], f"{val} — bu telefon bo'yicha user topilmadi."
        return [user["tg_id"]], None
    return [], f"Noma'lum yo'nalish: {target}"


async def _process_one(bc: dict) -> None:
    bid = bc["id"]
    text = html_to_telegram(bc.get("text") or "")
    if not text:
        await db.finish_broadcast(bid, 0, 0, status="error", error="Xabar matni bo'sh.")
        return

    recipients, err = await _resolve_recipients(bc)
    if err:
        await db.finish_broadcast(bid, 0, 0, status="error", error=err)
        logger.warning("Broadcast #%s: %s", bid, err)
        return

    total = len(recipients)
    await db.mark_broadcast_sending(bid, total)
    if total == 0:
        await db.finish_broadcast(bid, 0, 0, status="done",
                                  error="Qabul qiluvchi topilmadi (0 ta).")
        return

    counter = {"sent": 0, "failed": 0}
    finished = asyncio.Event()

    def on_result(ok: bool):
        counter["sent" if ok else "failed"] += 1
        done = counter["sent"] + counter["failed"]
        if done % PROGRESS_STEP == 0:  # adminda jonli ko'rinsin
            asyncio.create_task(
                db.update_broadcast_progress(bid, counter["sent"], counter["failed"]))
        if done >= total:
            finished.set()

    for chat_id in recipients:
        await sender.enqueue(chat_id, text, on_result=on_result)

    await finished.wait()
    await db.finish_broadcast(bid, counter["sent"], counter["failed"], status="done")
    logger.info("Broadcast #%s tugadi: %s yuborildi, %s yetmadi",
                bid, counter["sent"], counter["failed"])


async def broadcast_worker() -> None:
    """Doimiy tsikl: 'pending' broadcast bo'lsa navbatma-navbat qayta ishlaydi."""
    logger.info("Broadcast worker ishga tushdi (interval=%ss)", POLL_INTERVAL)
    while True:
        try:
            bc = await db.get_next_pending_broadcast()
            if bc:
                logger.info("Broadcast #%s topildi (yo'nalish=%s)",
                            bc["id"], bc["target"])
                await _process_one(bc)
                continue  # keyingisini darhol tekshiramiz
        except Exception:
            logger.exception("Broadcast worker: kutilmagan xato")
        await asyncio.sleep(POLL_INTERVAL)
