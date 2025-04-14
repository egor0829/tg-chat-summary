import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session

from src.config import API_ID, API_HASH, PHONE, BOT_TOKEN, TIMEZONE
from src.database import (
    get_or_create_user, 
    subscribe_to_chat, 
    unsubscribe_from_chat, 
    update_user_settings, 
    save_summary, 
    update_last_processed_message
)
from src.models import User, ChatSubscription
from src.utils.logger import logger
from src.utils.openrouter import generate_summary


class TelegramSummaryClient:
    def __init__(self, db: Session):
        """
        Инициализирует клиент Telegram
        
        Args:
            db: Сессия базы данных
        """
        self.db = db
        self.client = TelegramClient('anon', API_ID, API_HASH)
        self.bot = None  # Клиент бота будет инициализирован позже
        
    async def start(self):
        """Запускает клиент Telegram и настраивает обработчики событий"""
        try:
            # Запускаем клиент
            await self.client.start(phone=PHONE)
            logger.info("Telethon клиент запущен")
            
            # Запускаем бота, если задан токен
            if BOT_TOKEN:
                self.bot = TelegramClient('bot', API_ID, API_HASH)
                await self.bot.start(bot_token=BOT_TOKEN)
                logger.info("Telegram бот запущен")
                
                # Регистрируем обработчики сообщений бота
                self._register_bot_handlers()
            else:
                logger.warning("BOT_TOKEN не задан, бот не будет запущен")
                
        except Exception as e:
            logger.error(f"Ошибка при запуске Telegram клиента: {str(e)}")
            raise
            
    async def stop(self):
        """Останавливает клиент Telegram"""
        if self.client:
            await self.client.disconnect()
            logger.info("Telethon клиент остановлен")
            
        if self.bot:
            await self.bot.disconnect()
            logger.info("Telegram бот остановлен")
            
    def _register_bot_handlers(self):
        """Регистрирует обработчики сообщений для бота"""
        # Обработчик команды /start
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            """Обрабатывает команду /start"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            await event.respond(
                f"Привет, {sender.first_name}! 👋\n\n"
                "Я - бот для создания саммари по чатам Telegram.\n\n"
                "Вот что я умею:\n"
                "• Создавать ежедневные саммари по выбранным чатам\n"
                "• Настраивать время и частоту получения саммари\n\n"
                "Чтобы добавить чат для саммари, просто перешли мне сообщение из нужного чата.\n"
                "Для настройки времени отправки используй команду /settings.\n\n"
                "Чтобы увидеть все команды, используй /help."
            )
        
        # Обработчик команды /help
        @self.bot.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            """Обрабатывает команду /help"""
            help_text = (
                "📚 **Доступные команды:**\n\n"
                "/start - Начать работу с ботом\n"
                "/help - Показать эту справку\n"
                "/settings - Настроить время и частоту получения саммари\n"
                "/list - Показать список чатов для саммари\n"
                "/unsubscribe - Отписаться от чата (будет запрошен выбор)\n"
                "/summary - Получить саммари прямо сейчас\n\n"
                "Чтобы добавить чат для саммари, перешли мне любое сообщение из нужного чата."
            )
            await event.respond(help_text, parse_mode='md')
        
        # Обработчик команды /settings
        @self.bot.on(events.NewMessage(pattern='/settings'))
        async def settings_handler(event):
            """Обрабатывает команду /settings"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            settings = user.settings
            
            await event.respond(
                "⚙️ **Настройки**\n\n"
                f"Текущее время доставки саммари: {settings.delivery_time}\n"
                f"Частота: {settings.delivery_frequency}\n"
                f"Временная зона: {settings.timezone}\n\n"
                "Чтобы изменить время доставки, отправь сообщение в формате:\n"
                "`/time ЧЧ:ММ`\n\n"
                "Чтобы изменить частоту, отправь:\n"
                "`/frequency daily` или `/frequency weekly`",
                parse_mode='md'
            )
        
        # Обработчик команды /time
        @self.bot.on(events.NewMessage(pattern=r'/time\s+(\d{1,2}):(\d{1,2})'))
        async def time_handler(event):
            """Обрабатывает команду /time для установки времени доставки"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            # Извлекаем время из сообщения
            match = event.pattern_match
            hour, minute = int(match.group(1)), int(match.group(2))
            
            # Проверяем валидность времени
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                time_str = f"{hour:02d}:{minute:02d}"
                update_user_settings(self.db, user.id, delivery_time=time_str)
                await event.respond(f"✅ Время доставки саммари установлено на {time_str}")
            else:
                await event.respond("❌ Некорректное время. Используйте формат ЧЧ:ММ в 24-часовом формате.")
        
        # Обработчик команды /frequency
        @self.bot.on(events.NewMessage(pattern=r'/frequency\s+(daily|weekly)'))
        async def frequency_handler(event):
            """Обрабатывает команду /frequency для установки частоты доставки"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            # Извлекаем частоту из сообщения
            frequency = event.pattern_match.group(1)
            
            # Обновляем настройки пользователя
            update_user_settings(self.db, user.id, delivery_frequency=frequency)
            
            frequency_text = "ежедневно" if frequency == "daily" else "еженедельно"
            await event.respond(f"✅ Частота доставки саммари установлена на {frequency_text}")
        
        # Обработчик команды /list
        @self.bot.on(events.NewMessage(pattern='/list'))
        async def list_handler(event):
            """Обрабатывает команду /list для отображения списка подписок"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            # Получаем активные подписки пользователя
            subscriptions = [s for s in user.chats if s.is_active]
            
            if not subscriptions:
                await event.respond("У вас пока нет подписок на чаты. Чтобы добавить чат, перешлите мне сообщение из него.")
                return
                
            # Формируем список чатов
            chats_list = "\n".join([f"• {sub.chat_title} (ID: {sub.chat_id})" for sub in subscriptions])
            
            await event.respond(
                f"📋 **Ваши подписки на чаты:**\n\n"
                f"{chats_list}\n\n"
                f"Всего: {len(subscriptions)} чат(ов)",
                parse_mode='md'
            )
        
        # Обработчик команды /unsubscribe
        @self.bot.on(events.NewMessage(pattern='/unsubscribe'))
        async def unsubscribe_handler(event):
            """Обрабатывает команду /unsubscribe для отписки от чата"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            # Получаем активные подписки пользователя
            subscriptions = [s for s in user.chats if s.is_active]
            
            if not subscriptions:
                await event.respond("У вас пока нет подписок на чаты.")
                return
                
            # Формируем сообщение с кнопками выбора
            message = "Выберите чат, от которого хотите отписаться, отправив его номер:\n\n"
            
            for i, sub in enumerate(subscriptions, 1):
                message += f"{i}. {sub.chat_title}\n"
                
            message += "\nОтправьте номер чата для отписки."
            
            # Сохраняем список подписок во временном хранилище
            # В реальном приложении лучше использовать Redis или другое хранилище
            self._temp_unsubscribe_data = {
                sender.id: {
                    "subscriptions": subscriptions,
                    "message_id": (await event.respond(message)).id
                }
            }
        
        # Обработчик для завершения отписки
        @self.bot.on(events.NewMessage(pattern=r'^[0-9]+$'))
        async def unsubscribe_confirm_handler(event):
            """Обрабатывает выбор чата для отписки"""
            sender = await event.get_sender()
            
            # Проверяем, есть ли данные для отписки
            if not hasattr(self, '_temp_unsubscribe_data') or sender.id not in self._temp_unsubscribe_data:
                return
                
            try:
                # Получаем номер выбранного чата
                choice = int(event.text.strip())
                data = self._temp_unsubscribe_data[sender.id]
                subscriptions = data["subscriptions"]
                
                # Проверяем, что выбран корректный номер
                if 1 <= choice <= len(subscriptions):
                    sub = subscriptions[choice - 1]
                    
                    # Отписываем пользователя от чата
                    if unsubscribe_from_chat(self.db, sub.user_id, sub.chat_id):
                        await event.respond(f"✅ Вы успешно отписались от чата {sub.chat_title}")
                    else:
                        await event.respond("❌ Не удалось отписаться от чата")
                        
                    # Удаляем временные данные
                    del self._temp_unsubscribe_data[sender.id]
                else:
                    await event.respond("❌ Неверный номер чата. Попробуйте еще раз.")
            except (ValueError, IndexError):
                await event.respond("❌ Неверный формат. Пожалуйста, отправьте только номер чата.")
        
        # Обработчик пересланных сообщений (для добавления чатов)
        @self.bot.on(events.NewMessage(func=lambda e: e.is_private and e.message.forward))
        async def forwarded_handler(event):
            """Обрабатывает пересланные сообщения для добавления чатов"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            # Получаем информацию о чате из пересланного сообщения
            msg = event.message
            
            # Проверяем, есть ли информация о пересылке
            if not msg.forward or not msg.forward.chat:
                await event.respond("❌ Не могу определить чат из этого сообщения. Пожалуйста, перешлите сообщение из нужного чата.")
                return
                
            forward_info = msg.forward
            chat_id = forward_info.chat.id
            chat_title = forward_info.chat.title if hasattr(forward_info.chat, 'title') else str(chat_id)
            
            # Проверяем, есть ли у клиента доступ к чату
            try:
                chat_entity = await self.client.get_entity(chat_id)
                
                # Подписываем пользователя на чат
                subscription = subscribe_to_chat(self.db, user.id, chat_id, chat_title)
                
                await event.respond(
                    f"✅ Вы успешно подписались на саммари чата **{chat_title}**\n\n"
                    f"Вы будете получать саммари согласно вашим настройкам.",
                    parse_mode='md'
                )
                
            except Exception as e:
                logger.error(f"Ошибка при подписке на чат {chat_id}: {str(e)}")
                await event.respond(
                    "❌ Не удалось подписаться на чат. Возможные причины:\n"
                    "• Бот не имеет доступа к этому чату\n"
                    "• Чат больше не существует\n"
                    "• Произошла техническая ошибка\n\n"
                    "Убедитесь, что бот является участником чата."
                )
        
        # Обработчик команды /summary для ручного запроса саммари
        @self.bot.on(events.NewMessage(pattern='/summary'))
        async def summary_handler(event):
            """Обрабатывает команду /summary для ручного запроса саммари"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            # Получаем активные подписки пользователя
            subscriptions = [s for s in user.chats if s.is_active]
            
            if not subscriptions:
                await event.respond("У вас пока нет подписок на чаты. Чтобы добавить чат, перешлите мне сообщение из него.")
                return
                
            await event.respond("🔄 Генерирую саммари для ваших чатов, это может занять некоторое время...")
            
            try:
                # Генерируем саммари для всех чатов пользователя
                await generate_and_send_summaries(self.client, self.db, user, self.bot, event.chat_id)
            except Exception as e:
                logger.error(f"Ошибка при генерации саммари: {str(e)}")
                await event.respond(f"❌ Произошла ошибка при генерации саммари: {str(e)}")
            
            
