import logging
import time

from groq import Groq

logger = logging.getLogger(__name__)


def create_groq_client(api_key: str) -> Groq:
    return Groq(api_key=api_key)


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


def detect_intent(client: Groq, text: str, lang: str = "en", chat_history: list | None = None):
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
        model="llama-3.3-70b-versatile",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1,
        max_tokens=500,
    )
    elapsed = time.perf_counter() - start
    logger.info("Groq latency: %.2fs", elapsed)

    choice = response.choices[0]
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        return choice.message.tool_calls[0], elapsed
    return choice.message.content, elapsed
