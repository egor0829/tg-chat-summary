import os
from dotenv import load_dotenv
from pathlib import Path
import pytz

# Загрузка переменных окружения из .env файла
load_dotenv()

# Базовые пути
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"

# Настройки Telethon
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройки OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "meta-llama/llama-3-70b-instruct"  # Можно настроить другую модель

# Настройки для БД
DATABASE_URL = f"sqlite:///{DATA_DIR}/tg_summary.db"

# Настройки временной зоны
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "UTC"))

# Настройки логирования
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "tg_summary.log"

# Настройки для саммари
DEFAULT_SUMMARY_FORMAT = """
Основные темы:
{topics}

Ключевые обсуждения:
{discussions}

Важные объявления:
{announcements}
""" 