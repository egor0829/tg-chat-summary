from loguru import logger
import sys
from src.config import LOG_FILE

# Настройка логирования
logger.remove()  # Удаляем стандартный обработчик

# Добавляем обработчик для вывода в файл
logger.add(
    LOG_FILE,
    rotation="10 MB",
    retention="1 week",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# Добавляем обработчик для вывода в консоль
logger.add(
    sys.stderr,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | <level>{level}</level> | {message}"
) 