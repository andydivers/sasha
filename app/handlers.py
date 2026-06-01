import os
import re
import logging
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
from urllib.parse import quote

from aiogram import Bot, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.config import Config
from app.database import get_user_lang, set_user_lang, get_user_tz, set_user_tz, get_user_sheet, set_user_sheet, save_chat, log_event, add_reminder, add_todo, get_todos, mark_todo_done, create_pending_payment, get_unsynced_items, mark_items_synced, get_digest_config, set_digest_config, add_recurring_payment, get_recurring_payments, delete_recurring_payment
from app.groq_client import create_groq_client, detect_intent, chat_turn, transcribe_audio
from app.intents import handle_tool_call
from app.gemini_client import init_gemini, analyze_image
from app.sheets_client import init_sheets, read_sheet, write_sheet, append_row, get_service_email, is_ready as sheets_ready
from app.calendar_client import list_events, delete_event, get_calendar_link, is_ready as calendar_ready
from app.crypto_client import check_usdc_evm, NETWORKS
from app.i18n import t, TRANSLATIONS

logger = logging.getLogger(__name__)
router = Router()

config = Config()
groq = create_groq_client(config.groq_api_key) if config.groq_api_key else None

if config.gemini_api_key:
    init_gemini(config.gemini_api_key)

STAR_PRICES = {
    "weekly": {"label_en": "Weekly subscription", "label_ru": "Подписка на неделю", "stars": 400},
    "monthly": {"label_en": "Monthly subscription", "label_ru": "Подписка на месяц", "stars": 1000},
}

CRYPTO_PRICES = {
    "weekly": {"label_en": "Weekly subscription", "label_ru": "Подписка на неделю", "usdc": 5.0},
    "monthly": {"label_en": "Monthly subscription", "label_ru": "Подписка на месяц", "usdc": 15.0},
}

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


dashboard_url = config.webhook_url.replace("/webhook", "/dashboard") if config.webhook_url else "https://sasha-dbgw.onrender.com/dashboard"

START_MENU_EN = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎤 How it works", callback_data="menu_howto")],
    [InlineKeyboardButton(text="📋 Commands", callback_data="menu_help")],
    [InlineKeyboardButton(text="📊 Dashboard", web_app=types.WebAppInfo(url=dashboard_url))],
    [InlineKeyboardButton(text="💳 Buy subscription", callback_data="buy_show")],
    [InlineKeyboardButton(text="🌐 Language", callback_data="menu_lang")],
])
START_MENU_RU = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎤 Как работать", callback_data="menu_howto")],
    [InlineKeyboardButton(text="📋 Команды", callback_data="menu_help")],
    [InlineKeyboardButton(text="📊 Дашборд", web_app=types.WebAppInfo(url=dashboard_url))],
    [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_show")],
    [InlineKeyboardButton(text="🌐 Язык", callback_data="menu_lang")],
])


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    lang = await get_lang(message.from_user.id)
    menu = START_MENU_RU if lang == "ru" else START_MENU_EN
    msg = t(lang, "welcome")
    await message.answer(msg, parse_mode="HTML", reply_markup=menu)
    await message.answer(t(lang, "onboarding_voice"), parse_mode="HTML")


