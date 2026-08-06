"""EslatBot — kirish nuqtasi. Ishga tushirish: python main.py"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import BOT_TOKEN
from app.database import db
from app.handlers import dayplan, edit, manage, referral, reminders, settings, start
from app.scheduler.scheduler import (
    load_all_digests,
    load_all_reminders,
    scheduler,
)
from app.utils.activity import ActivityMiddleware
from app.utils.broadcaster import broadcast_worker
from app.utils.sender import sender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN or "TOKENINGIZNI" in BOT_TOKEN:
        raise SystemExit(
            "❌ BOT_TOKEN topilmadi!\n"
            ".env faylini oching va @BotFather dan olgan tokeningizni qo'ying:\n"
            "BOT_TOKEN=1234567890:AAE..."
        )

    await db.init_db()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Har interaksiyada (xabar VA tugma bosish) last_seen yangilanadi — faollikni
    # to'g'ri o'lchash uchun (faqat tugma bosadigan userlar ham "faol" sanaladi)
    dp.update.outer_middleware(ActivityMiddleware())

    # DIQQAT: referral.router boshida — Referral holatlarida yozilgan matnni
    # boshqa routerlar (ayniqsa reminders'dagi erkin matn handleri) ushlab
    # qolmasligi uchun.
    # reminders.router oxirida — unda erkin matnni ushlaydigan handler bor.
    dp.include_routers(
        referral.router, start.router, manage.router, settings.router,
        dayplan.router, edit.router, reminders.router,
    )

    # Chiquvchi xabar navbatini ishga tushiramiz (flood himoyasi) — jadval
    # ishga tushishidan oldin worker tayyor bo'lsin
    await sender.start(bot)

    # Adminkadan yozilgan broadcast'larni yuboruvchi fon-jarayoni
    asyncio.create_task(broadcast_worker(), name="broadcast-worker")

    scheduler.start()
    await load_all_reminders(bot)
    await load_all_digests(bot)

    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash / bosh menyu"),
        BotCommand(command="new", description="➕ Yangi eslatma"),
        BotCommand(command="list", description="📋 Eslatmalarim"),
        BotCommand(command="help", description="❓ Yordam"),
        BotCommand(command="cancel", description="❌ Amalni bekor qilish"),
    ])

    logger.info("EslatBot ishga tushdi! 🚀")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code:
            print(e.code)
        else:
            print("Bot to'xtatildi.")
