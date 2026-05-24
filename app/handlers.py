import os
import re
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.config import Config
from app.database import get_user_lang, set_user_lang, get_user_tz, set_user_tz, save_chat, log_event, add_reminder
from app.groq_client import create_groq_client, detect_intent
from app.intents import handle_tool_call
from app.gemini_client import init_gemini, analyze_image
from app.sheets_client import init_sheets, read_sheet, write_sheet, append_row, get_service_email, is_ready as sheets_ready
from app.calendar_client import list_events, delete_event, get_calendar_link, is_ready as calendar_ready
from app.i18n import t, TRANSLATIONS

logger = logging.getLogger(__name__)
router = Router()

config = Config()
groq = create_groq_client(config.groq_api_key) if config.groq_api_key else None

if config.gemini_api_key:
    init_gemini(config.gemini_api_key)

LANG_LIST = ["en", "ru", "es", "fr", "zh", "ar", "pt", "de", "hi", "ja"]

LANG_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(
        text=f"{TRANSLATIONS[code]['flag']} {TRANSLATIONS[code]['name']}",
        callback_data=f"lang_{code}"
    )] for code in LANG_LIST
])

_lang_cache: dict[int, str] = {}
_tz_cache: dict[int, str] = {}
_sheet_cache: dict[int, str] = {}


async def get_lang(user_id: int) -> str:
    if user_id not in _lang_cache:
        _lang_cache[user_id] = await get_user_lang(user_id)
    return _lang_cache.get(user_id, "en")


async def get_tz(user_id: int) -> str:
    if user_id not in _tz_cache:
        tz = await get_user_tz(user_id)
        _tz_cache[user_id] = tz if tz else "UTC"
    return _tz_cache.get(user_id, "UTC")


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "lang_prompt"), reply_markup=LANG_KEYBOARD)


@router.callback_query(F.data.startswith("lang_"))
async def on_lang_choice(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    _lang_cache[callback.from_user.id] = lang
    await set_user_lang(callback.from_user.id, lang)
    await callback.message.edit_text(t(lang, "lang_changed"))
    await callback.message.answer(t(lang, "welcome"))


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "help"))


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "ping"))


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    await message.answer(t("en", "lang_prompt"), reply_markup=LANG_KEYBOARD)


@router.message(Command("webhook"))
async def cmd_webhook(message: types.Message, bot: Bot):
    info = await bot.get_webhook_info()
    lang = await get_lang(message.from_user.id)
    await message.answer(t(lang, "webhook",
        url=info.url or t(lang, "webhook_not_set"),
        errors=info.last_error_message or t(lang, "webhook_no_errors"),
    ))


@router.message(Command("sheet"))
async def cmd_sheet(message: types.Message):
    lang = await get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        if lang == "ru":
            await message.answer(
                "Отправь ссылку на Google Таблицу:\n"
                "<code>/sheet https://docs.google.com/spreadsheets/d/...</code>\n\n"
                "Не забудь <b>открыть доступ</b> таблице для:\n"
                f"<code>{get_service_email()}</code>"
            )
        else:
            await message.answer(
                "Send your Google Sheet URL:\n"
                "<code>/sheet https://docs.google.com/spreadsheets/d/...</code>\n\n"
                "Make sure to <b>share</b> the sheet with:\n"
                f"<code>{get_service_email()}</code>"
            )
        return

    url = parts[1].strip()
    _sheet_cache[message.from_user.id] = url
    if lang == "ru":
        await message.answer("Google Таблица подключена! Теперь я могу читать и записывать данные.")
    else:
        await message.answer("Google Sheet connected! I can now read and write data.")


@router.message(Command("tz"))
async def cmd_tz(message: types.Message):
    lang = await get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        if lang == "ru":
            await message.answer("Укажи часовой пояс: /tz UTC+3\nНапример: /tz Europe/Moscow, /tz UTC+5, /tz America/New_York")
        else:
            await message.answer("Set your timezone with: /tz UTC+3\nOr use IANA names: /tz Europe/Moscow, /tz America/New_York")
        return

    raw = parts[1].strip()
    m = re.match(r"^UTC([+-]?)(\d{1,2})(?::(\d{2}))?$", raw, re.I)
    if m:
        h = int(m.group(2))
        if h == 0:
            tz = "UTC"
        elif m.group(1) in ("", "+"):
            tz = f"Etc/GMT-{h}"
        else:
            tz = f"Etc/GMT+{h}"
    else:
        tz = raw
    _tz_cache[message.from_user.id] = tz
    await set_user_tz(message.from_user.id, tz)

    if lang == "ru":
        await message.answer(f"Часовой пояс установлен: {tz}")
    else:
        await message.answer(f"Timezone set: {tz}")


@router.message(Command("events"))
async def cmd_events(message: types.Message):
    lang = await get_lang(message.from_user.id)
    if not calendar_ready():
        await message.answer("Calendar not configured." if lang != "ru" else "Календарь не настроен.")
        return
    try:
        events = list_events(10)
        if not events:
            await message.answer("No events found." if lang != "ru" else "Событий нет.")
            return
        out = []
        for i, ev in enumerate(events, 1):
            s = ev["start"].get("dateTime", ev["start"].get("date", "?"))
            if "T" in s:
                dt = s[:16].replace("T", " ")
            else:
                dt = s
            summary = ev.get("summary", "—")
            out.append(f"{i}. <b>{summary}</b> — {dt}")
        if lang == "ru":
            out.insert(0, "📅 <b>Мои события</b>")
        else:
            out.insert(0, "📅 <b>My events</b>")
        await message.answer("\n".join(out))
    except Exception as e:
        logger.error("Events error: %s", e)
        await message.answer("Error loading events." if lang != "ru" else "Ошибка загрузки событий.")