@router.callback_query(F.data.in_({"menu_howto", "menu_help", "menu_lang", "menu_back", "buy_show"}))
async def on_menu_callback(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    data = callback.data
    menu = START_MENU_RU if lang == "ru" else START_MENU_EN
    if data == "menu_howto":
        back = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Menu" if lang != "ru" else "🏠 Меню", callback_data="menu_back")]
        ])
        await callback.message.edit_text(t(lang, "onboarding_voice"), parse_mode="HTML", reply_markup=back)
    elif data == "menu_help":
        back = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Menu" if lang != "ru" else "🏠 Меню", callback_data="menu_back")]
        ])
        await callback.message.edit_text(t(lang, "help"), parse_mode="HTML", reply_markup=back)
    elif data == "menu_lang":
        await callback.message.edit_text(t(lang, "lang_prompt"), reply_markup=LANG_KEYBOARD)
    elif data == "menu_back":
        await callback.message.edit_text(t(lang, "welcome"), reply_markup=menu, parse_mode="HTML")
    elif data == "buy_show":
        btns = [
            [InlineKeyboardButton(text="📊 Weekly $4.99 / 400⭐" if lang != "ru" else "📊 Неделя $4.99 / 400⭐", callback_data="buy_weekly")],
            [InlineKeyboardButton(text="📊 Monthly $14.99 / 1000⭐" if lang != "ru" else "📊 Месяц $14.99 / 1000⭐", callback_data="buy_monthly")],
            [InlineKeyboardButton(text="💎 USDC Crypto" if lang != "ru" else "💎 USDC Крипта", callback_data="buy_crypto")],
            [InlineKeyboardButton(text="🏠 Menu" if lang != "ru" else "🏠 Меню", callback_data="menu_back")],
        ]
        await callback.message.edit_text(
            "💳 <b>Subscription</b>" if lang != "ru" else "💳 <b>Подписка</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=btns), parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("lang_"))
async def on_lang_choice(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    _lang_cache[callback.from_user.id] = lang
    await set_user_lang(callback.from_user.id, lang)
    await callback.message.edit_text(t(lang, "lang_changed"))
    menu = START_MENU_RU if lang == "ru" else START_MENU_EN
    await callback.message.answer(t(lang, "welcome"), reply_markup=menu, parse_mode="HTML")
    await callback.message.answer(t(lang, "onboarding_voice"), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "help"), parse_mode="HTML")


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "ping"))


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    await message.answer(t("en", "lang_prompt"), reply_markup=LANG_KEYBOARD)


@router.message(Command("webhook"))
async def cmd_webhook(message: types.Message, bot: Bot):
    lang = await get_lang(message.from_user.id)
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(url=config.webhook_url)
    info = await bot.get_webhook_info()
    msg = (
        f"✅ Webhook reset\nURL: {info.url}\nErrors: {info.last_error_message or 'None'}"
        if lang != "ru" else
        f"✅ Вебхук сброшен\nURL: {info.url}\nОшибки: {info.last_error_message or 'Нет'}"
    )
    await message.answer(msg)


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
    await set_user_sheet(message.from_user.id, url)
    if lang == "ru":
        await message.answer("Google Таблица подключена! Теперь я могу читать и записывать данные.")
    else:
        await message.answer("Google Sheet connected! I can now read and write data.")


@router.message(Command("sync"))
async def cmd_sync(message: types.Message):
    lang = await get_lang(message.from_user.id)
    user_id = message.from_user.id

    sheet_url = _sheet_cache.get(user_id) or await get_user_sheet(user_id)
    if not sheet_url:
        if lang == "ru":
            await message.answer("Сначала подключи Google Таблицу через /sheet https://...")
        else:
            await message.answer("First connect a Google Sheet via /sheet https://...")
        return

    if not sheets_ready():
        if lang == "ru":
            await message.answer("Google Sheets не настроен на сервере.")
        else:
            await message.answer("Google Sheets is not configured.")
        return

    items = await get_unsynced_items(user_id)
    if not items:
        if lang == "ru":
            await message.answer("Нет несинхронизированных записей.")
        else:
            await message.answer("No unsynced items.")
        return

    try:
        # write header if table is empty
        header = [["Category", "Description", "Amount", "Date"]]
        existing = read_sheet(sheet_url, "A1:D1")
        if not existing or existing == [[""]]:
            write_sheet(sheet_url, header, "A1:D1")

        synced_ids = []
        for item in items:
            cat = item.get("category", "")
            desc = item.get("description", "")
            amt = item.get("amount", "")
            dt = item.get("created_at", "")
            append_row(sheet_url, [cat, desc, amt, dt])
            synced_ids.append(item["id"])

        if synced_ids:
            await mark_items_synced(synced_ids)

        if lang == "ru":
            await message.answer(f"✅ Синхронизировано {len(synced_ids)} записей в Google Таблицу.")
        else:
            await message.answer(f"✅ Synced {len(synced_ids)} items to Google Sheet.")
    except Exception as e:
        logger.error("Sync error: %s", e)
        if lang == "ru":
            await message.answer(f"Ошибка синхронизации: {e}")
        else:
            await message.answer(f"Sync error: {e}")


