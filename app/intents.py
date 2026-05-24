import logging
import json

from app.i18n import t

logger = logging.getLogger(__name__)


async def handle_tool_call(tool_call, lang: str = "en") -> str:
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    handlers = {
        "analyze_screenshot": _handle_analyze_screenshot,
        "manage_sheets": _handle_manage_sheets,
        "create_event": _handle_create_event,
        "generate_report": _handle_generate_report,
    }

    handler = handlers.get(name)
    if handler:
        return handler(args, lang)
    return f"I don't know how to handle {name} yet."


def _handle_analyze_screenshot(args: dict, lang: str) -> str:
    if lang == "ru":
        return "Понял! Я проанализирую этот скриншот. Отправь изображение, и я обработаю его."
    return "Got it! I'll analyze that screenshot. Send me the image and I'll process it."


def _handle_manage_sheets(args: dict, lang: str) -> str:
    action = args.get("action", "read")
    if lang == "ru":
        if action == "write":
            return "Запишу данные в Google Таблицу. Полная интеграция будет в День 5."
        return "Проверяю таблицу. Чтение из Google Sheets — в День 5."
    if action == "write":
        return "Sure! I'll write that to your Google Sheet (full integration in Day 5)."
    return "Let me check your spreadsheet (full integration in Day 5)."


def _handle_create_event(args: dict, lang: str) -> str:
    summary = args.get("summary", "Event")
    date = args.get("date", "—")
    time = args.get("time", "—")
    if lang == "ru":
        return f"Событие создано: <b>{summary}</b>\nДата: {date}\nВремя: {time}\n\n(Полная интеграция с Google Calendar — в День 6)"
    return (
        f"Calendar event created: <b>{summary}</b>\n"
        f"Date: {date}\n"
        f"Time: {time}\n\n"
        f"(Full Google Calendar integration comes Day 6)"
    )


def _handle_generate_report(args: dict, lang: str) -> str:
    fmt = args.get("format", "pdf")
    topic = args.get("topic", "")
    if lang == "ru":
        return f"Генерирую отчёт в <b>{fmt.upper()}</b> по теме: {topic}\n(Полная реализация — в День 8)."
    return (
        f"Generating <b>{fmt.upper()}</b> report on: {topic}\n"
        f"Your report will be ready shortly (full implementation Day 8)."
    )
