import aiohttp
import json
from src.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from src.utils.logger import logger

async def generate_summary(messages_text: str) -> str:
    """
    Генерирует саммари сообщений с помощью OpenRouter API
    
    Args:
        messages_text: Текст сообщений для саммаризации
        
    Returns:
        str: Сгенерированное саммари
    """
    if not messages_text.strip():
        return "Нет сообщений для саммаризации."
    
    prompt = f"""Пожалуйста, создай краткое саммари следующих сообщений из телеграм-чата. 
Структурируй саммари по таким разделам:
1. Основные темы: перечисли 3-5 главных тем, которые обсуждались
2. Ключевые обсуждения: выдели 2-3 важных обсуждения и их основные моменты
3. Важные объявления: перечисли важные объявления или информацию, если такие были

Сообщения для саммаризации:
{messages_text}

Составь максимально информативное саммари, выделяя самое важное. Постарайся сделать его лаконичным, но полезным.
"""

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com",
        }
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system", 
                    "content": "Ты - помощник, который создает краткие и информативные саммари телеграм-чатов на русском языке."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"OpenRouter API ошибка: {response.status}, {error_text}")
                    return f"Ошибка генерации саммари: {response.status}"
                
                result = await response.json()
                summary = result["choices"][0]["message"]["content"]
                return summary
                
    except Exception as e:
        logger.error(f"Ошибка при генерации саммари: {str(e)}")
        return f"Не удалось сгенерировать саммари: {str(e)}" 