@router.message(Command("digest"))
async def cmd_digest(message: types.Message):
    lang = await get_lang(message.from_user.id)
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        cfg = await get_digest_config(user_id)
        status = "✅ On" if cfg.get("digest_enabled") else "❌ Off"
        t = cfg.get("digest_time", "09:00")
        if lang == "ru":
            await message.answer(
                f"📋 <b>Ежедневный дайджест</b>\n"
                f"Статус: {status}\n"
                f"Время: {t}\n\n"
                f"<code>/digest on 09:00</code> — включить\n"
                f"<code>/digest off</code> — выключить\n"
                f"<code>/digest now</code> — показать сейчас"
            )
        else:
            await message.answer(
                f"📋 <b>Daily Digest</b>\n"
                f"Status: {status}\n"
                f"Time: {t}\n\n"
                f"<code>/digest on 09:00</code> — enable\n"
                f"<code>/digest off</code> — disable\n"
                f"<code>/digest now</code> — show now"
            )
        return

    cmd = parts[1].lower()
    if cmd == "off":
        await set_digest_config(user_id, False)
        if lang == "ru":
            await message.answer("📋 Дайджест выключен.")
        else:
            await message.answer("📋 Digest disabled.")
        return

    if cmd == "now":
        from app.digest import generate_digest
        digest_text = await generate_digest(user_id, lang)
        msg = await message.answer(digest_text, parse_mode="HTML")
        try:
            await msg.pin()
        except Exception:
            pass
        return

    if cmd == "on":
        time = parts[2] if len(parts) > 2 else "09:00"
        if not re.match(r"^\d{2}:\d{2}$", time):
            if lang == "ru":
                await message.answer("Формат времени: HH:MM (например, 09:00)")
            else:
                await message.answer("Time format: HH:MM (e.g., 09:00)")
            return
        await set_digest_config(user_id, True, time)
        if lang == "ru":
            await message.answer(f"📋 Дайджест включён в {time} ежедневно.")
        else:
            await message.answer(f"📋 Digest enabled at {time} daily.")
        return

    if lang == "ru":
        await message.answer("Команды: /digest on HH:MM, /digest off, /digest now")
    else:
        await message.answer("Usage: /digest on HH:MM, /digest off, /digest now")


@router.message(Command("anomalies"))
async def cmd_anomalies(message: types.Message):
    lang = await get_lang(message.from_user.id)
    from app.anomaly import detect_anomalies
    alerts = await detect_anomalies(message.from_user.id, lang)
    if not alerts:
        if lang == "ru":
            await message.answer("✅ Аномалий не обнаружено.")
        else:
            await message.answer("✅ No anomalies detected.")
        return
    header = "🔍 <b>Anomalies:</b>" if lang != "ru" else "🔍 <b>Аномалии:</b>"
    await message.answer(header + "\n" + "\n".join(alerts), parse_mode="HTML")


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


@router.message(Command("todo"))
async def cmd_todo(message: types.Message):
    lang = await get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) >= 2:
        title = parts[1].strip()
        await add_todo(message.from_user.id, title)
        if lang == "ru":
            await message.answer(f"✅ Задача добавлена: {title}")
        else:
            await message.answer(f"✅ Task added: {title}")
        return
    todos = await get_todos(message.from_user.id)
    if not todos:
        if lang == "ru":
            await message.answer("📋 Список задач пуст.\n\nДобавь задачу: /todo купить молоко")
        else:
            await message.answer("📋 Todo list is empty.\n\nAdd a task: /todo buy milk")
        return
    lines = []
    for i, t in enumerate(todos, 1):
        title = t.get("title", "—")
        lines.append(f"{i}. {title}")
    text = "📋 <b>Tasks:</b>\n" + "\n".join(lines)
    if lang == "ru":
        text = "📋 <b>Задачи:</b>\n" + "\n".join(lines)
        text += "\n\nОтметить выполненной: /done N"
    else:
        text += "\n\nMark as done: /done N"
    await message.answer(text)


