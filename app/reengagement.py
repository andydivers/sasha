REENGAGEMENT_MESSAGES = {
    "en": [
        "Hi! Just tap the mic and say what's new.\n\n\"coffee $5\" or \"at work\" or \"remind me in 1h\"\n\nI'll log it.",
        "Quick check-in. Press the mic and tell me:\n\n\"coffee $5\" or \"meeting Friday 10am\" or \"all good\"",
        "Any new expenses? Tap the mic and say it in 3 seconds.\n\n\"lunch $12\" or \"at the gym\" or \"nope\"",
        "How's your day? One voice message and I'll handle it.\n\n\"takeaway $8\" or \"remind me tomorrow\"",
    ],
    "ru": [
        "Привет! Нажми микрофон и скажи, что нового.\n\n«кофе 300₽» или «я на работе» или «напомни через час»\n\nЯ запишу.",
        "Быстрый чек-ин. Нажми микрофон и скажи:\n\n«кофе 300₽» или «встреча в пятницу в 10» или «всё ок»",
        "Новые траты? Нажми микрофон и скажи за 3 секунды.\n\n«обед 500₽» или «я в зале» или «нет»",
        "Как день? Одно голосовое — и я всё понял.\n\n«доставка 800₽» или «напомни завтра»",
    ],
    "es": [
        "¡Hola! Toca el micrófono y dime qué hay de nuevo.\n\n\"café $5\" o \"en el trabajo\" o \"recuérdame en 1h\"",
        "¿Nuevos gastos? Toca el micrófono y dilo en 3 segundos.\n\n\"comida $12\" o \"en el gimnasio\" o \"no\"",
    ],
    "fr": [
        "Salut ! Appuie sur le micro et dis ce qui est nouveau.\n\n\"café 5€\" ou \"au travail\" ou \"rappelle-moi dans 1h\"",
        "Nouveaux frais ? Appuie sur le micro et dis-le en 3 secondes.\n\n\"déjeuner 12€\" ou \"à la salle\" ou \"non\"",
    ],
    "zh": [
        "嘿！按下麦克风，说说新鲜事。\n\n“咖啡5美元”或“在工作”或“1小时后提醒我”",
        "新支出？按麦克风，3秒说完。\n\n“午餐12美元”或“在健身房”或“没有”",
    ],
    "ar": [
        "مرحباً! اضغط على الميكروفون وقل ما الجديد.\n\n«قهوة 5 دولارات» أو «في العمل» أو «ذكرني بعد ساعة»",
        "مصروفات جديدة؟ اضغط على الميكروفون وقلها في 3 ثوانٍ.\n\n«غداء 12 دولاراً» أو «في النادي» أو «لا»",
    ],
    "pt": [
        "Olá! Aperte o mic e diga o que há de novo.\n\n\"café $5\" ou \"no trabalho\" ou \"lembre-me em 1h\"",
        "Novos gastos? Aperte o mic e diga em 3 segundos.\n\n\"almoço $12\" ou \"na academia\" ou \"não\"",
    ],
    "de": [
        "Hallo! Tipp aufs Mikro und sag, was los ist.\n\n\"Kaffee 5€\" oder \"bei der Arbeit\" oder \"erinnere mich in 1h\"",
        "Neue Ausgaben? Tipp aufs Mikro und sag's in 3 Sekunden.\n\n\"Mittagessen 12€\" oder \"im Fitness\" oder \"nein\"",
    ],
    "hi": [
        "नमस्ते! माइक दबाएँ और बताएँ क्या नया है।\n\n\"कॉफ़ी ₹400\" या \"काम पर\" या \"1 घंटे में याद दिलाएं\"",
        "नए खर्च? माइक दबाएँ और 3 सेकंड में बताएँ।\n\n\"लंच ₹600\" या \"जिम में\" या \"नहीं\"",
    ],
    "ja": [
        "こんにちは！マイクを押して、近況を教えて。\n\n「コーヒー5ドル」または「仕事中」または「1時間後にリマインド」",
        "新しい支出は？マイクを押して3秒で言って。\n\n「昼食12ドル」または「ジム」または「なし」",
    ],
}

def get_reengagement_message(lang: str, index: int = 0) -> str:
    msgs = REENGAGEMENT_MESSAGES.get(lang, REENGAGEMENT_MESSAGES["en"])
    return msgs[index % len(msgs)]
