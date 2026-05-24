TRANSLATIONS = {
    "en": {
        "welcome": "Hi! I'm <b>Viktor</b> — your AI assistant.\n\nI can:\n• Analyze screenshots\n• Work with Google Sheets\n• Create calendar events\n• Generate reports\n\n<i>Language can be changed anytime with /lang</i>",
        "help": "/start — Restart\n/help — This help\n/ping — Ping test\n/lang — Change language\n/webhook — Webhook status",
        "ping": "Pong!",
        "webhook": "<b>Webhook:</b>\nURL: {url}\nErrors: {errors}",
        "webhook_not_set": "Not set",
        "webhook_no_errors": "None",
        "lang_prompt": "Choose your language / Выбери язык:",
        "lang_changed": "Language changed to English!",
        "thinking": "Thinking...",
        "error": "Sorry, I ran into an issue. Try again in a moment.",
        "not_ready": "I'm not fully set up yet. Try /help",
    },
    "ru": {
        "welcome": "Привет! Я <b>Viktor</b> — твой AI-ассистент.\n\nЯ умею:\n• Анализировать скриншоты\n• Работать с Google Таблицами\n• Создавать события в календаре\n• Формировать отчёты\n\n<i>Язык можно сменить через /lang</i>",
        "help": "/start — Начать\n/help — Справка\n/ping — Проверка\n/lang — Сменить язык\n/webhook — Статус вебхука",
        "ping": "Понг!",
        "webhook": "<b>Вебхук:</b>\nURL: {url}\nОшибок: {errors}",
        "webhook_not_set": "Не установлен",
        "webhook_no_errors": "Нет",
        "lang_prompt": "Choose your language / Выбери язык:",
        "lang_changed": "Язык изменён на русский!",
        "thinking": "Думаю...",
        "error": "Извини, произошла ошибка. Попробуй ещё раз.",
        "not_ready": "Я ещё не до конца настроен. Попробуй /help",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    text = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