@router.message(Command("done"))
async def cmd_done(message: types.Message):
    lang = await get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        if lang == "ru":
            await message.answer("Используй: /done N (где N — номер из /todo)")
        else:
            await message.answer("Use: /done N (N is the number from /todo)")
        return
    idx = int(parts[1].strip())
    todos = await get_todos(message.from_user.id)
    if idx < 1 or idx > len(todos):
        if lang == "ru":
            await message.answer(f"Нет задачи под номером {idx}. Сначала /todo.")
        else:
            await message.answer(f"No task #{idx}. Run /todo first.")
        return
    todo_id = todos[idx - 1]["id"]
    ok = await mark_todo_done(todo_id)
    if ok:
        title = todos[idx - 1].get("title", "—")
        if lang == "ru":
            await message.answer(f"✅ Задача выполнена: {title}")
        else:
            await message.answer(f"✅ Task done: {title}")
    else:
        if lang == "ru":
            await message.answer("Задача уже выполнена или не найдена.")
        else:
            await message.answer("Task already done or not found.")


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


@router.message(Command("recurring"))
async def cmd_recurring(message: types.Message):
    lang = await get_lang(message.from_user.id)
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=4)
    if len(parts) < 2:
        payments = await get_recurring_payments(user_id)
        if not payments:
            if lang == "ru":
                await message.answer("📋 Нет регулярных платежей.\n\nДобавь: /recurring add Netflix 9.99 USD monthly 1\nУдали: /recurring del 1\nСписок: /recurring list")
            else:
                await message.answer("📋 No recurring payments.\n\nAdd: /recurring add Netflix 9.99 USD monthly 1\nDelete: /recurring del 1\nList: /recurring list")
            return
        total = 0
        lines = []
        for i, p in enumerate(payments, 1):
            amt = float(p.get("amount", 0))
            total += amt
            cur = p.get("currency", "USD")
            name = p.get("name", "")
            day = p.get("day_of_month", 1)
            due = p.get("next_due", "")[:10]
            lines.append(f"{i}. {name} — {amt:.0f} {cur} (day {day}, next: {due})")
        header = "📋 <b>Regular payments:</b>" if lang != "ru" else "📋 <b>Регулярные платежи:</b>"
        total_line = f"\n<b>Total monthly: {total:.0f}</b>" if lang != "ru" else f"\n<b>В месяц: {total:.0f}</b>"
        await message.answer(header + "\n" + "\n".join(lines) + total_line, parse_mode="HTML")
        return

    cmd = parts[1].lower()
    if cmd == "list":
        payments = await get_recurring_payments(user_id)
        if not payments:
            if lang == "ru":
                await message.answer("Нет регулярных платежей.")
            else:
                await message.answer("No recurring payments.")
            return
        lines = []
        for i, p in enumerate(payments, 1):
            amt = p.get("amount", 0)
            cur = p.get("currency", "USD")
            name = p.get("name", "")
            day = p.get("day_of_month", 1)
            due = p.get("next_due", "")[:10]
            lines.append(f"{i}. {name} — {amt} {cur} (day {day}, next: {due})")
        await message.answer("📋 " + "\n".join(lines))
    elif cmd == "add" and len(parts) >= 5:
        name = parts[2]
        try:
            amount = float(parts[3])
        except ValueError:
            if lang == "ru":
                await message.answer("Сумма должна быть числом.")
            else:
                await message.answer("Amount must be a number.")
            return
        currency = parts[4].upper() if len(parts) > 4 else "USD"
        frequency = parts[5] if len(parts) > 5 else "monthly"
        day = int(parts[6]) if len(parts) > 6 else 1
        await add_recurring_payment(user_id, name, amount, currency, frequency, day)
        if lang == "ru":
            await message.answer(f"✅ Добавлен: {name} — {amount:.0f} {currency} (каждый {day}-й день месяца)")
        else:
            await message.answer(f"✅ Added: {name} — {amount:.0f} {currency} (every {day}th)")
    elif cmd == "del" and len(parts) >= 3:
        try:
            idx = int(parts[2])
            payments = await get_recurring_payments(user_id)
            if idx < 1 or idx > len(payments):
                if lang == "ru": await message.answer("Неверный номер.")
                else: await message.answer("Invalid number.")
                return
            pid = payments[idx - 1]["id"]
            await delete_recurring_payment(pid)
            if lang == "ru":
                await message.answer(f"✅ Платёж {idx} удалён.")
            else:
                await message.answer(f"✅ Payment {idx} deleted.")
        except ValueError:
            if lang == "ru": await message.answer("Укажи номер из списка.")
            else: await message.answer("Specify the number from the list.")
    else:
        if lang == "ru": await message.answer("/recurring add Netflix 9.99 USD monthly 1\n/recurring del 1\n/recurring list")
        else: await message.answer("/recurring add Netflix 9.99 USD monthly 1\n/recurring del 1\n/recurring list")


