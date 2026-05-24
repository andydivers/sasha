import logging
import json

from app.i18n import t
from app.sheets_client import read_sheet, write_sheet, append_row, get_service_email, is_ready as sheets_ready
from app.calendar_client import create_event, is_ready as calendar_ready

logger = logging.getLogger(__name__)


async def handle_tool_call(tool_call, lang: str = "en", sheet_url: str | None = None) -> str:
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    if name == "manage_sheets":
        return _handle_manage_sheets(args, lang, sheet_url)

    handlers = {
        "analyze_screenshot": _handle_analyze_screenshot,
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


def _handle_manage_sheets(args: dict, lang: str, sheet_url: str | None = None) -> str:
    action = args.get("action", "read")
    description = args.get("description", "")

    if not sheet_url:
        if lang == "ru":
            return "Сначала подключи таблицу через /sheet https://..."
        return "First connect your sheet via /sheet https://..."

    if not sheets_ready():
        if lang == "ru":
            return "Google Sheets не настроен на сервере."
        return "Google Sheets is not configured."

    try:
        if action == "write":
            row = [description]
            if "amount" in args or "sum" in description.lower():
                import re
                nums = re.findall(r"[\d,.]+", description)
                if nums:
                    row = [description, nums[0]]
            append_row(sheet_url, row)
            return f"Written to sheet: {description}" if lang != "ru" else f"Записано в таблицу: {description}"

        data = read_sheet(sheet_url)
        if not data:
            return "Sheet is empty." if lang != "ru" else "Таблица пуста."
        lines = "\n".join(" | ".join(str(c) for c in row[:5]) for row in data[:15])
        return f"<b>Sheet data (first 15 rows):</b>\n<pre>{lines}</pre>" if lang != "ru" else f"<b>Таблица (первые 15 строк):</b>\n<pre>{lines}</pre>"
    except Exception as e:
        logger.error("Sheets error: %s", e)
        if "not found" in str(e).lower():
            if lang == "ru":
                return "Таблица не найдена. Проверь ссылку и открой доступ для сервис-аккаунта."
            return "Sheet not found. Check the URL and share it with the service account."
        if "permission" in str(e).lower():
            if lang == "ru":
                return "Нет доступа к таблице. Открой доступ для:\n" + get_service_email()
            return "No access to sheet. Share it with:\n" + get_service_email()
        return f"Sheet error: {e}" if lang != "ru" else f"Ошибка таблицы: {e}"


def _handle_create_event(args: dict, lang: str) -> str:
    summary = args.get("summary", "Event")
    date = args.get("date", "")
    time = args.get("time", "10:00")
    try:
        link = create_event(summary, date, time)
        if lang == "ru":
            return f"Событие создано: <a href='{link}'><b>{summary}</b></a>\nДата: {date}\nВремя: {time}"
        return f"Event created: <a href='{link}'><b>{summary}</b></a>\nDate: {date}\nTime: {time}"
    except Exception as e:
        logger.error("Calendar error: %s", e)
        if lang == "ru":
            return "Не удалось создать событие. Проверь, что сервис-аккаунт имеет доступ к календарю."
        return "Failed to create event. Make sure the service account has calendar access."


def _handle_generate_report(args: dict, lang: str) -> str:
    fmt = args.get("format", "pdf")
    topic = args.get("topic", "")
    if lang == "ru":
        return f"Генерирую отчёт в <b>{fmt.upper()}</b> по теме: {topic}\n(Полная реализация — в День 8)."
    return (
        f"Generating <b>{fmt.upper()}</b> report on: {topic}\n"
        f"Your report will be ready shortly (full implementation Day 8)."
    )
