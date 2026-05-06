"""
Главный файл Telegram-бота для поиска юзернеймов
Автор: codedev
Версия: 1.0
"""

import asyncio
import logging
import sys
from os import getenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from dotenv import load_dotenv

# Импорт обработчиков
from handlers import start, search, filter, profile, support
from database.db import db

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """
    Главная функция запуска бота
    """
    # Получаем токен из переменных окружения
    bot_token = getenv("BOT_TOKEN")
    
    if not bot_token:
        logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
        logger.error("Создайте файл .env и добавьте: BOT_TOKEN=ваш_токен")
        sys.exit(1)
    
    # Инициализация бота
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Инициализация диспетчера с хранилищем состояний
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(search.router)
    dp.include_router(filter.router)
    dp.include_router(profile.router)
    dp.include_router(support.router)
    
    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    await db.init_db()
    logger.info("✅ База данных инициализирована")
    
    # Запуск бота
    logger.info("🚀 Бот запущен и готов к работе!")
    logger.info("Нажмите Ctrl+C для остановки")
    
    try:
        # Удаляем вебхуки (если были)
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Запускаем polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    
    finally:
        logger.info("Остановка бота...")
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