@router.message(Command("dashboard"))
async def cmd_dashboard(message: types.Message):
    lang = await get_lang(message.from_user.id)
    url = config.webhook_url.replace("/webhook", "/dashboard")
    btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=("📊 Open Dashboard" if lang != "ru" else "📊 Открыть дашборд"),
            web_app=types.WebAppInfo(url=url)
        )]
    ])
    if lang == "ru":
        await message.answer("📊 Открой дашборд в один клик:", reply_markup=btn)
    else:
        await message.answer("📊 Open dashboard with one tap:", reply_markup=btn)


@router.message(Command("buy"))
async def cmd_buy(message: types.Message, bot: Bot):
    lang = await get_lang(message.from_user.id)
    btns = [
        [InlineKeyboardButton(
            text=f"📊 {p['label_en']} — {p['stars']} ⭐" if lang != "ru" else f"📊 {p['label_ru']} — {p['stars']} ⭐",
            callback_data=f"buy_{k}"
        )]
        for k, p in STAR_PRICES.items()
    ]
    crypto_label = "💎 Pay with Crypto" if lang != "ru" else "💎 Оплатить криптовалютой"
    btns.append([InlineKeyboardButton(text=crypto_label, callback_data="buy_crypto")])
    kb = InlineKeyboardMarkup(inline_keyboard=btns)
    if lang == "ru":
        await message.answer("Выбери подписку:", reply_markup=kb)
    else:
        await message.answer("Choose a service:", reply_markup=kb)


@router.message(Command("crypto"))
async def cmd_crypto(message: types.Message):
    lang = await get_lang(message.from_user.id)
    if not config.usdc_address:
        if lang == "ru":
            await message.answer("Крипто-платежи временно недоступны.")
        else:
            await message.answer("Crypto payments temporarily unavailable.")
        return

    supported = ", ".join(NETWORKS.keys())

    if lang == "ru":
        msg = (
            f"💳 <b>Оплата USDC</b>\n\n"
            f"Поддерживаемые сети: {supported}\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(нажми на адрес чтобы скопировать)\n\n"
            f"Используй /buy чтобы оплатить услугу."
        )
        await message.answer(msg)
    else:
        msg = (
            f"💳 <b>Pay with USDC</b>\n\n"
            f"Supported networks: {supported}\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(tap the address to copy)\n\n"
            f"Use /buy to purchase a service."
        )
        await message.answer(msg)


@router.message(Command("qr"))
async def cmd_qr(message: types.Message):
    lang = await get_lang(message.from_user.id)
    if not config.usdc_address:
        if lang == "ru":
            await message.answer("Крипто-платежи не настроены.")
        else:
            await message.answer("Crypto payments not configured.")
        return

    supported = ", ".join(n.capitalize() for n in ["ethereum", "polygon", "arbitrum", "base", "bsc", "optimism", "avalanche"])
    if lang == "ru":
        await message.answer(
            f"💳 <b>USDC</b>\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(нажми на адрес чтобы скопировать)\n\n"
            f"✅ <b>Поддерживаемые сети:</b>\n{supported}\n\n"
            f"⚠️ <b>Важно:</b> Отправляй ТОЛЬКО в одну из этих сетей. "
            f"Если отправишь в другую сеть — средства будут утеряны, "
            f"подписка не будет оформлена, и вернуть их невозможно."
        )
    else:
        await message.answer(
            f"💳 <b>USDC</b>\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(tap the address to copy)\n\n"
            f"✅ <b>Supported networks:</b>\n{supported}\n\n"
            f"⚠️ <b>Important:</b> Send ONLY on one of these networks. "
            f"If you send on a different network — funds will be lost, "
            f"subscription will not be activated, and recovery is impossible."
        )
    qr_data = quote(f"ethereum:{config.usdc_address}", safe="")
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={qr_data}"
    try:
        qr_bytes = urlopen(qr_url, timeout=10).read()
        await message.answer_photo(
            photo=types.BufferedInputFile(qr_bytes, filename="qr.png"),
            caption=config.usdc_address,
        )
    except Exception as e:
        logger.warning("QR failed: %s", e)
        if lang == "ru":
            await message.answer("Не удалось сгенерировать QR. Попробуй позже.")
        else:
            await message.answer("Failed to generate QR. Try again later.")