async def generate_and_send_summaries(client, db: Session, user: User, bot=None, chat_id=None):
    """
    Генерирует и отправляет саммари для всех чатов пользователя
    
    Args:
        client: Telegram клиент
        db: Сессия базы данных
        user: Пользователь
        bot: Telegram бот (опционально)
        chat_id: ID чата для отправки (опционально)
    """
    # Получаем активные подписки пользователя
    subscriptions = [s for s in user.chats if s.is_active]
    
    if not subscriptions:
        logger.info(f"У пользователя {user.telegram_id} нет активных подписок")
        if bot and chat_id:
            await bot.send_message(chat_id, "У вас нет активных подписок на чаты.")
        return
        
    # Генерируем саммари для каждой подписки
    for subscription in subscriptions:
        try:
            # Получаем сообщения из чата с момента последнего обработанного сообщения
            chat_entity = await client.get_entity(subscription.chat_id)
            
            # Определяем начальное сообщение
            last_processed_id = subscription.last_processed_message_id
            
            # Если нет последнего обработанного сообщения, берем сообщения за последние 24 часа
            if not last_processed_id:
                # Получаем сообщения за последние 24 часа
                yesterday = datetime.now(TIMEZONE) - timedelta(days=1)
                messages = await client.get_messages(
                    chat_entity,
                    limit=100,  # Ограничиваем количество сообщений
                    offset_date=yesterday
                )
            else:
                # Получаем сообщения с момента последнего обработанного
                messages = await client.get_messages(
                    chat_entity,
                    limit=100,
                    min_id=last_processed_id
                )
            
            # Проверяем, есть ли новые сообщения
            if not messages:
                logger.info(f"Нет новых сообщений в чате {subscription.chat_title}")
                continue
                
            # Сортируем сообщения по ID
            messages = sorted(messages, key=lambda m: m.id)
            
            # Собираем тексты сообщений
            messages_text = ""
            for msg in messages:
                if msg.message:
                    sender = await client.get_entity(msg.sender_id) if msg.sender_id else None
                    sender_name = f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip() if sender else "Unknown"
                    
                    # Форматируем сообщение
                    timestamp = msg.date.astimezone(TIMEZONE).strftime("%d.%m %H:%M")
                    messages_text += f"[{timestamp}] {sender_name}: {msg.message}\n\n"
            
            # Генерируем саммари
            summary_text = await generate_summary(messages_text)
            
            # Записываем саммари в базу данных
            summary = save_summary(
                db, 
                subscription.id, 
                summary_text,
                messages[0].id if messages else None,
                messages[-1].id if messages else None
            )
            
            # Обновляем последнее обработанное сообщение
            if messages:
                update_last_processed_message(db, subscription.id, messages[-1].id)
            
            # Отправляем саммари пользователю
            if bot and chat_id:
                await bot.send_message(
                    chat_id,
                    f"📝 **Саммари чата {subscription.chat_title}:**\n\n{summary_text}",
                    parse_mode='md'
                )
                
        except Exception as e:
            logger.error(f"Ошибка при генерации саммари для чата {subscription.chat_title}: {str(e)}")
            if bot and chat_id:
                await bot.send_message(
                    chat_id,
                    f"❌ Не удалось сгенерировать саммари для чата {subscription.chat_title}: {str(e)}"
                )
                
    logger.info(f"Саммари сгенерированы для пользователя {user.telegram_id}") 