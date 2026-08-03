import json
import logging
import time
import re
import os
import urllib.request
from io import BytesIO

from groq import Groq

logger = logging.getLogger(__name__)


class _ToolCallFn:
    __slots__ = ("name", "arguments")

    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    __slots__ = ("function",)

    def __init__(self, name: str, arguments: str):
        self.function = _ToolCallFn(name, arguments)


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

# ─── Model config ───────────────────────────────────────────────────────────
# Primary: llama-3.1-8b-instant (fast, reliable native tool calling, free tier)
# Fallback: same model — single retry handles transient errors
PRIMARY_MODEL = "llama-3.1-8b-instant"
FALLBACK_MODEL = "llama-3.1-8b-instant"
OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct"


def create_groq_client(api_key: str) -> Groq:
    return Groq(api_key=api_key, timeout=30.0)


def _openrouter_chat(messages: list, tools: list, max_tokens: int, temperature: float = 0.1):
    """Call OpenRouter with native tool calling — used when Groq is rate-limited.

    Returns a dict-like message ({"content", "tool_calls"}) or None on failure.
    """
    key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("OPENROUTER_API_KEY2", "")
    if not key:
        logger.warning("OpenRouter fallback skipped: OPENROUTER_API_KEY not set")
        return None
    body = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]
    except Exception as e:
        logger.warning("OpenRouter fallback failed: %s", e)
        return None


def _or_tool_calls(message: dict) -> list[_ToolCall] | None:
    """Convert OpenRouter tool_calls to Groq SDK-compatible objects."""
    tcs = message.get("tool_calls")
    if not tcs:
        return None
    return [_ToolCall(tc["function"]["name"], tc["function"]["arguments"]) for tc in tcs]


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


# ─── Tool definitions (native Groq format) ──────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "Record an expense or purchase. Call this when user says they spent money (e.g., 'coffee $5', 'lunch 1200₽', 'uber $12', 'купил хлеб 50₽'). Extracts the amount, category and currency automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What was purchased or paid for"},
                    "amount": {"type": "string", "description": "The amount spent (e.g., '5', '1200', '12.50')"},
                    "currency": {"type": "string", "description": "Currency code from the message (e.g., 'THB', 'RUB', 'USD', 'EUR'). Extract from symbols like ₽/$/€/฿ or words like 'руб', 'bath', 'dollars'. If no currency mentioned, leave empty."},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_income",
            "description": "Record income or earnings. Call this when user says they received or earned money (e.g., 'earned $5000', 'salary 100000₽', 'получил 5000₽', 'фриланс 200$', 'got paid $3000'). Use for any money received, not spent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Source of income (e.g., 'salary', 'freelance', 'consulting')"},
                    "amount": {"type": "string", "description": "The amount earned (e.g., '5000', '100000')"},
                    "currency": {"type": "string", "description": "Currency code from the message (e.g., 'THB', 'RUB', 'USD', 'EUR'). Extract from symbols like ₽/$/€/฿ or words like 'руб', 'bath', 'dollars'. If no currency mentioned, leave empty."},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": "Add a task or to-do item. Call this when user says 'add task', 'remind me to', 'I need to', or mentions something they need to do later.",
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
            "description": "Log the user's current location or movement. Call this when user says where they are or what they're doing right now.",
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
            "description": "Set the user's timezone based on their current city or country. Call this when user mentions being in a new city or country.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or country name"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_sheets",
            "description": "Read from or write to a Google Sheet the user has connected. If no sheet is connected, saves locally.",
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
            "description": "Create a calendar event. Call this when user asks to schedule a meeting or create an event.",
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
            "name": "set_reminder",
            "description": "Set a reminder or alarm. Call this when user asks to be reminded about something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The reminder text"},
                    "when": {"type": "string", "description": "When to remind (e.g., 'in 1 hour', 'tomorrow 9am', 'через 2 часа')"},
                },
                "required": ["message", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": "Get total spent for a period. Call this when user asks how much they spent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Time period: today/yesterday/week/month/YYYY-MM"},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "Generate a report. Call this when user asks for a report or analytics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["excel", "html"], "description": "Report format"},
                    "topic": {"type": "string", "description": "What the report should cover"},
                },
                "required": ["format", "topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_receipt",
            "description": "Analyze a receipt or bill image. Call this when user sends a photo of a receipt. Extracts store name, total amount, date, and items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_description": {"type": "string", "description": "Description of what was extracted from the image"},
                },
                "required": ["image_description"],
            },
        },
    },
]


