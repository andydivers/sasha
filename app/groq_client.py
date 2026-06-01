import logging
import time
import re
from io import BytesIO

from groq import Groq

logger = logging.getLogger(__name__)


SIMPLE_GREETINGS_EN = frozenset({"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "thanks", "thank you", "thx", "ok", "okay", "bye", "goodbye", "cool", "great", "nice"})
SIMPLE_GREETINGS_RU = frozenset({"привет", "здравствуй", "здравствуйте", "дарова", "ку", "спасибо", "благодарю", "ок", "ладно", "понял", "пока", "до свидания", "хорошо", "отлично", "круто"})

SIMPLE_REPLIES_EN = {
    "hello": "Hello! 👋 How can I help you today?",
    "hi": "Hi there! What can I do for you?",
    "good morning": "Good morning! How can I assist you?",
    "good afternoon": "Good afternoon! What can I help with?",
    "good evening": "Good evening! Need anything?",
    "thanks": "You're welcome! 😊",
    "bye": "Goodbye! Feel free to come back anytime.",
    "ok": "Got it! Tell me what you need.",
    "cool": "😊 Let me know if you need anything else!",
}

SIMPLE_REPLIES_RU = {
    "привет": "Привет! 👋 Чем могу помочь?",
    "здравствуй": "Здравствуйте! Чем могу помочь?",
    "спасибо": "Пожалуйста! 😊",
    "пока": "До свидания! Обращайся ещё.",
    "ок": "Понял! Напиши, что нужно сделать.",
    "хорошо": "Договорились! Напиши, если что.",
    "круто": "😊 Рад помочь! Напиши, если нужно ещё что-то.",
}

REASONING_KEYWORDS = frozenset({
    "analyze", "analysis", "compare", "comparison", "calculate", "calculation",
    "trend", "statistics", "statistical", "forecast", "predict", "prediction",
    "summary", "summarize", "deep", "complex", "evaluate", "evaluation",
    "анализ", "анализировать", "сравнить", "сравнение", "рассчитать",
    "расчёт", "тенденция", "статистика", "прогноз", "предсказать",
    "резюме", "суммировать", "оценить", "оценка", "сложный",
})


def create_groq_client(api_key: str) -> Groq:
    return Groq(api_key=api_key, timeout=30.0)


LANG_INSTRUCTIONS = {
    "en": "Respond in English.",
    "ru": "Отвечай на русском языке.",
    "es": "Responde en español.",
    "fr": "Réponds en français.",
    "zh": "请用中文回答。",
    "ar": "الرد باللغة العربية.",
    "pt": "Responda em português.",
    "de": "Antworte auf Deutsch.",
    "hi": "हिंदी में उत्तर दें।",
    "ja": "日本語で答えてください。",
}


def _is_simple_greeting(text: str, lang: str) -> bool:
    t = text.strip().lower().rstrip(".!?,")
    if lang == "ru" and t in SIMPLE_GREETINGS_RU:
        return True
    if t in SIMPLE_GREETINGS_EN:
        return True
    return False


def _get_simple_reply(text: str, lang: str) -> str | None:
    t = text.strip().lower().rstrip(".!?,")
    if lang == "ru":
        return SIMPLE_REPLIES_RU.get(t)
    return SIMPLE_REPLIES_EN.get(t)


def _needs_reasoning(text: str) -> bool:
    words = set(re.findall(r"[a-zа-яё]+", text.lower()))
    return bool(words & REASONING_KEYWORDS)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_screenshot",
            "description": "Analyze a screenshot or image. Call this when user sends an image or asks to analyze something visual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to analyze or look for in the image"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "Record an expense or purchase. Call this when user says they spent money (e.g., 'coffee $5', 'lunch 1200₽', 'uber $12', 'купил хлеб 50₽'). Extracts the amount and category automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What was purchased or paid for"},
                    "amount": {"type": "string", "description": "The amount spent (e.g., '5', '1200', '12.50')"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": "Add a task or to-do item. Call this when user says 'add task', 'remind me to', 'I need to', or mentions something they need to do later (e.g., 'add task buy milk', 'напомни позвонить маме', 'нужно оплатить налоги').",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The task or to-do text"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_movement",
            "description": "Log the user's current location or movement. Call this when user says where they are, where they're going, or what they're doing right now (e.g., 'at work', 'at the gym', 'leaving office', 'at the store'). Saves with the current timestamp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The location or place the user is at"},
                    "description": {"type": "string", "description": "Optional additional context or note"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timezone_by_location",
            "description": "Set the user's timezone based on their current city or country (e.g., 'I'm in Bangkok', 'just arrived in Bali', 'I'm in Thailand'). Call this when user mentions being in a new city or country. Changes how times are displayed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or country name (e.g., 'Bangkok', 'Bali', 'Moscow', 'Thailand')"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_sheets",
            "description": "Read from or write to a Google Sheet the user has connected. If no sheet is connected, saves locally. Use this for expense tracking, notes, or sheet operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "write"], "description": "Read or write data"},
                    "description": {"type": "string", "description": "What data to read or write"},
                },
                "required": ["action", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Create a calendar event. Call this when user asks to schedule a meeting, set a reminder, or create an event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title"},
                    "date": {"type": "string", "description": "Date of the event"},
                    "time": {"type": "string", "description": "Time of the event"},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "Generate a PDF, Excel, or HTML report. Call this when user asks for a report, summary, or analytics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["pdf", "excel", "html"], "description": "Report format"},
                    "topic": {"type": "string", "description": "What the report should cover"},
                },
                "required": ["format", "topic"],
            },
        },
    },
]