@router.message(F.text.startswith("/confirm"))
async def cmd_confirm(message: types.Message):
    parts = message.text.split(maxsplit=2)
    txid = ""
    specified_net = ""
    if len(parts) >= 2:
        txid = parts[1]
    if len(parts) >= 3:
        specified_net = parts[2].lower()

    if not txid:
        return

    lang = await get_lang(message.from_user.id)
    if not config.usdc_address:
        return

    await message.answer("⏳ Checking transaction..." if lang != "ru" else "⏳ Проверяю транзакцию...")

    result = None
    checked = []
    txid_lower = txid.lower()

    if txid_lower.startswith("0x"):
        evm_nets = [specified_net] if specified_net in NETWORKS else list(NETWORKS.keys())
        for net in evm_nets:
            if not config.etherscan_api_key:
                continue
            checked.append(net)
            result = check_usdc_evm(txid, config.usdc_address, net, config.etherscan_api_key)
            if result:
                break

    if not result:
        checked_str = ", ".join(checked) if checked else "—"
        if lang == "ru":
            await message.answer(
                f"❌ Транзакция не найдена.\n"
                f"Проверено сетей: {checked_str}\n"
                f"Убедись, что TXID правильный и USDC отправлен на верный адрес."
            )
        else:
            await message.answer(
                f"❌ Transaction not found.\n"
                f"Checked networks: {checked_str}\n"
                f"Make sure TXID is correct and USDC was sent to the right address."
            )
        return

    value = result["value"]
    confirmations = result["confirmations"]
    net_name = result["network"]
    from_addr = result["from"]
    to_addr = result["to"]
    txid_short = txid[:16] + "..."

    if lang == "ru":
        await message.answer(
            f"✅ <b>USDC-транзакция найдена!</b>\n"
            f"Сеть: {net_name}\n"
            f"Сумма: {value:.2f} USDC\n"
            f"От: <code>{from_addr[:12]}...</code>\n"
            f"Кому: <code>{to_addr[:12]}...</code>\n"
            f"TXID: <code>{txid_short}</code>\n"
            f"Подтверждений: {confirmations}\n\n"
            f"{'✅ Платёж подтверждён!' if confirmations > 0 else '⏳ Ожидание подтверждений...'}"
        )
    else:
        await message.answer(
            f"✅ <b>USDC transaction found!</b>\n"
            f"Network: {net_name}\n"
            f"Amount: {value:.2f} USDC\n"
            f"From: <code>{from_addr[:12]}...</code>\n"
            f"To: <code>{to_addr[:12]}...</code>\n"
            f"TXID: <code>{txid_short}</code>\n"
            f"Confirmations: {confirmations}\n\n"
            f"{'✅ Payment confirmed!' if confirmations > 0 else '⏳ Waiting for confirmations...'}"
        )

    await log_event(message.from_user.id, "usdc_tx_checked", {
        "txid": txid,
        "value": value,
        "network": result["network"],
        "confirmations": confirmations
    })


@router.callback_query(F.data.in_({"buy_weekly", "buy_monthly", "buy_crypto"}))
async def on_buy_choice(callback: CallbackQuery, bot: Bot):
    key = callback.data[4:]
    lang = await get_lang(callback.from_user.id)

    if key == "crypto":
        await callback.message.delete()
        if not config.usdc_address:
            if lang == "ru":
                await callback.message.answer("Крипто-платежи временно недоступны.")
            else:
                await callback.message.answer("Crypto payments temporarily unavailable.")
            await callback.answer()
            return

        btns = [
            [InlineKeyboardButton(
                text=f"📊 {p['label_en']} — ${p['usdc']} USDC" if lang != "ru" else f"📊 {p['label_ru']} — ${p['usdc']} USDC",
                callback_data=f"crypto_service_{k}"
            )]
            for k, p in CRYPTO_PRICES.items()
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=btns)
        if lang == "ru":
            await callback.message.answer("Выбери подписку для оплаты USDC:", reply_markup=kb)
        else:
            await callback.message.answer("Choose a subscription to pay with USDC:", reply_markup=kb)
        await callback.answer()
        return

    price = STAR_PRICES.get(key)
    if not price:
        await callback.answer("Unknown service")
        return
    title = price["label_en"] if lang != "ru" else price["label_ru"]
    stars_amount = price["stars"]
    prices = [types.LabeledPrice(label=title, amount=stars_amount)]
    await callback.message.delete()
    kwargs = dict(
        chat_id=callback.from_user.id,
        title=title,
        description=title,
        payload=key,
        provider_token="",
        currency="XTR",
        prices=prices,
    )
    if key == "monthly":
        kwargs["subscription_period"] = 2592000
    await bot.send_invoice(**kwargs)
    await callback.answer()


