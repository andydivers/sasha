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
from app.database import get_user_lang, set_user_lang, get_user_tz, set_user_tz, get_user_sheet, set_user_sheet, save_chat, log_event, add_reminder, add_todo, get_todos, mark_todo_done, create_pending_payment
from app.groq_client import create_groq_client, detect_intent, transcribe_audio
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
    "weekly": {"label_en": "Weekly subscription", "label_ru": "Подписка на неделю", "usdc": 8.0},
    "monthly": {"label_en": "Monthly subscription", "label_ru": "Подписка на месяц", "usdc": 20.0},
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
    await set_user_sheet(message.from_user.id, url)
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

    qr_data = quote(f"ethereum:{config.usdc_address}", safe="")
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={qr_data}"
    try:
        qr_bytes = urlopen(qr_url, timeout=10).read()
        caption = config.usdc_address
        await message.answer_photo(
            photo=types.BufferedInputFile(qr_bytes, filename="qr.png"),
            caption=caption,
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

    if lang == "ru":
        msg = (
            f"💳 <b>{title}</b>\n\n"
            f"Отправь <b>ровно {unique_amount} USDC</b>\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(нажми на адрес чтобы скопировать)\n\n"
            f"После отправки бот автоматически проверит платеж.\n"
            f"Ничего вручную вводить не нужно."
        )
        await callback.message.answer(msg)
    else:
        msg = (
            f"💳 <b>{title}</b>\n\n"
            f"Send <b>exactly {unique_amount} USDC</b>\n\n"
            f"<code>{config.usdc_address}</code>\n"
            f"(tap the address to copy)\n\n"
            f"Bot will automatically detect the payment.\n"
            f"No manual confirmation needed."
        )
        await callback.message.answer(msg)

    try:
        qr_bytes = urlopen(qr_url, timeout=10).read()
        await callback.message.answer_photo(
            photo=types.BufferedInputFile(qr_bytes, filename="qr.png"),
            caption=f"{unique_amount} USDC"
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