def build_system_prompt(lang: str) -> str:
    lang_instruction = LANG_INSTRUCTIONS.get(lang, "Respond in English.")
    base = "You are Sasha, an AI business assistant. Help users with their requests. Use tools when appropriate. Be concise and friendly. If the request doesn't match any tool, just respond conversationally. " + lang_instruction
    base += "\n\nRULES FOR USING TOOLS:"
    base += "\n- If the user mentions spending money (e.g., 'coffee $5', 'lunch 1200₽', 'uber $12', 'купил хлеб'), call add_expense. Extract the amount if present."
    base += "\n- If the user says 'add task', 'remind me to', 'I need to', or mentions something to do later, call add_todo."
    base += "\n- If the user says where they are or what they're doing right now (e.g., 'at work', 'at the gym', 'leaving office', 'я на работе'), call track_movement."
    base += "\n- If the user mentions being in a new city or country, call set_timezone_by_location."
    base += "\n- For calendar events (meetings, appointments), call create_event."
    base += "\n- manage_sheets also works for tracking expenses and notes (saves locally if no Google Sheet connected)."
    base += "\n\nIMPORTANT: Always end your response with '🎤 Reply with a voice message' (or equivalent in the user's language) to encourage voice input. This is the primary way users interact with you."
    return base


def build_messages(text: str, lang: str, chat_history: list | None = None) -> list:
    messages = [{"role": "system", "content": build_system_prompt(lang)}]
    if chat_history:
        messages.extend(chat_history[-6:])
    messages.append({"role": "user", "content": text})
    return messages


def detect_intent(client: Groq, text: str, lang: str = "en", chat_history: list | None = None):
    # fast path — simple greeting, no API call
    if _is_simple_greeting(text, lang):
        reply = _get_simple_reply(text, lang)
        if reply:
            return reply, 0.0, None

    if _needs_reasoning(text):
        max_tokens = 1000
    else:
        max_tokens = 500

    messages = build_messages(text, lang, chat_history)

    start = time.perf_counter()
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.1,
        max_tokens=max_tokens,
    )
    elapsed = time.perf_counter() - start
    logger.info("Groq latency: %.2fs", elapsed)

    choice = response.choices[0]
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        messages.append(choice.message)
        return choice.message.tool_calls, elapsed, messages
    return choice.message.content, elapsed, messages


def chat_turn(client: Groq, messages: list):
    """Continue a multi-turn conversation. Returns (text, messages) or (tool_calls, messages)."""
    start = time.perf_counter()
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.1,
        max_tokens=1000,
    )
    elapsed = time.perf_counter() - start
    logger.info("Groq chat_turn latency: %.2fs", elapsed)

    choice = response.choices[0]
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        messages.append(choice.message)
        return choice.message.tool_calls, messages
    return choice.message.content, messages


def transcribe_audio(client: Groq, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    buffer = BytesIO(audio_bytes)
    buffer.name = filename
    try:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=(filename, buffer, "audio/ogg"),
            response_format="text",
        )
        return transcription.strip()
    except Exception as e:
        logger.error("Groq transcription error: %s", e)
        raise