@router.callback_query(F.data.startswith("crypto_service_"))
async def on_crypto_service(callback: CallbackQuery):
    key = callback.data[len("crypto_service_"):]
    price = CRYPTO_PRICES.get(key)
    if not price:
        await callback.answer("Unknown service")
        return
    lang = await get_lang(callback.from_user.id)
    if not config.etherscan_api_key:
        if lang == "ru":
            await callback.message.answer("Платежи временно недоступны.")
        else:
            await callback.message.answer("Payments temporarily unavailable.")
        await callback.answer()
        return

    payment = await create_pending_payment(callback.from_user.id, key, price["usdc"])
    if not payment:
        if lang == "ru":
            await callback.message.answer("Ошибка создания платежа. Попробуй ещё раз.")
        else:
            await callback.message.answer("Failed to create payment. Try again.")
        await callback.answer()
        return

    unique_amount = payment["unique_amount"]
    qr_data = quote(f"ethereum:{config.usdc_address}", safe="")
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={qr_data}"

    title = price["label_ru"] if lang == "ru" else price["label_en"]
    clean_amount = int(price["usdc"])
    supported = ", ".join(n.capitalize() for n in ["ethereum", "polygon", "arbitrum", "base", "bsc", "optimism", "avalanche"])

    if lang == "ru":
        msg = (
            f"💳 <b>{title}</b>\n\n"
            f"Отправь <b>{clean_amount} USDC</b>\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(нажми на адрес чтобы скопировать)\n\n"
            f"✅ <b>Поддерживаемые сети:</b>\n{supported}\n\n"
            f"⚠️ <b>Важно:</b> Отправляй ТОЛЬКО в одну из этих сетей. "
            f"Если отправишь в другую сеть — средства будут утеряны, "
            f"подписка не будет оформлена, и вернуть их невозможно.\n\n"
            f"После отправки бот автоматически проверит платёж.\n"
            f"Ничего вручную вводить не нужно."
        )
        await callback.message.answer(msg)
    else:
        msg = (
            f"💳 <b>{title}</b>\n\n"
            f"Send <b>{clean_amount} USDC</b>\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(tap the address to copy)\n\n"
            f"✅ <b>Supported networks:</b>\n{supported}\n\n"
            f"⚠️ <b>Important:</b> Send ONLY on one of these networks. "
            f"If you send on a different network — funds will be lost, "
            f"subscription will not be activated, and recovery is impossible.\n\n"
            f"Bot will automatically detect the payment.\n"
            f"No manual confirmation needed."
        )
        await callback.message.answer(msg)

    try:
        qr_bytes = urlopen(qr_url, timeout=10).read()
        await callback.message.answer_photo(
            photo=types.BufferedInputFile(qr_bytes, filename="qr.png"),
            caption=f"{clean_amount} USDC"
        )
    except Exception as e:
        logger.warning("QR download failed: %s", e)
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(message: types.Message):
    lang = await get_lang(message.from_user.id)
    payload = message.successful_payment.invoice_payload
    if lang == "ru":
        await message.answer(f"✅ Оплачено! Услуга: {payload}. Чем могу помочь?")
    else:
        await message.answer(f"✅ Payment received! Service: {payload}. What now?")


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
        if len(result) > 4000:
            result = result[:4000] + "..."
        await message.answer(result)
        await log_event(message.from_user.id, "image_analyzed")
    except Exception as e:
        logger.error("Gemini error: %s", e)
        await message.answer(t(lang, "error"))


