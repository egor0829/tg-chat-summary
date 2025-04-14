FROM python:3.10-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов приложения
COPY . .

# Создание директории для данных и логов
RUN mkdir -p data logs

# Установка переменной окружения
ENV PYTHONPATH=/app

# Запуск приложения
CMD ["python", "-m", "src.main"] 