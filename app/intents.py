import re
import logging
import json
from datetime import datetime, timedelta, timezone

from app.i18n import t
from app.sheets_client import read_sheet, write_sheet, append_row, get_service_email, is_ready as sheets_ready
from app.calendar_client import create_event, get_calendar_link, is_ready as calendar_ready
from app.reports import generate_excel, generate_html
from app.database import add_expense, get_user_items, add_movement, add_todo, add_reminder, has_seen_sheet_offer, mark_seen_sheet_offer, set_user_tz, log_event
from app.timezone_utils import find_timezone, format_dual_time

logger = logging.getLogger(__name__)


async def handle_tool_call(tool_call, lang: str = "en", sheet_url: str | None = None, tz: str = "UTC", user_id: int = 0) -> str:
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    if name == "manage_sheets":
        return await _handle_manage_sheets(args, lang, sheet_url, user_id=user_id)

    if name == "create_event":
        return await _handle_create_event(args, lang, tz, user_id)

    if name == "generate_report":
        return _handle_generate_report(args, lang, sheet_url)

    if name == "track_movement":
        return await _handle_track_movement(args, lang, user_id, tz)

    if name == "add_expense":
        return await _handle_add_expense(args, lang, user_id)

    if name == "add_todo":
        return await _handle_add_todo(args, lang, user_id)

    if name == "set_reminder":
        return await _handle_add_reminder(args, lang, user_id, tz)

    if name == "set_timezone_by_location":
        return await _handle_set_timezone_by_location(args, lang, user_id)

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


async def _handle_manage_sheets(args: dict, lang: str, sheet_url: str | None = None, user_id: int = 0) -> str:
    action = args.get("action", "read")
    description = args.get("description", "")

    if not sheet_url:
        if action == "write":
            amount = ""
            nums = re.findall(r"[\d,.]+", description)
            if nums:
                amount = nums[0]
            category = "expense" if amount else "note"
            try:
                await add_expense(user_id, description, amount, category)
            except Exception:
                pass
            offer = ""
            if user_id:
                try:
                    seen = await has_seen_sheet_offer(user_id)
                    if not seen:
                        await mark_seen_sheet_offer(user_id)
                        if lang == "ru":
                            offer = "\n\n💡 Хочешь, чтобы записи отображались в Google Таблице? Просто отправь ссылку."
                        else:
                            offer = "\n\n💡 Want to see items in a Google Sheet? Just send the sheet link."
                except Exception:
                    pass
            if lang == "ru":
                emoji = "💰" if category == "expense" else "📝"
                return f"{emoji} Записал: {description}{offer}"
            emoji = "💰" if category == "expense" else "📝"
            return f"{emoji} Saved: {description}{offer}"
        # read from local when no sheet
        try:
            items = await get_user_items(user_id, limit=15)
        except Exception:
            items = []
        if not items:
            if lang == "ru":
                return "Пока нет записей. Скажи что-нибудь — я сохраню!"
            return "No items yet. Tell me something and I'll save it!"
        lines = []
        for it in items:
            desc = it.get("description", "")
            amt = it.get("amount", "")
            cat = it.get("category", "")
            cat_label = {"expense": "💰", "note": "📝"}.get(cat, "📌")
            if amt:
                lines.append(f"{cat_label} {desc} — {amt}")
            else:
                lines.append(f"{cat_label} {desc}")
        joined = "\n".join(lines)
        label = "Recent items" if lang != "ru" else "Последние записи"
        return f"<b>{label}:</b>\n<pre>{joined}</pre>"

    if not sheets_ready():
        if lang == "ru":
            return "Google Sheets не настроен на сервере."
        return "Google Sheets is not configured."

    try:
        if action == "write":
            nums = re.findall(r"[\d,.]+", description)
            amount = nums[0] if nums else ""
            category = "expense" if amount else "note"
            try:
                await add_expense(user_id, description, amount, category)
            except Exception as e:
                logger.warning("Failed to save expense locally: %s", e)
            row = [description, amount] if amount else [description]
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


async def _handle_create_event(args: dict, lang: str, tz: str = "UTC", user_id: int = 0) -> str:
    summary = args.get("summary", "Event")
    date_raw = args.get("date", "")
    time_raw = args.get("time", "10:00")
    date = _parse_date(date_raw) if date_raw else datetime.now().strftime("%Y-%m-%d")
    time = _parse_time(time_raw)
    try:
        link = create_event(summary, date, time, tz=tz)
        cal_link = get_calendar_link()

        await log_event(user_id, "calendar_event", {
            "summary": summary,
            "date": date,
            "time": time,
            "tz": tz,
            "link": link,
        })

        time_str = f"{time} {tz}"
        msk_time = ""
        if tz and tz != "UTC":
            try:
                import zoneinfo
                from datetime import timezone, timedelta
                utc_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                user_tz_obj = zoneinfo.ZoneInfo(tz)
                user_dt = utc_dt.replace(tzinfo=user_tz_obj)
                msk_dt = user_dt.astimezone(timezone(timedelta(hours=3)))
                msk_time = f" ({msk_dt.strftime('%H:%M')} MSK)"
            except Exception:
                pass
        if lang == "ru":
            return (
                f"Событие создано: <a href='{link}'><b>{summary}</b></a>\n"
                f"Дата: {date}\nВремя: {time_str}{msk_time}\n\n"
                f"📅 <a href='{cal_link}'>Подписаться на календарь Sasha</a>"
            )
        return (
            f"Event created: <a href='{link}'><b>{summary}</b></a>\n"
            f"Date: {date}\nTime: {time_str}{msk_time}\n\n"
            f"📅 <a href='{cal_link}'>Subscribe to Sasha Calendar</a>"
        )
    except Exception as e:
        logger.error("Calendar error: %s", e)
        if lang == "ru":
            return "Не удалось создать событие. Проверь, что сервис-аккаунт имеет доступ к календарю."
        return "Failed to create event. Make sure the service account has calendar access."


