"""EslatBot — kirish nuqtasi. Ishga tushirish: python main.py"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import BOT_TOKEN
from app.database import db
from app.handlers import manage, reminders, start
from app.scheduler.scheduler import load_all_reminders, scheduler

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

    # DIQQAT: reminders.router oxirida — unda erkin matnni ushlaydigan handler bor
    dp.include_routers(start.router, manage.router, reminders.router)

    scheduler.start()
    await load_all_reminders(bot)

    logger.info("EslatBot ishga tushdi! 🚀")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code:
            print(e.code)
        else:
            print("Bot to'xtatildi.")
