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


def detect_intent(client: Groq, text: str, lang: str = "en", chat_history: list | None = None):
    # fast path — simple greeting, no API call
    if _is_simple_greeting(text, lang):
        reply = _get_simple_reply(text, lang)
        if reply:
            return reply, 0.0

    # choose model based on complexity
    if _needs_reasoning(text):
        model = "llama-3.3-70b-versatile"
        max_tokens = 1000
    else:
        model = "llama-3.3-70b-versatile"
        max_tokens = 500

    tools = [
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
                "name": "manage_sheets",
                "description": "Read from or write to Google Sheets. Call this when user asks to track expenses, update budgets, or view spreadsheet data.",
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

    lang_instruction = LANG_INSTRUCTIONS.get(lang, "Respond in English.")
    system_prompt = f"You are Sasha, an AI business assistant. Help users with their requests. Use tools when appropriate. Be concise and friendly. If the request doesn't match any tool, just respond conversationally. {lang_instruction}"
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history[-6:])
    messages.append({"role": "user", "content": text})

    start = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1,
        max_tokens=max_tokens,
    )
    elapsed = time.perf_counter() - start
    logger.info("Groq %s latency: %.2fs", model, elapsed)

    choice = response.choices[0]
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        return choice.message.tool_calls[0], elapsed
    return choice.message.content, elapsed


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
