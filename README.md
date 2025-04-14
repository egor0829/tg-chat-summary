# Telegram Summary Bot

Бот для создания саммари чатов Telegram с использованием OpenRouter API. Бот может регулярно анализировать сообщения из выбранных чатов и отправлять их краткое содержание пользователю.

## Возможности

- Подписка на саммари чатов
- Настройка времени и периодичности получения саммари (ежедневно или еженедельно)
- Ручной запрос саммари по требованию
- Саммари создаются с помощью модели LLaMA через OpenRouter API

## Технический стек

- Python 3.10+
- Telethon (для работы с Telegram API)
- OpenRouter API (для генерации саммари)
- SQLAlchemy (для хранения данных и настроек)
- Docker (для удобного развертывания)

## Установка и настройка

### Предварительные требования

1. API ID и API Hash от Telegram (получить на [my.telegram.org](https://my.telegram.org/))
2. Номер телефона для аутентификации в Telegram
3. Токен бота от @BotFather
4. API ключ от [OpenRouter](https://openrouter.ai/)

### Настройка переменных окружения

Создайте файл `.env` на основе примера `.env.example`:

```bash
cp .env.example .env
```

Заполните переменные окружения в файле `.env`:

```
# Telethon credentials
API_ID=ваш_api_id
API_HASH=ваш_api_hash
PHONE=ваш_номер_телефона

# Telegram bot token (получить у @BotFather)
BOT_TOKEN=токен_вашего_бота

# OpenRouter API key
OPENROUTER_API_KEY=ваш_ключ_openrouter

# Временная зона для планировщика
TIMEZONE=Europe/Moscow
```

### Запуск с помощью Docker

1. Убедитесь, что у вас установлены Docker и Docker Compose
2. Запустите контейнер:

```bash
docker-compose up -d
```

### Запуск без Docker

1. Создайте виртуальное окружение и активируйте его:

```bash
python -m venv venv
source venv/bin/activate  # Для Linux/MacOS
# или
venv\Scripts\activate  # Для Windows
```

2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Запустите приложение:

```bash
python -m src.main
```

## Использование

После запуска бота, следуйте этим шагам для настройки:

1. Откройте бота в Telegram и отправьте команду `/start`
2. Настройте время и частоту доставки саммари командами:
   - `/time ЧЧ:ММ` (например, `/time 08:00`)
   - `/frequency daily` или `/frequency weekly`
3. Чтобы добавить чат для саммари, перешлите боту любое сообщение из этого чата
4. Для получения саммари прямо сейчас, используйте команду `/summary`
5. Для просмотра списка подписок, используйте команду `/list`
6. Для отписки от чата, используйте команду `/unsubscribe`

## Техническая информация

### Архитектура

- **Telegram-клиент**: Использует библиотеку Telethon для взаимодействия с API Telegram. Читает сообщения из выбранных чатов и отправляет саммари пользователю через бота.
- **Планировщик**: Отвечает за запуск задач по расписанию, учитывая настройки пользователя.
- **OpenRouter API**: Используется для генерации саммари с помощью моделей LLM.
- **База данных**: SQLite для хранения настроек пользователя, информации о подписках и истории саммари.

## Лицензия

MIT 