@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    lang = await get_lang(message.from_user.id)
    if not groq:
        await message.answer(t(lang, "not_ready"))
        return

    if message.from_user.id not in _sheet_cache:
        db_url = await get_user_sheet(message.from_user.id)
        if db_url:
            _sheet_cache[message.from_user.id] = db_url

    await message.answer(t(lang, "thinking"))

    try:
        voice = message.voice
        file = await bot.get_file(voice.file_id)
        buffer = await bot.download_file(file.file_path)
        audio_bytes = buffer.read()

        text = transcribe_audio(groq, audio_bytes)
        if not text:
            if lang == "ru":
                await message.answer("Не удалось распознать голос. Попробуй ещё раз.")
            else:
                await message.answer("Could not transcribe voice. Try again.")
            return

        tz = await get_tz(message.from_user.id)
        result, latency, messages = detect_intent(groq, text, lang=lang)

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
                await message.answer(response_text + t(lang, "voice_prompt"))
        else:
            sheet_url = _sheet_cache.get(message.from_user.id)
            all_responses = []
            turn_count = 0
            current = result  # list of tool_calls
            while turn_count < 10:
                turn_count += 1
                for tool_call in current:
                    resp = await handle_tool_call(tool_call, lang=lang, sheet_url=sheet_url, tz=tz, user_id=message.from_user.id)
                    if resp.startswith("__REPORT__:"):
                        parts = resp.split(":", 2)
                        fmt = parts[1]
                        path = parts[2]
                        fname = f"report.{fmt}"
                        with open(path, "rb") as f:
                            await message.answer_document(types.BufferedInputFile(f.read(), filename=fname))
                        os.unlink(path)
                    else:
                        all_responses.append(resp)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": resp})
                next_result, messages = chat_turn(groq, messages)
                if isinstance(next_result, str):
                    if next_result not in all_responses:
                        all_responses.append(next_result)
                    break
                current = next_result
            response_text = "\n\n".join(all_responses) if all_responses else "Done."
            if all_responses:
                await message.answer(response_text + t(lang, "voice_prompt"))

        await save_chat(message.from_user.id, text, response_text, int(latency * 1000))
        logger.info("Handled voice in %.2fs", latency)
    except Exception as e:
        logger.error("Voice error: %s", e)
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
        url = m.group(0)
        _sheet_cache[message.from_user.id] = url
        await set_user_sheet(message.from_user.id, url)
        if lang == "ru":
            await message.answer("Google Таблица подключена! Теперь я могу читать и записывать данные.")
        else:
            await message.answer("Google Sheet connected! I can now read and write data.")
        return

    if not groq:
        await message.answer(t(lang, "not_ready"))
        return

    tz = await get_tz(message.from_user.id)

    if message.from_user.id not in _sheet_cache:
        db_url = await get_user_sheet(message.from_user.id)
        if db_url:
            _sheet_cache[message.from_user.id] = db_url

    await message.answer(t(lang, "thinking"))

    try:
        result, latency, messages = detect_intent(groq, text, lang=lang)

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
                await message.answer(response_text + t(lang, "voice_prompt"))
        else:
            sheet_url = _sheet_cache.get(message.from_user.id)
            all_responses = []
            turn_count = 0
            current = result
            while turn_count < 10:
                turn_count += 1
                for tool_call in current:
                    resp = await handle_tool_call(tool_call, lang=lang, sheet_url=sheet_url, tz=tz, user_id=message.from_user.id)
                    if resp.startswith("__REPORT__:"):
                        parts = resp.split(":", 2)
                        fmt = parts[1]
                        path = parts[2]
                        fname = f"report.{fmt}"
                        with open(path, "rb") as f:
                            await message.answer_document(types.BufferedInputFile(f.read(), filename=fname))
                        os.unlink(path)
                    else:
                        all_responses.append(resp)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": resp})
                next_result, messages = chat_turn(groq, messages)
                if isinstance(next_result, str):
                    if next_result not in all_responses:
                        all_responses.append(next_result)
                    break
                current = next_result
            response_text = "\n\n".join(all_responses) if all_responses else "Done."
            if all_responses:
                await message.answer(response_text + t(lang, "voice_prompt"))

        await save_chat(message.from_user.id, text, response_text, int(latency * 1000))
        logger.info("Handled message in %.2fs", latency)
    except Exception as e:
        logger.error("Groq error: %s", e)
        await message.answer(t(lang, "error"))
