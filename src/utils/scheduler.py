import schedule
import time
import threading
import datetime
from src.utils.logger import logger
from sqlalchemy.orm import Session
from src.models import UserSettings, User, ChatSubscription
import asyncio
from typing import Callable, Any, Dict


class SchedulerManager:
    def __init__(self, db: Session, telegram_client):
        """
        Инициализирует менеджер планировщика
        
        Args:
            db: Сессия базы данных
            telegram_client: Клиент Telegram
        """
        self.db = db
        self.telegram_client = telegram_client
        self.stop_event = threading.Event()
        self.scheduler_thread = None
        
    def start(self):
        """Запускает планировщик в отдельном потоке"""
        if self.scheduler_thread is not None:
            logger.warning("Планировщик уже запущен")
            return
            
        self.stop_event.clear()
        self.scheduler_thread = threading.Thread(target=self._run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        logger.info("Планировщик запущен")
        
    def stop(self):
        """Останавливает планировщик"""
        if self.scheduler_thread is None:
            logger.warning("Планировщик не запущен")
            return
            
        self.stop_event.set()
        self.scheduler_thread.join()
        self.scheduler_thread = None
        logger.info("Планировщик остановлен")
        
    def _run_scheduler(self):
        """Основной цикл планировщика"""
        self._schedule_all_users()
        
        while not self.stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)
            
    def _schedule_all_users(self):
        """Планирует задачи для всех активных пользователей"""
        schedule.clear()
        users = self.db.query(User).join(UserSettings).filter(
            User.is_active == True,
            UserSettings.is_active == True
        ).all()
        
        for user in users:
            self._schedule_user(user)
            
        logger.info(f"Запланированы задачи для {len(users)} пользователей")
        
    def _schedule_user(self, user: User):
        """
        Планирует задачи для конкретного пользователя
        
        Args:
            user: Пользователь для которого нужно запланировать задачи
        """
        if not user.settings:
            logger.warning(f"У пользователя {user.telegram_id} нет настроек")
            return
            
        delivery_time = user.settings.delivery_time
        frequency = user.settings.delivery_frequency
        
        # Функция для выполнения
        def job():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._process_user_summaries(user.id))
            loop.close()
        
        # Планирование в зависимости от частоты
        if frequency == "daily":
            schedule.every().day.at(delivery_time).do(job)
        elif frequency == "weekly":
            schedule.every().monday.at(delivery_time).do(job)
        else:
            logger.error(f"Неизвестная частота {frequency} для пользователя {user.telegram_id}")
            
    async def _process_user_summaries(self, user_id: int):
        """
        Обрабатывает и отправляет саммари для пользователя
        
        Args:
            user_id: ID пользователя
        """
        from src.telegram_client import generate_and_send_summaries
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"Пользователь с ID {user_id} не найден")
            return
            
        await generate_and_send_summaries(self.telegram_client, self.db, user) 