def _parse_delay(raw: str) -> int:
    raw = raw.lower().strip()
    m = re.match(r"(\d+)\s*(m|min|h|hr|hour|d|day)s?", raw)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit in ("h", "hr", "hour"):
            return n * 3600
        if unit in ("d", "day"):
            return n * 86400
        return n * 60
    raise ValueError(f"Can't parse: {raw}")


def _parse_when(when: str, tz: str) -> str | None:
    """Parse 'when' string to UTC ISO time. Returns None if can't parse."""
    when = when.lower().strip()
    try:
        delay = _parse_delay(when)
        return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
    except ValueError:
        pass
    try:
        hour_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", when)
        if hour_match:
            hour = int(hour_match.group(1))
            minute = int(hour_match.group(2)) if hour_match.group(2) else 0
            ampm = hour_match.group(3)
            if ampm:
                if ampm == "pm" and hour < 12:
                    hour += 12
                if ampm == "am" and hour == 12:
                    hour = 0
            import zoneinfo
            try:
                tz_obj = zoneinfo.ZoneInfo(tz)
            except Exception:
                tz_obj = timezone.utc
            now_local = datetime.now(tz_obj)
            target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_local <= now_local:
                target_local += timedelta(days=1)
            target_utc = target_local.astimezone(timezone.utc)
            return target_utc.isoformat()
    except Exception:
        pass
    return None


async def _handle_add_reminder(args: dict, lang: str, user_id: int = 0, tz: str = "UTC") -> str:
    message_text = args.get("message", "")
    when = args.get("when", "")
    if not message_text or not when:
        if lang == "ru":
            return "Что напомнить и когда? Например: напомни купить молоко через 2 часа"
        return "What to remind and when? Say: remind me to buy milk in 2 hours"
    when_utc = _parse_when(when, tz)
    if when_utc:
        await add_reminder(user_id, message_text, when_utc)
        if lang == "ru":
            return f"⏰ Напомню: {message_text}"
        return f"⏰ I'll remind you: {message_text}"
    if lang == "ru":
        return f"⏰ Напомню: {message_text} ({when})"
    return f"⏰ I'll remind you: {message_text} ({when})"


async def _handle_add_expense(args: dict, lang: str, user_id: int = 0) -> str:
    description = args.get("description", "")
    amount = args.get("amount", "")
    category = "expense" if amount else "note"
    try:
        await add_expense(user_id, description, amount, category)
    except Exception as e:
        logger.error("Failed to add expense: %s", e)
    emoji = "💰" if amount else "📝"
    if lang == "ru":
        return f"{emoji} {description}{' — ' + amount if amount else ''}"
    return f"{emoji} {description}{' — ' + amount if amount else ''}"


async def _handle_add_todo(args: dict, lang: str, user_id: int = 0) -> str:
    title = args.get("title", "")
    if not title:
        if lang == "ru":
            return "Что нужно сделать? Скажи, например: добавить задачу купить молоко"
        return "What needs to be done? Say: add task buy milk"
    try:
        await add_todo(user_id, title)
    except Exception as e:
        logger.error("Failed to add todo: %s", e)
    if lang == "ru":
        return f"☐ {title}"
    return f"☐ {title}"


async def _handle_track_movement(args: dict, lang: str, user_id: int = 0, tz: str = "UTC") -> str:
    location = args.get("location", "somewhere")
    description = args.get("description", "")
    try:
        await add_movement(user_id, location, description)
    except Exception as e:
        logger.error("Failed to add movement: %s", e)
    time_str = format_dual_time(user_tz=tz)
    if lang == "ru":
        return f"📍 {location} ({time_str}){' — ' + description if description else ''}"
    return f"📍 {location} ({time_str}){' — ' + description if description else ''}"


async def _handle_set_timezone_by_location(args: dict, lang: str, user_id: int = 0) -> str:
    location = args.get("location", "")
    if not location:
        if lang == "ru":
            return "Не понял, где ты находишься. Назови город или страну."
        return "I didn't catch where you are. Tell me a city or country."
    tz_name = find_timezone(location)
    if not tz_name:
        if lang == "ru":
            return f"Не знаю часовой пояс для «{location}». Установи вручную: /tz Europe/Moscow"
        return f"Don't know timezone for '{location}'. Set manually: /tz Europe/Moscow"
    try:
        await set_user_tz(user_id, tz_name)
    except Exception:
        pass
    if lang == "ru":
        return f"🕐 Часовой пояс установлен: {tz_name}. Теперь время показываю как MSK + местное."
    return f"🕐 Timezone set to {tz_name}. Now showing times as MSK + local."


def _handle_generate_report(args: dict, lang: str, sheet_url: str | None = None) -> str:
    fmt = args.get("format", "").lower()
    topic = args.get("topic", "report")

    if fmt not in ("excel", "html"):
        if lang == "ru":
            return "Выбери формат: <b>Excel</b> или <b>HTML</b>"
        return "Choose format: <b>Excel</b> or <b>HTML</b>"

    if not sheet_url:
        if lang == "ru":
            return "Нет данных для отчёта. Подключи Google Таблицу через /sheet https://..."
        return "No data for report. Connect a Google Sheet via /sheet https://..."

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
