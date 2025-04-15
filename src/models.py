from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
from typing import List, Optional
from src.config import DATABASE_URL, DEFAULT_OPENROUTER_MODEL

Base = declarative_base()

# Создаем движок базы данных
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    chats = relationship("ChatSubscription", back_populates="user")
    settings = relationship("UserSettings", uselist=False, back_populates="user")


class ChatSubscription(Base):
    """Модель подписки на чат"""
    __tablename__ = "chat_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    chat_id = Column(Integer)  # ID чата в Telegram
    chat_title = Column(String)
    is_active = Column(Boolean, default=True)
    last_processed_message_id = Column(Integer, nullable=True)
    user = relationship("User", back_populates="chats")
    summaries = relationship("Summary", back_populates="subscription")


class UserSettings(Base):
    """Настройки пользователя"""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    delivery_time = Column(String, default="10:00")  # Формат HH:MM
    delivery_frequency = Column(String, default="daily")  # daily, weekly
    timezone = Column(String, default="UTC")
    is_active = Column(Boolean, default=True)
    openrouter_model = Column(String, default=DEFAULT_OPENROUTER_MODEL)  # Модель OpenRouter
    user = relationship("User", back_populates="settings")


class Summary(Base):
    """Модель саммари"""
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("chat_subscriptions.id"))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    from_message_id = Column(Integer, nullable=True)
    to_message_id = Column(Integer, nullable=True)
    model_used = Column(String, nullable=True)  # Какая модель использовалась
    subscription = relationship("ChatSubscription", back_populates="summaries")


# Создаем таблицы
def init_db():
    Base.metadata.create_all(bind=engine) 