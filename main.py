import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import router
from logger import configure_logging, get_logger

logger = get_logger(__name__)


async def main():
    configure_logging()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Бот запускается…")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as exc:  # pragma: no cover - safety net for production
        logger.exception("Bot stopped because of an unexpected error: %s", exc)
        raise
    finally:
        await bot.session.close()
        logger.info("Бот остановлен.")

if __name__ == "__main__":
    asyncio.run(main())
