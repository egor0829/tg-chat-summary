import os
import asyncio
import time
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session

from src.config import API_ID, API_HASH, PHONE, BOT_TOKEN, TIMEZONE, DATA_DIR, AVAILABLE_MODELS
from src.database import (
    get_or_create_user, 
    subscribe_to_chat, 
    unsubscribe_from_chat, 
    update_user_settings, 
    save_summary, 
    update_last_processed_message,
    get_user_model
)
from src.models import User, ChatSubscription
from src.utils.logger import logger
from src.utils.openrouter import generate_summary, list_available_models


class TelegramSummaryClient:
    def __init__(self, db: Session):
        """
        Инициализирует клиент Telegram
        
        Args:
            db: Сессия базы данных
        """
        self.db = db
        
        # Используем директорию data для хранения файлов сессии
        session_file = os.path.join(DATA_DIR, 'anon')
        self.client = TelegramClient(session_file, API_ID, API_HASH)
        self.bot = None  # Клиент бота будет инициализирован позже
        
    async def start(self):
        """Запускает клиент Telegram и настраивает обработчики событий"""
        try:
            # Проверяем существование файлов сессии перед запуском
            session_path = os.path.join(DATA_DIR, 'anon.session')
            bot_session_path = os.path.join(DATA_DIR, 'bot.session')
            
            if not os.path.exists(session_path):
                logger.error(f"Файл сессии не найден: {session_path}")
                logger.error("Пожалуйста, запустите скрипт auth_telethon.py на хост-машине перед запуском в Docker")
                raise FileNotFoundError(f"Файл сессии не найден: {session_path}")
            
            # Сначала просто подключаемся, не запрашивая код
            await self.client.connect()
            
            # Проверяем авторизацию
            if not await self.client.is_user_authorized():
                logger.error("Сессия существует, но пользователь не авторизован")
                logger.error("Пожалуйста, выполните повторную аутентификацию, запустив скрипт auth_telethon.py")
                await self.client.disconnect()
                raise RuntimeError("Пользователь не авторизован")
                
            logger.info("Telethon клиент успешно подключен с существующей сессией")
            
            # Запускаем бота, если задан токен
            if BOT_TOKEN:
                if not os.path.exists(bot_session_path):
                    logger.error(f"Файл сессии бота не найден: {bot_session_path}")
                    logger.error("Пожалуйста, запустите скрипт auth_bot.py на хост-машине перед запуском в Docker")
                    raise FileNotFoundError(f"Файл сессии бота не найден: {bot_session_path}")
                
                # Инициализируем бота с использованием существующей сессии
                bot_session_file = os.path.join(DATA_DIR, 'bot')
                self.bot = TelegramClient(bot_session_file, API_ID, API_HASH)
                
                # Просто подключаемся
                await self.bot.connect()
                
                # Проверяем авторизацию бота
                if not await self.bot.is_user_authorized():
                    logger.error("Сессия бота существует, но бот не авторизован")
                    logger.error("Пожалуйста, выполните повторную аутентификацию, запустив скрипт auth_bot.py")
                    await self.bot.disconnect()
                    raise RuntimeError("Бот не авторизован")
                
                logger.info("Telegram бот успешно подключен с существующей сессией")
                
                # Регистрируем обработчики сообщений бота
                self._register_bot_handlers()
            else:
                logger.warning("BOT_TOKEN не задан, бот не будет запущен")
                
        except FloodWaitError as e:
            # Обработка ошибки FloodWait
            wait_time = e.seconds
            logger.warning(f"Telegram требует подождать {wait_time} секунд. Ожидаем...")
            
            # Закрываем соединение перед ожиданием
            if hasattr(self, 'client') and self.client.is_connected():
                await self.client.disconnect()
            if hasattr(self, 'bot') and self.bot and self.bot.is_connected():
                await self.bot.disconnect()
                
            # Ждем указанное время + 5 секунд для надежности
            await asyncio.sleep(wait_time + 5)
            
            # Повторно пытаемся запустить после ожидания
            logger.info(f"Ожидание {wait_time} секунд завершено, повторное подключение...")
            await self.start()
                
        except Exception as e:
            logger.error(f"Ошибка при запуске Telegram клиента: {str(e)}")
            # Закрываем соединения при ошибке
            if hasattr(self, 'client') and self.client.is_connected():
                await self.client.disconnect()
            if hasattr(self, 'bot') and self.bot and self.bot.is_connected():
                await self.bot.disconnect()
            raise
            
    async def stop(self):
        """Останавливает клиент Telegram"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Telethon клиент остановлен")
            
        if self.bot and self.bot.is_connected():
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
            
            # Получаем название модели из списка доступных
            model_name = settings.openrouter_model
            model_display_name = AVAILABLE_MODELS.get(model_name, model_name)
            
            await event.respond(
                "⚙️ **Настройки**\n\n"
                f"Текущее время доставки саммари: {settings.delivery_time}\n"
                f"Частота: {settings.delivery_frequency}\n"
                f"Временная зона: {settings.timezone}\n\n"
                f"Модель для саммаризации: {model_display_name}\n\n"
                "Чтобы изменить время доставки, отправь сообщение в формате:\n"
                "`/time ЧЧ:ММ`\n\n"
                "Чтобы изменить частоту, отправь:\n"
                "`/frequency daily` или `/frequency weekly`\n\n"
                "Для выбора модели саммаризации используй:\n"
                "`/models` - список доступных моделей\n"
                "`/model ID_модели` - выбор конкретной модели",
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
            
            # Логируем структуру объекта для диагностики
            logger.info(f"Получено пересланное сообщение: {msg}")
            logger.info(f"Атрибуты объекта forward: {dir(msg.forward)}")
            
            try:
                forward_info = msg.forward
                
                # Проверяем доступные атрибуты для извлечения информации о чате
                from_id = None
                chat_id = None
                chat_title = None
                is_private_chat = False
                user_id = None
                
                # Проверяем, есть ли информация об отправителе (для приватных чатов)
                if hasattr(forward_info, 'from_id'):
                    logger.info(f"Найден атрибут from_id: {forward_info.from_id}")
                    from_id = forward_info.from_id
                    
                    # Проверяем, является ли from_id PeerUser (приватный чат)
                    if hasattr(from_id, 'user_id'):
                        user_id = from_id.user_id
                        logger.info(f"Обнаружен приватный чат с пользователем ID: {user_id}")
                        is_private_chat = True
                        # Для приватных чатов используем user_id в качестве chat_id с префиксом "user_"
                        chat_id = f"user_{user_id}"
                    # Если есть from_id, но нет chat_id, это может быть пересылка из приватного чата
                    elif not chat_id and hasattr(from_id, 'channel_id'):
                        chat_id = from_id.channel_id
                
                # Проверяем наличие имени отправителя (для приватных чатов без явного ID)
                if hasattr(forward_info, 'from_name') and forward_info.from_name and not user_id:
                    logger.info(f"Найден атрибут from_name: {forward_info.from_name}")
                    chat_title = forward_info.from_name
                    is_private_chat = True
                    # Создаем псевдо-ID на основе имени (не идеально, но работает для демонстрации)
                    # В реальном сценарии лучше попытаться найти пользователя по имени через API
                    chat_id = f"name_{hash(forward_info.from_name) % 10000000}"
                
                # Пробуем извлечь ID чата из разных возможных атрибутов (для групп и каналов)
                if not is_private_chat:
                    if hasattr(forward_info, 'chat') and forward_info.chat:
                        logger.info(f"Найден атрибут chat: {forward_info.chat}")
                        if hasattr(forward_info.chat, 'id'):
                            chat_id = forward_info.chat.id
                        if hasattr(forward_info.chat, 'title'):
                            chat_title = forward_info.chat.title
                    
                    # Проверяем атрибуты для случая пересылки из канала или группы
                    if hasattr(forward_info, 'channel_id'):
                        logger.info(f"Найден атрибут channel_id: {forward_info.channel_id}")
                        chat_id = forward_info.channel_id
                    
                    # Проверяем, есть ли у сообщения другие атрибуты, которые могут содержать ID чата
                    if not chat_id and hasattr(msg, 'peer_id'):
                        logger.info(f"Найден атрибут peer_id: {msg.peer_id}")
                        if hasattr(msg.peer_id, 'channel_id'):
                            chat_id = msg.peer_id.channel_id
                            
                    # Получаем имя чата, если оно не было найдено
                    if not chat_title and hasattr(forward_info, 'chat_name'):
                        chat_title = forward_info.chat_name
                    elif not chat_title and hasattr(forward_info, 'channel_post') and forward_info.channel_post:
                        # Для постов из каналов
                        chat_title = f"Канал (ID: {chat_id})"
                
                # Если не удалось извлечь ID чата ни из одного атрибута
                if not chat_id:
                    logger.error(f"Не удалось определить ID чата из пересланного сообщения: {msg}")
                    await event.respond(
                        "❌ Не могу определить чат из этого сообщения.\n\n"
                        "Это может происходить из-за ограничений приватности канала или чата.\n\n"
                        "Попробуйте:\n"
                        "1. Переслать сообщение из публичного канала или группы\n"
                        "2. Убедиться, что основной аккаунт является участником чата\n"
                        "3. Переслать сообщение от имени администратора канала или группы"
                    )
                    return
                
                # Если не удалось извлечь название чата, используем ID
                if not chat_title:
                    if is_private_chat and user_id:
                        chat_title = f"Личный чат с пользователем {user_id}"
                    else:
                        chat_title = f"Чат {chat_id}"
                
                logger.info(f"Определен чат: ID={chat_id}, Title={chat_title}, IsPrivate={is_private_chat}")
                
                # Для приватных чатов используем специальную логику
                if is_private_chat:
                    try:
                        if user_id:
                            # Получаем сущность пользователя
                            user_entity = await self.client.get_entity(user_id)
                            logger.info(f"Успешно получена сущность пользователя {user_id}")
                            
                            # Формируем имя пользователя для отображения
                            full_name = getattr(user_entity, 'first_name', '')
                            if hasattr(user_entity, 'last_name') and user_entity.last_name:
                                full_name += f" {user_entity.last_name}"
                            
                            chat_title = f"Личный чат с {full_name}"
                        
                        # Подписываем пользователя на личный чат
                        subscription = subscribe_to_chat(self.db, user.id, chat_id, chat_title)
                        
                        await event.respond(
                            f"✅ Вы успешно подписались на саммари личного чата **{chat_title}**\n\n"
                            f"Вы будете получать саммари согласно вашим настройкам.",
                            parse_mode='md'
                        )
                        return
                        
                    except Exception as e:
                        chat_error = str(e)
                        logger.error(f"Ошибка при обработке приватного чата: {chat_error}")
                        await event.respond(
                            f"❌ Не удалось подписаться на личный чат **{chat_title}**.\n\n"
                            f"Ошибка: {chat_error}",
                            parse_mode='md'
                        )
                        return
                
                # Для групп и каналов - стандартная логика
                # Пытаемся получить сущность чата через главный клиент
                try:
                    # Загружаем сущность чата
                    chat_entity = await self.client.get_entity(chat_id)
                    logger.info(f"Успешно получена сущность чата {chat_id}")
                    
                    # Если получилось получить сущность, обновляем название из неё
                    if hasattr(chat_entity, 'title') and chat_entity.title:
                        chat_title = chat_entity.title
                    
                    # Подписываем пользователя на чат
                    subscription = subscribe_to_chat(self.db, user.id, chat_id, chat_title)
                    
                    await event.respond(
                        f"✅ Вы успешно подписались на саммари чата **{chat_title}**\n\n"
                        f"Вы будете получать саммари согласно вашим настройкам.",
                        parse_mode='md'
                    )
                    
                except Exception as e:
                    chat_error = str(e)
                    logger.error(f"Ошибка при получении сущности чата {chat_id}: {chat_error}")
                    
                    # Отображаем понятное сообщение об ошибке
                    if "Cannot get entity from a channel" in chat_error or "Could not find the input entity" in chat_error:
                        await event.respond(
                            f"❌ Не удалось подписаться на чат **{chat_title}**.\n\n"
                            f"Для корректной работы саммари основной клиент должен быть участником чата. "
                            f"Пожалуйста, добавьте аккаунт {PHONE} в чат как участника, а затем повторите попытку.\n\n"
                            f"Технические детали ошибки: {chat_error}",
                            parse_mode='md'
                        )
                    else:
                        await event.respond(
                            f"❌ Не удалось подписаться на чат **{chat_title}**.\n\n"
                            f"Причина: {chat_error}\n\n"
                            f"Пожалуйста, убедитесь, что аккаунт {PHONE} является участником чата.",
                            parse_mode='md'
                        )
                
            except Exception as e:
                logger.error(f"Ошибка при обработке пересланного сообщения: {str(e)}")
                await event.respond(
                    "❌ Произошла ошибка при обработке пересланного сообщения.\n\n"
                    f"Ошибка: {str(e)}\n\n"
                    "Попробуйте переслать другое сообщение из того же чата или обратитесь к администратору бота."
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
        
        # Обработчик команды /models
        @self.bot.on(events.NewMessage(pattern='/models'))
        async def models_handler(event):
            """Обрабатывает команду /models для отображения списка доступных моделей"""
            # Получаем список моделей
            models_list = await list_available_models()
            
            # Отправляем список моделей
            await event.respond(models_list, parse_mode='html')
            
        # Обработчик команды /model
        @self.bot.on(events.NewMessage(pattern=r'/model\s+(.+)'))
        async def model_handler(event):
            """Обрабатывает команду /model для установки модели для саммаризации"""
            sender = await event.get_sender()
            user = get_or_create_user(
                self.db, 
                sender.id, 
                sender.first_name,
                getattr(sender, 'last_name', None),
                getattr(sender, 'username', None)
            )
            
            # Извлекаем название модели из сообщения
            model_id = event.pattern_match.group(1).strip()
            
            # Проверяем, что модель существует в списке доступных
            if model_id in AVAILABLE_MODELS:
                # Обновляем настройки пользователя
                update_user_settings(self.db, user.id, openrouter_model=model_id)
                model_display_name = AVAILABLE_MODELS[model_id]
                
                await event.respond(
                    f"✅ Модель для саммаризации успешно изменена на:\n"
                    f"<b>{model_display_name}</b>\n\n"
                    f"<code>{model_id}</code>",
                    parse_mode='html'
                )
            else:
                # Если модель не найдена, показываем список доступных
                await event.respond(
                    f"❌ Модель <code>{model_id}</code> не найдена в списке доступных.\n\n"
                    f"Пожалуйста, выберите модель из следующего списка:",
                    parse_mode='html'
                )
                
                # Получаем и отправляем список моделей
                models_list = await list_available_models()
                await event.respond(models_list, parse_mode='html')

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
    
    # Получаем выбранную пользователем модель
    user_model = get_user_model(db, user.id)
    logger.info(f"Пользователь {user.telegram_id} использует модель: {user_model}")
        
    # Генерируем саммари для каждой подписки
    for subscription in subscriptions:
        try:
            # Проверяем, является ли это приватным чатом
            is_private_chat = str(subscription.chat_id).startswith('user_') or str(subscription.chat_id).startswith('name_')
            
            if is_private_chat:
                # Обработка приватного чата
                logger.info(f"Обрабатываем приватный чат: {subscription.chat_title}")
                
                # Для чатов с user_id
                if str(subscription.chat_id).startswith('user_'):
                    user_id = int(str(subscription.chat_id).replace('user_', ''))
                    logger.info(f"Извлечен user_id: {user_id}")
                    
                    # Получаем сущность пользователя
                    try:
                        chat_entity = await client.get_entity(user_id)
                    except Exception as e:
                        logger.error(f"Не удалось получить сущность пользователя {user_id}: {str(e)}")
                        if bot and chat_id:
                            await bot.send_message(
                                chat_id,
                                f"❌ Не удалось получить доступ к чату {subscription.chat_title}: {str(e)}"
                            )
                        continue
                else:
                    # Для чатов с именем без user_id
                    logger.warning(f"Чат идентифицирован только по имени: {subscription.chat_title}")
                    if bot and chat_id:
                        await bot.send_message(
                            chat_id,
                            f"⚠️ Чат {subscription.chat_title} идентифицирован только по имени. "
                            f"Для корректной работы переслите новое сообщение из этого чата."
                        )
                    continue
                
                # Определяем начальное сообщение
                last_processed_id = subscription.last_processed_message_id
                
                # Для приватных чатов получаем диалог с пользователем
                # Если нет последнего обработанного сообщения, берем сообщения за последние 24 часа
                if not last_processed_id:
                    # Получаем сообщения за последние 24 часа
                    yesterday = datetime.now(TIMEZONE) - timedelta(days=1)
                    messages = await client.get_messages(
                        chat_entity,  # Используем entity пользователя
                        limit=100,    # Ограничиваем количество сообщений
                        offset_date=yesterday
                    )
                else:
                    # Получаем сообщения с момента последнего обработанного
                    messages = await client.get_messages(
                        chat_entity,  # Используем entity пользователя
                        limit=100,
                        min_id=last_processed_id
                    )
            else:
                # Обработка групп и каналов (стандартная логика)
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
                if bot and chat_id:
                    await bot.send_message(
                        chat_id,
                        f"Нет новых сообщений в чате {subscription.chat_title} с момента последнего саммари."
                    )
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
            
            # Генерируем саммари с использованием выбранной модели
            summary_text = await generate_summary(messages_text, user_model)
            
            # Записываем саммари в базу данных
            summary = save_summary(
                db, 
                subscription.id, 
                summary_text,
                messages[0].id if messages else None,
                messages[-1].id if messages else None,
                model_used=user_model
            )
            
            # Обновляем последнее обработанное сообщение
            if messages:
                update_last_processed_message(db, subscription.id, messages[-1].id)
            
            # Отправляем саммари пользователю
            if bot and chat_id:
                model_display_name = AVAILABLE_MODELS.get(user_model, user_model)
                await bot.send_message(
                    chat_id,
                    f"📝 <b>Саммари чата {subscription.chat_title}</b>\n"
                    f"<i>Модель: {model_display_name}</i>\n\n"
                    f"{summary_text}",
                    parse_mode='html'
                )
                
        except Exception as e:
            logger.error(f"Ошибка при генерации саммари для чата {subscription.chat_title}: {str(e)}")
            if bot and chat_id:
                await bot.send_message(
                    chat_id,
                    f"❌ Не удалось сгенерировать саммари для чата {subscription.chat_title}: {str(e)}"
                )
                
    logger.info(f"Саммари сгенерированы для пользователя {user.telegram_id}") 