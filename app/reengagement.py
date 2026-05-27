REENGAGEMENT_MESSAGES = {
    "en": [
        "Hey! It's been a while since we last chatted. Need me to track any expenses, set reminders, or log your movements? 🎤",
        "Hi there! Just checking in — want to update your budget, add a note, or see what's on your calendar? 📋",
        "Long time no see! I can still track your expenses, movements, and todos. Send a voice message anytime! 🎤",
        "Quick check-in! Got any new expenses to log? Or want to know your spending trends this week? 📊",
    ],
    "ru": [
        "Привет! Давно не общались. Нужно записать расходы, поставить напоминание или отметить перемещение? 🎤",
        "Здорóво! Как дела? Хочешь обновить бюджет, добавить заметку или проверить календарь? 📋",
        "Давно не виделись! Я всё ещё помню твои расходы, перемещения и задачи. Просто отправь голосовое! 🎤",
        "Быстрый чек-ин! Есть новые траты? Или хочешь узнать статистику за неделю? 📊",
    ],
    "es": [
        "¡Hola! Ha pasado tiempo. ¿Necesitas registrar gastos, crear recordatorios o moverte? 🎤",
    ],
    "fr": [
        "Salut ! Ça fait un moment. Besoin d'enregistrer des dépenses, des rappels ou vos déplacements ? 🎤",
    ],
    "zh": [
        "嘿！很久没聊了。需要记录开支、设置提醒或记录行程吗？🎤",
    ],
    "ar": [
        "مرحباً! مضى وقت طويل. هل تحتاج إلى تسجيل المصروفات أو التذكيرات أو الحركات؟ 🎤",
    ],
    "pt": [
        "Olá! Quanto tempo. Precisa registrar despesas, lembretes ou movimentos? 🎤",
    ],
    "de": [
        "Hallo! Lange nicht gesehen. Ausgaben erfassen, Erinnerungen oder Bewegungen protokollieren? 🎤",
    ],
    "hi": [
        "नमस्ते! बहुत समय हो गया। खर्च, रिमाइंडर या मूवमेंट लॉग करने की ज़रूरत है? 🎤",
    ],
    "ja": [
        "お久しぶりです！支出の記録、リマインダー、移動の追跡はいかがですか？🎤",
    ],
}


def get_reengagement_message(lang: str, index: int = 0) -> str:
    msgs = REENGAGEMENT_MESSAGES.get(lang, REENGAGEMENT_MESSAGES["en"])
    return msgs[index % len(msgs)]
