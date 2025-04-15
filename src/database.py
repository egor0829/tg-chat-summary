from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from datetime import datetime

from src.config import DATABASE_URL, DEFAULT_OPENROUTER_MODEL
from src.models import User, UserSettings, ChatSubscription, Summary, Base
from src.utils.logger import logger

# Настройка базы данных
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Создает таблицы в базе данных"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Таблицы базы данных созданы успешно")
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {str(e)}")
        raise


def get_db():
    """Возвращает сессию базы данных"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def get_or_create_user(db: Session, telegram_id: int, first_name: str, last_name: str = None, username: str = None) -> User:
    """
    Получает или создает пользователя в базе данных
    
    Args:
        db: Сессия базы данных
        telegram_id: ID пользователя в Telegram
        first_name: Имя пользователя
        last_name: Фамилия пользователя (опционально)
        username: Имя пользователя в Telegram (опционально)
        
    Returns:
        User: Объект пользователя
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    
    if user:
        # Обновляем существующего пользователя
        user.first_name = first_name
        user.last_name = last_name
        user.username = username
        db.commit()
        return user
        
    # Создаем нового пользователя
    user = User(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Создаем настройки по умолчанию
    settings = UserSettings(user_id=user.id)
    db.add(settings)
    db.commit()
    
    return user


def subscribe_to_chat(db: Session, user_id: int, chat_id: int, chat_title: str) -> ChatSubscription:
    """
    Подписывает пользователя на чат
    
    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        chat_id: ID чата в Telegram
        chat_title: Название чата
        
    Returns:
        ChatSubscription: Объект подписки на чат
    """
    # Проверяем существующую подписку
    subscription = db.query(ChatSubscription).filter(
        ChatSubscription.user_id == user_id,
        ChatSubscription.chat_id == chat_id
    ).first()
    
    if subscription:
        # Если подписка существует, активируем ее и обновляем название
        subscription.is_active = True
        subscription.chat_title = chat_title
        db.commit()
        return subscription
        
    # Создаем новую подписку
    subscription = ChatSubscription(
        user_id=user_id,
        chat_id=chat_id,
        chat_title=chat_title,
        is_active=True
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    
    return subscription


def unsubscribe_from_chat(db: Session, user_id: int, chat_id: int) -> bool:
    """
    Отписывает пользователя от чата
    
    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        chat_id: ID чата в Telegram
        
    Returns:
        bool: True если операция успешна, иначе False
    """
    subscription = db.query(ChatSubscription).filter(
        ChatSubscription.user_id == user_id,
        ChatSubscription.chat_id == chat_id
    ).first()
    
    if not subscription:
        return False
        
    subscription.is_active = False
    db.commit()
    return True


def update_user_settings(db: Session, user_id: int, delivery_time: str = None, 
                         delivery_frequency: str = None, timezone: str = None,
                         openrouter_model: str = None) -> UserSettings:
    """
    Обновляет настройки пользователя
    
    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        delivery_time: Время доставки (формат HH:MM)
        delivery_frequency: Частота доставки (daily, weekly)
        timezone: Временная зона
        openrouter_model: Модель OpenRouter
        
    Returns:
        UserSettings: Обновленные настройки пользователя
    """
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    
    if not settings:
        settings = UserSettings(
            user_id=user_id,
            openrouter_model=DEFAULT_OPENROUTER_MODEL
        )
        db.add(settings)
        
    if delivery_time:
        settings.delivery_time = delivery_time
        
    if delivery_frequency:
        settings.delivery_frequency = delivery_frequency
        
    if timezone:
        settings.timezone = timezone
        
    if openrouter_model:
        settings.openrouter_model = openrouter_model
        
    db.commit()
    db.refresh(settings)
    return settings


def get_user_model(db: Session, user_id: int) -> str:
    """
    Получает выбранную пользователем модель
    
    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        
    Returns:
        str: Название модели
    """
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    
    if not settings or not settings.openrouter_model:
        return DEFAULT_OPENROUTER_MODEL
        
    return settings.openrouter_model


def save_summary(db: Session, subscription_id: int, content: str, 
                from_message_id: int = None, to_message_id: int = None,
                model_used: str = None) -> Summary:
    """
    Сохраняет саммари в базу данных
    
    Args:
        db: Сессия базы данных
        subscription_id: ID подписки
        content: Текст саммари
        from_message_id: ID начального сообщения
        to_message_id: ID конечного сообщения
        model_used: Использованная модель
        
    Returns:
        Summary: Созданный объект саммари
    """
    summary = Summary(
        subscription_id=subscription_id,
        content=content,
        from_message_id=from_message_id,
        to_message_id=to_message_id,
        created_at=datetime.utcnow(),
        model_used=model_used
    )
    
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary
    
    
def update_last_processed_message(db: Session, subscription_id: int, message_id: int) -> bool:
    """
    Обновляет ID последнего обработанного сообщения для подписки
    
    Args:
        db: Сессия базы данных
        subscription_id: ID подписки
        message_id: ID сообщения
        
    Returns:
        bool: True если обновление успешно, иначе False
    """
    subscription = db.query(ChatSubscription).filter(
        ChatSubscription.id == subscription_id
    ).first()
    
    if not subscription:
        return False
        
    subscription.last_processed_message_id = message_id
    db.commit()
    return True 