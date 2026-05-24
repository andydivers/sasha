import re
import logging
import json
from datetime import datetime, timedelta

from app.i18n import t
from app.sheets_client import read_sheet, write_sheet, append_row, get_service_email, is_ready as sheets_ready
from app.calendar_client import create_event, get_calendar_link, is_ready as calendar_ready
from app.reports import generate_excel, generate_html

logger = logging.getLogger(__name__)


async def handle_tool_call(tool_call, lang: str = "en", sheet_url: str | None = None, tz: str = "UTC") -> str:
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    if name == "manage_sheets":
        return _handle_manage_sheets(args, lang, sheet_url)

    if name == "create_event":
        return _handle_create_event(args, lang, tz)

    if name == "generate_report":
        return _handle_generate_report(args, lang, sheet_url)

    handlers = {
        "analyze_screenshot": _handle_analyze_screenshot,
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


_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def _parse_date(raw: str) -> str:
    raw = raw.strip().lower()
    today = datetime.now()
    if raw == "today":
        return today.strftime("%Y-%m-%d")
    if raw == "tomorrow":
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if raw in _WEEKDAYS:
        target = _WEEKDAYS[raw]
        days_ahead = (target - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    if raw.startswith("next "):
        rest = raw[5:]
        if rest in _WEEKDAYS:
            target = _WEEKDAYS[rest]
            days_ahead = (target - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead + 7)).strftime("%Y-%m-%d")
    try:
        datetime.fromisoformat(raw)
        return raw
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%d.%m.%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return today.strftime("%Y-%m-%d")


def _parse_time(raw: str) -> str:
    raw = raw.strip().lower()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", raw)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        mer = m.group(3)
        if mer:
            mer = mer.replace(".", "")
            if mer == "pm" and hour < 12:
                hour += 12
            elif mer == "am" and hour == 12:
                hour = 0
        return f"{hour:02d}:{minute:02d}"
    try:
        datetime.strptime(raw, "%H:%M")
        return raw
    except ValueError:
        return "10:00"


def _handle_create_event(args: dict, lang: str, tz: str = "UTC") -> str:
    summary = args.get("summary", "Event")
    date_raw = args.get("date", "")
    time_raw = args.get("time", "10:00")
    date = _parse_date(date_raw) if date_raw else datetime.now().strftime("%Y-%m-%d")
    time = _parse_time(time_raw)
    try:
        link = create_event(summary, date, time, tz=tz)
        cal_link = get_calendar_link()
        if lang == "ru":
            return (
                f"Событие создано: <a href='{link}'><b>{summary}</b></a>\n"
                f"Дата: {date}\nВремя: {time}\n\n"
                f"📅 <a href='{cal_link}'>Подписаться на календарь Sasha</a>"
            )
        return (
            f"Event created: <a href='{link}'><b>{summary}</b></a>\n"
            f"Date: {date}\nTime: {time}\n\n"
            f"📅 <a href='{cal_link}'>Subscribe to Sasha Calendar</a>"
        )
    except Exception as e:
        logger.error("Calendar error: %s", e)
        if lang == "ru":
            return "Не удалось создать событие. Проверь, что сервис-аккаунт имеет доступ к календарю."
        return "Failed to create event. Make sure the service account has calendar access."


def _handle_generate_report(args: dict, lang: str, sheet_url: str | None = None) -> str:
    fmt = args.get("format", "").lower()
    topic = args.get("topic", "report")

    if fmt not in ("excel", "html"):
        if lang == "ru":
            return "Выбери формат: <b>Excel</b> или <b>HTML</b>"
        return "Choose format: <b>Excel</b> or <b>HTML</b>"

    if not sheet_url:
        if lang == "ru":
            return "Сначала подключи таблицу через /sheet https://..."
        return "First connect your sheet via /sheet https://..."

    if not sheets_ready():
        if lang == "ru":
            return "Google Sheets не настроен."
        return "Google Sheets is not configured."

    try:
        data = read_sheet(sheet_url)
        if not data:
            if lang == "ru":
                return "Таблица пуста. Нечего формировать."
            return "Sheet is empty. Nothing to report."

        if fmt == "excel":
            path = generate_excel(data, topic)
            return f"__REPORT__:{fmt}:{path}"
        else:
            path = generate_html(data, topic)
            return f"__REPORT__:{fmt}:{path}"
    except Exception as e:
        logger.error("Report error: %s", e)
        if lang == "ru":
            return "Ошибка при формировании отчёта."
        return "Error generating report."
