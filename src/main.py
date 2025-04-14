import asyncio
import sys
import os
import signal
from pathlib import Path

from src.config import BASE_DIR
from src.database import create_tables, get_db
from src.telegram_client import TelegramSummaryClient
from src.utils.logger import logger
from src.utils.scheduler import SchedulerManager


async def main():
    """Основная функция приложения"""
    try:
        # Создаем директорию для данных, если она не существует
        data_dir = BASE_DIR / "data"
        data_dir.mkdir(exist_ok=True)
        
        # Создаем таблицы базы данных
        create_tables()
        
        # Получаем сессию базы данных
        db = get_db()
        
        # Инициализируем и запускаем клиент Telegram
        telegram_client = TelegramSummaryClient(db)
        await telegram_client.start()
        
        # Инициализируем и запускаем планировщик
        scheduler = SchedulerManager(db, telegram_client.client)
        scheduler.start()
        
        # Настраиваем обработчик сигналов для корректного завершения
        def handle_exit(*args):
            asyncio.create_task(shutdown(telegram_client, scheduler))
            
        # Регистрируем обработчики сигналов
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, handle_exit)
        
        # Бесконечный цикл для поддержания работы приложения
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {str(e)}")
        raise
    
    
async def shutdown(telegram_client, scheduler):
    """Корректно завершает работу приложения"""
    logger.info("Завершение работы приложения...")
    
    # Останавливаем планировщик
    if scheduler:
        scheduler.stop()
        
    # Останавливаем клиент Telegram
    if telegram_client:
        await telegram_client.stop()
        
    # Выходим из программы
    sys.exit(0)
    
    
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main()) 