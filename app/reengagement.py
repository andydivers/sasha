REENGAGEMENT_MESSAGES = {
    "en": [
        "Hey! Just send a voice message — tell me what's happened since we last talked. 🎤",
        "Quick check-in. Any new expenses? Just press the mic and say it. 🎤",
        "Still here! Send a voice message whenever something comes up — I'll log it. 🎤",
        "How's your day going? Any coffee, meetings, or reminders to add? Just talk. 🎤",
    ],
    "ru": [
        "Привет! Отправь голосовое — расскажи, что произошло. 🎤",
        "Быстрый чек-ин. Новые траты? Нажми микрофон и скажи. 🎤",
        "Я тут! Отправь голосовое, когда что-то случится — я запишу. 🎤",
        "Как день? Кофе, встречи, напоминания? Просто говори вслух. 🎤",
    ],
    "es": [
        "¡Hola! Envía un mensaje de voz y cuéntame qué ha pasado. 🎤",
        "¿Cómo va el día? ¿Café, reuniones, gastos? Solo habla. 🎤",
    ],
    "fr": [
        "Salut ! Envoie un message vocal, raconte-moi tout. 🎤",
        "Ça va ? Nouveaux frais ? Appuie sur le micro et dis-le. 🎤",
    ],
    "zh": [
        "嘿！发送语音消息，告诉我发生了什么。🎤",
        "今天怎么样？有咖啡、会议或提醒要添加吗？直接说就行。🎤",
    ],
    "ar": [
        "مرحباً! أرسل رسالة صوتية وأخبرني what الجديد. 🎤",
        "كيف يومك؟ قهوة، اجتماعات، مصروفات؟ فقط تكلم. 🎤",
    ],
    "pt": [
        "Olá! Envia um áudio e me conta as novidades. 🎤",
        "Como está o dia? Café, reuniões, gastos? Só falar. 🎤",
    ],
    "de": [
        "Hallo! Schick eine Sprachnachricht und erzähl mir, was los ist. 🎤",
        "Wie läuft's? Kaffee, Termine, Ausgaben? Einfach sprechen. 🎤",
    ],
    "hi": [
        "नमस्ते! वॉइस मैसेज भेजें और बताएं क्या हुआ। 🎤",
        "दिन कैसा है? कॉफ़ी, मीटिंग, खर्च? बस बोलें। 🎤",
    ],
    "ja": [
        "お久しぶり！音声メッセージで最近のことを教えて。🎤",
        "今日はどう？コーヒー、会議、支出？話すだけ。🎤",
    ],
}


def get_reengagement_message(lang: str, index: int = 0) -> str:
    msgs = REENGAGEMENT_MESSAGES.get(lang, REENGAGEMENT_MESSAGES["en"])
    return msgs[index % len(msgs)]