@router.message(Command("delete"))
async def cmd_delete(message: types.Message):
    lang = await get_lang(message.from_user.id)
    if not calendar_ready():
        await message.answer("Calendar not configured." if lang != "ru" else "Календарь не настроен.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        if lang == "ru":
            await message.answer("Используй: /delete N (где N — номер из /events)")
        else:
            await message.answer("Use: /delete N (N is the number from /events)")
        return
    idx = int(parts[1].strip()) - 1
    try:
        events = list_events(10)
        if idx < 0 or idx >= len(events):
            if lang == "ru":
                await message.answer(f"Нет события под номером {idx + 1}. Сначала /events.")
            else:
                await message.answer(f"No event #{idx + 1}. Run /events first.")
            return
        ev = events[idx]
        delete_event(ev["id"])
        if lang == "ru":
            await message.answer(f"Удалено: <b>{ev.get('summary', '—')}</b>")
        else:
            await message.answer(f"Deleted: <b>{ev.get('summary', '—')}</b>")
    except Exception as e:
        logger.error("Delete error: %s", e)
        await message.answer("Error deleting event." if lang != "ru" else "Ошибка удаления.")


@router.message(Command("remind"))
async def cmd_remind(message: types.Message):
    lang = await get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        if lang == "ru":
            await message.answer("Используй: /remind 1h check my email\n/remind tomorrow 9am call John\n/remind 30min take a break")
        else:
            await message.answer("Use: /remind 1h check my email\n/remind tomorrow 9am call John\n/remind 30min take a break")
        return

    when_raw = parts[1].strip()
    text = parts[2].strip()

    try:
        delay = _parse_delay(when_raw)
        when_utc = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
    except Exception:
        if lang == "ru":
            await message.answer("Не понял время. Используй: 1h, 30min, tomorrow 9am")
        else:
            await message.answer("Can't parse time. Use: 1h, 30min, tomorrow 9am")
        return

    await add_reminder(message.from_user.id, text, when_utc)
    if lang == "ru":
        await message.answer(f"Напомню через <b>{when_raw}</b>: {text}")
    else:
        await message.answer(f"Reminder set in <b>{when_raw}</b>: {text}")


def _parse_delay(raw: str) -> int:
    raw = raw.lower()
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


@router.message(F.photo)
async def handle_photo(message: types.Message, bot: Bot):
    lang = await get_lang(message.from_user.id)
    caption = message.caption or ""
    prompt = caption if caption else ("What do you see in this image?" if lang != "ru" else "Что ты видишь на этом изображении?")

    await message.answer(t(lang, "thinking"))

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        image_bytes = await bot.download_file(file.file_path)
        result = analyze_image(image_bytes.read(), "image/jpeg", prompt)
        await message.answer(result)
        await log_event(message.from_user.id, "image_analyzed")
    except Exception as e:
        logger.error("Gemini error: %s", e)
        await message.answer(t(lang, "error"))


@router.message()
async def handle_message(message: types.Message):
    if not message.text:
        lang = await get_lang(message.from_user.id)
        await message.answer(t(lang, "not_ready"))
        return

    lang = await get_lang(message.from_user.id)

    text = message.text.strip()

    m = re.match(r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", text)
    if m:
        _sheet_cache[message.from_user.id] = m.group(0)
        if lang == "ru":
            await message.answer("Google Таблица подключена! Теперь я могу читать и записывать данные.")
        else:
            await message.answer("Google Sheet connected! I can now read and write data.")
        return

    if not groq:
        await message.answer(t(lang, "not_ready"))
        return

    tz = await get_tz(message.from_user.id)

    await message.answer(t(lang, "thinking"))

    try:
        result, latency = detect_intent(groq, text, lang=lang)

        if isinstance(result, str):
            response_text = result
            if response_text.startswith("__REPORT__:"):
                parts = response_text.split(":", 2)
                fmt = parts[1]
                path = parts[2]
                fname = f"report.{fmt}"
                with open(path, "rb") as f:
                    await message.answer_document(types.BufferedInputFile(f.read(), filename=fname))
                os.unlink(path)
            else:
                await message.answer(response_text)
        else:
            sheet_url = _sheet_cache.get(message.from_user.id)
            response_text = await handle_tool_call(result, lang=lang, sheet_url=sheet_url, tz=tz)
            if response_text.startswith("__REPORT__:"):
                parts = response_text.split(":", 2)
                fmt = parts[1]
                path = parts[2]
                fname = f"report.{fmt}"
                with open(path, "rb") as f:
                    await message.answer_document(types.BufferedInputFile(f.read(), filename=fname))
                os.unlink(path)
            else:
                await message.answer(response_text)

        await save_chat(message.from_user.id, text, response_text, int(latency * 1000))
        logger.info("Handled message in %.2fs", latency)
    except Exception as e:
        logger.error("Groq error: %s", e)
        await message.answer(t(lang, "error"))
