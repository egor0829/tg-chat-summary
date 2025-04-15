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
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3-70b-instruct"  # Модель по умолчанию

# Список доступных моделей OpenRouter
AVAILABLE_MODELS = {
    "meta-llama/llama-3-70b-instruct": "Llama 3 70B (рекомендуется)",
    "meta-llama/llama-3-8b-instruct": "Llama 3 8B (быстрее)",
    "anthropic/claude-3-opus-20240229": "Claude 3 Opus (высокое качество)",
    "anthropic/claude-3-sonnet-20240229": "Claude 3 Sonnet (баланс)",
    "anthropic/claude-3-haiku-20240307": "Claude 3 Haiku (быстрее)",
    "google/gemini-1.5-pro-latest": "Gemini 1.5 Pro",
    "mistralai/mixtral-8x7b-instruct": "Mixtral 8x7B",
    "mistralai/mistral-7b-instruct": "Mistral 7B (быстрее)",
    "openai/gpt-4o": "GPT-4o",
    "openai/gpt-3.5-turbo": "GPT-3.5 Turbo (быстрее)",
}

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