def build_system_prompt(lang: str) -> str:
    lang_instruction = LANG_INSTRUCTIONS.get(lang, "Respond in English.")
    base = (
        "You are Sasha, an AI business assistant for entrepreneurs and freelancers. "
        "Help users track expenses, manage tasks, and stay organized. "
        "Use tools when appropriate. Be concise and friendly. "
        "If the request doesn't match any tool, just respond conversationally. "
        + lang_instruction
    )
    base += "\n\nRULES:"
    base += "\n- If user mentions spending money, call add_expense. ALWAYS include the currency parameter (e.g., 'THB', 'RUB', 'USD', 'EUR') if detectable from the message."
    base += "\n- If user mentions receiving/earning money (salary, freelance, got paid), call add_income. ALWAYS include the currency parameter."
    base += "\n- Detect currency from symbols (₽=$=€=฿=£=¥) or words (руб/bath/dollars/euros/won/yuan/донгов) in the message. 'донг/донга/донгов' means VND."
    base += "\n- NEVER claim you saved/added/recorded an expense, income or task unless you actually called the function and got a result. If you did not call a function, just say what you understood and ask for confirmation."
    base += "\n- Use only valid ISO currency codes for the currency parameter: USD, EUR, RUB, GBP, THB, VND, CNY, JPY, KRW, INR, AED, BRL. Never invent codes like 'донга' or 'KHR' for 'донг'."
    base += "\n- IMPORTANT: If user mentions MULTIPLE expenses in one message (e.g., 'еда 150 бат, хостинг 600 рублей'), call add_expense SEPARATELY for EACH item. Each expense must have its own currency."
    base += "\n- If user mentions a task or something to do later, call add_todo."
    base += "\n- If user says where they are, call track_movement AND set_timezone_by_location."
    base += "\n- For events/meetings, call create_event."
    base += "\n- For reminders, call set_reminder."
    base += "\n- For spending summary, call get_spending_summary."
    base += "\n- When user sends a receipt photo, call analyze_receipt with extracted data."
    base += "\n- When user sends a bank statement, extract ALL transactions and call add_expense or add_income for each — include currency for every transaction."
    base += "\n- You may call MULTIPLE functions in one response when the user mentions multiple items to track."
    base += "\n\nUser commands: /currency USD — change currency. /tz — set timezone. /digest — daily summary. /undo — delete last entry."
    return base


def build_messages(text: str, lang: str, chat_history: list | None = None) -> list:
    messages = [{"role": "system", "content": build_system_prompt(lang)}]
    if chat_history:
        messages.extend(chat_history[-6:])
    messages.append({"role": "user", "content": text})
    return messages


def detect_intent(client: Groq, text: str, lang: str = "en", chat_history: list | None = None):
    """Detect user intent using native Groq tool calling.
    Returns: (text, latency, messages) or (tool_calls_list, latency, messages)
    """
    # Fast path — simple greeting, no API call
    if _is_simple_greeting(text, lang):
        reply = _get_simple_reply(text, lang)
        if reply:
            return reply, 0.0, None

    max_tokens = 2000 if _needs_reasoning(text) else 1000
    messages = build_messages(text, lang, chat_history)

    # Try primary model (70B), fallback to 8B
    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            start = time.perf_counter()
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=max_tokens,
            )
            elapsed = time.perf_counter() - start
            logger.info("Groq latency (%s): %.2fs", model, elapsed)

            choice = response.choices[0]
            msg = choice.message

            # Native tool calls
            if msg.tool_calls:
                messages.append(msg)
                return msg.tool_calls, elapsed, messages

            # Plain text response
            content = msg.content or ""
            return content, elapsed, messages

        except Exception as e:
            logger.warning("Groq error with %s: %s", model, e)
            continue

    # Try OpenRouter (Groq is rate-limited / down) — still with native tool calling
    or_msg = _openrouter_chat(messages, TOOLS, max_tokens)
    if or_msg:
        logger.info("OpenRouter fallback used")
        or_tcs = _or_tool_calls(or_msg)
        if or_tcs:
            messages.append({"role": "assistant", "content": or_msg.get("content") or None, "tool_calls": or_msg.get("tool_calls") or []})
            return or_tcs, elapsed, messages
        content = or_msg.get("content") or ""
        return content, elapsed, messages

    # Last resort: no tools, simple response
    try:
        start = time.perf_counter()
        response = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=max_tokens,
        )
        elapsed = time.perf_counter() - start
        choice = response.choices[0]
        msg = choice.message
        if msg.tool_calls:
            messages.append(msg)
            return msg.tool_calls, elapsed, messages
        content = msg.content or ""
        return content, elapsed, messages
    except Exception as e:
        logger.error("All Groq models failed: %s", e)
        return "Sorry, I'm having trouble connecting. Please try again.", 0.0, None


def chat_turn(client: Groq, messages: list):
    """Continue a multi-turn conversation with native tool calling."""
    max_tokens = 1000

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            start = time.perf_counter()
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=max_tokens,
            )
            elapsed = time.perf_counter() - start
            logger.info("Groq chat_turn (%s): %.2fs", model, elapsed)

            choice = response.choices[0]
            msg = choice.message

            if msg.tool_calls:
                messages.append(msg)
                return msg.tool_calls, messages

            content = msg.content or ""
            messages.append({"role": "assistant", "content": content})
            return content, messages

        except Exception as e:
            logger.warning("Groq chat_turn error with %s: %s", model, e)
            continue

    # OpenRouter fallback with native tool calling
    or_msg = _openrouter_chat(messages, TOOLS, max_tokens)
    if or_msg:
        or_tcs = _or_tool_calls(or_msg)
        if or_tcs:
            messages.append({"role": "assistant", "content": or_msg.get("content") or None, "tool_calls": or_msg.get("tool_calls") or []})
            return or_tcs, messages
        content = or_msg.get("content") or ""
        messages.append({"role": "assistant", "content": content})
        return content, messages

    return "I'm having trouble. Please try again.", messages


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
