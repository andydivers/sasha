import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
from urllib.parse import quote

from aiogram import Bot, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.config import Config
from app.database import get_user_lang, set_user_lang, get_user_tz, set_user_tz, get_user_currency, set_user_currency, get_user_sheet, set_user_sheet, save_chat, log_event, add_reminder, add_todo, get_todos, mark_todo_done, create_pending_payment, get_unsynced_items, mark_items_synced, get_digest_config, set_digest_config, add_recurring_payment, get_recurring_payments, delete_recurring_payment, add_expense, delete_last_expense, delete_expense
from app.groq_client import create_groq_client, detect_intent, chat_turn, transcribe_audio
from app.intents import handle_tool_call, _country_from_location
from app.currency_utils import extract_currency, currency_symbol, format_amount_with_currency
from app.gemini_client import init_gemini, analyze_image
from app.sheets_client import init_sheets, read_sheet, write_sheet, append_row, get_service_email, is_ready as sheets_ready
from app.calendar_client import list_events, delete_event, get_calendar_link, is_ready as calendar_ready
from app.crypto_client import check_usdc_evm, NETWORKS
from app.i18n import t, TRANSLATIONS

logger = logging.getLogger(__name__)
router = Router()


def parse_amount(raw: str) -> str:
    """Parse amount string, correctly handling comma as thousands vs decimal separator.

    Rules:
      - "1,800" or "1.800" with exactly 3 digits after separator → thousands → "1800"
      - "1,8" or "1.8" with 1-2 digits after separator → decimal → "1.8"
      - "1,000,000" → remove all thousands separators → "1000000"
      - "1.200,50" (European) or "1,200.50" (US) → "1200.50"
    """
    if not raw:
        return ""
    s = raw.strip().replace(" ", "")
    # Mixed separators: decide which is the decimal one
    if "," in s and "." in s:
        if s.rindex(",") > s.rindex("."):
            # comma is the decimal separator: "1.200,50" → "1200.50"
            return s.replace(".", "").replace(",", ".")
        # dot is the decimal separator: "1,200.50" → "1200.50"
        return s.replace(",", "")
    # Multiple commas → thousands separators: "1,000,000"
    parts_comma = s.split(",")
    if len(parts_comma) > 2:
        return "".join(parts_comma)
    if "," in s:
        before, after = s.split(",", 1)
        if len(after) == 3 and after.isdigit():
            # "1,800" → 1800 (thousands)
            return before + after
        # "1,8" or "1,80" → 1.8 (decimal)
        return before + "." + after
    # Multiple dots → thousands separators: "1.000.000"
    parts_dot = s.split(".")
    if len(parts_dot) > 2:
        return "".join(parts_dot)
    if "." in s:
        before, after = s.split(".", 1)
        if len(after) == 3 and after.isdigit() and len(before) > 0:
            # Ambiguous: "1.800" could be 1.8 or 1800
            # Heuristic: if it looks like a price with 3 decimal places, keep as decimal
            # But "1.800" in Thai context is usually 1800
            # If before part has digits, treat as thousands for amounts > 100
            if int(before) > 0:
                return before + after  # "1.800" → "1800"
        # Normal decimal: "1.8"
        return s
    return s

config = Config()
groq = create_groq_client(config.groq_api_key) if config.groq_api_key else None

BOT_USERNAME = "HeySasha_bot"
MENTION_RE = re.compile(r"@HeySasha_bot\s*", re.IGNORECASE)


def _is_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


def _should_respond(message: types.Message) -> bool:
    if not _is_group(message):
        return True
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
        return True
    if message.text and f"@{BOT_USERNAME}" in message.text.lower():
        return True
    return False


def _strip_mention(text: str) -> str:
    return MENTION_RE.sub("", text, count=1).strip()

# Always init image analysis — Groq Vision fallback works even without Gemini key
init_gemini(config.gemini_api_key or "")

STAR_PRICES = {
    "weekly": {"label_en": "Weekly subscription", "label_ru": "Подписка на неделю", "stars": 99},
    "monthly": {"label_en": "Monthly subscription", "label_ru": "Подписка на месяц", "stars": 299},
}

CRYPTO_PRICES = {
    "weekly": {"label_en": "Weekly subscription", "label_ru": "Подписка на неделю", "usdc": 1.5},
    "monthly": {"label_en": "Monthly subscription", "label_ru": "Подписка на месяц", "usdc": 3.89},
}

LANG_LIST = ["en", "ru", "es", "fr", "zh", "ar", "pt", "de", "hi", "ja"]

LANG_TO_CURRENCY = {
    "en": "USD", "ru": "RUB", "es": "EUR", "fr": "EUR",
    "zh": "CNY", "ar": "AED", "pt": "BRL", "de": "EUR",
    "hi": "INR", "ja": "JPY",
}

LANG_TOGGLE_CURRENCIES = {
    "pt": ["USD", "EUR", "BRL"],
}

LANG_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(
        text=f"{TRANSLATIONS[code]['flag']} {TRANSLATIONS[code]['name']} ({currency_symbol(LANG_TO_CURRENCY.get(code, 'USD'))})",
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


_EXPENSE_WORDS = {"купил","потратил","оплатил","заплатил","spent","bought","paid","cost","кофе","обед","ужин","завтрак","lunch","dinner","coffee","uber","такси","билет","проезд","бензин","gas","food","еда","продукты","покупка","delivery","доставка"}

_NON_EXPENSE_WORDS = {"напомни","напомнить","напомню","напоминани","напоминание","напоминания","напомин","remind","reminder","встреча","meeting","встречу","завтра","tomorrow","через","надо","нужно","необходимо","запланируй","schedule","plan","событие","event","рожден","день рождения","birthday","ужин сегодня","dinner today","обед сегодня","будильник","alarm","не забудь","забудь","на будущий","следующ"}


_MULTIPLIERS = [
    (r"(?:^|\s)\d[\d.,]*\s*(тысяч|тысячи|тыща|тыщи|тыс|nghìn|ngàn)\b", 1000),
    (r"(?:^|\s)\d[\d.,]*\s*(миллион|миллиона|млн)\b", 1000000),
    (r"(?:^|\s)\d[\d.,]*\s*(миллиард|миллиарда|млрд)\b", 1000000000),
    (r"(?:^|\s)\d[\d.,]*\s*k\b", 1000),
]

# Number words → digits ("пятьдесят тысяч" → "50000"). Whisper often
# transcribes spoken amounts as words; the fallback needs digits.
_NUM_UNITS = {
    "ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_NUM_TEENS = {
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
    "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16,
    "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_NUM_TENS = {
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUM_HUNDREDS = {
    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400,
    "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800,
    "девятьсот": 900, "hundred": 100,
}
_NUM_BIG = {
    "тысяча": 1000, "тысячи": 1000, "тысяч": 1000, "тыс": 1000,
    "миллион": 1000000, "миллиона": 1000000, "миллионов": 1000000, "млн": 1000000,
    "миллиард": 1000000000, "миллиарда": 1000000000, "миллиардов": 1000000000, "млрд": 1000000000,
    "thousand": 1000, "million": 1000000, "billion": 1000000000,
}
_NUM_WORDS_ALL = {**_NUM_UNITS, **_NUM_TEENS, **_NUM_TENS, **_NUM_HUNDREDS, **_NUM_BIG}
_NUM_WORD_ALT = "|".join(sorted(_NUM_WORDS_ALL, key=len, reverse=True))
_NUM_RUN_RE = re.compile(
    r"\b(?:" + _NUM_WORD_ALT + r")(?:\s+(?:" + _NUM_WORD_ALT + r"|\d[\d.,]*))*\b", re.I,
)

# "8,5 миллиона" → "8500000"; "20 тысяч" → "20000". Must run BEFORE word-run
# conversion so the standalone multiplier word is not converted to its scale
# number (which would corrupt "8,5 миллиона" → "8,5 1000000").
_NUM_MULT_WORDS = (
    "тысяча|тысячи|тысяч|тыс|thousand|"
    "миллион|миллиона|миллионов|млн|million|"
    "миллиард|миллиарда|миллиардов|млрд|billion"
)
_NUM_MULT_SCALE = {
    "тысяча": 1000, "тысячи": 1000, "тысяч": 1000, "тыс": 1000, "thousand": 1000,
    "миллион": 1000000, "миллиона": 1000000, "миллионов": 1000000, "млн": 1000000,
    "миллиард": 1000000000, "миллиарда": 1000000000, "миллиардов": 1000000000,
    "млрд": 1000000000, "billion": 1000000000,
    "million": 1000000,
}
_DIGIT_MULT_RE = re.compile(r"(\d[\d.,]*)\s+(" + _NUM_MULT_WORDS + r")\b", re.I)


def _merge_digit_multiplier(text: str) -> str:
    def repl(m):
        try:
            num = float(parse_amount(m.group(1)))
            return str(int(num * _NUM_MULT_SCALE[m.group(2).lower()]))
        except Exception:
            return m.group(0)

    return _DIGIT_MULT_RE.sub(repl, text)


def _eval_num_run(words: list) -> int:
    total = 0
    seg = 0
    for w in words:
        if re.fullmatch(r"\d[\d.,]*", w):
            # Spoken mixed form: "два миллиона 850 тысяч" already merged to
            # "два миллиона 850000" — a digit group inside the run is a part
            # of the same number ("850000" → 850000).
            try:
                seg += float(parse_amount(w))
            except Exception:
                continue
        elif w == "hundred":
            seg = (seg if seg else 1) * 100
        elif w in _NUM_BIG:
            total += (seg if seg else 1) * _NUM_BIG[w]
            seg = 0
        else:
            seg += _NUM_UNITS.get(w, 0) + _NUM_TEENS.get(w, 0) + _NUM_TENS.get(w, 0) + _NUM_HUNDREDS.get(w, 0)
    total += seg
    if float(total).is_integer():
        return int(total)
    return round(total, 2)


def _numwords_to_digits(text: str) -> str:
    if not re.search(r"[а-яёa-z]", text):
        return text
    normalized = text.replace("-", " ")
    normalized = _merge_digit_multiplier(normalized)

    def _repl(m):
        words = [w.lower() for w in m.group().split()]
        try:
            return str(_eval_num_run(words))
        except Exception:
            return m.group()

    return _NUM_RUN_RE.sub(_repl, normalized)


# Split multi-item messages: "еда 300 бат и кофе 100 бат" → two expenses
_SPLIT_RE = re.compile(
    r"\s+(?:и\s+ещё|и|а\s+также|также|ещё|and|also|then|потом|затем|"
    r"y|e|et|und|e\s+mais|và|और|و|以及|和|そして|または|そして)\s+"
    r"|\s*;\s*|,\s*(?!\d)",
    re.I,
)

_CURRENCY_WORDS_CLEANUP = re.compile(
    r"\s*(?:донгов|донга|донг|dong|đồng|"
    r"рублей|рубль|руб|rubles|rub|"
    r"долларов|доллар|dollars|dollar|dólares|dólar|usd|\$|"
    r"фунтов|фунт|pounds|pound|gbp|£|"
    r"евро|euros|euro|eur|€|yenes?|euros?|"
    r"миллионов|миллиона|миллион|млн|миллиардов|миллиарда|миллиард|млрд|"
    r"тысяч|тысячи|тыща|тыщи|тыс|nghìn|ngàn|"
    r"батов|бат|bahts|baht|baths|bath|฿|บาท|₽|₫|reais|"
    r"元|人民币|块|円|ドル|ユーロ|泰铢|"
    r"रुपये|रुपया|रुपिए|₹|"
    r"درهم|يورو|دولار|ليرة|ريال|دينار|جنيه)",
    re.I,
)


def _extract_amount(segment: str) -> str:
    """Extract amount, joining space/comma-grouped thousands: '650 000' → '650000'.

    Also handles irregular spoken numbers Whisper splits into groups without a
    separator: '2000000 850000' → '2850000' (one value). Plain space-grouping
    like '2 000 000' (all groups ≤3 digits) is joined verbatim.
    """
    m = re.search(r"(?<!\d)\d[\d\s.,]*(?!\d)", segment)
    if not m:
        return ""
    raw = m.group().strip()
    parts = raw.split()
    if len(parts) == 1:
        return parse_amount(parts[0])
    if all(re.fullmatch(r"\d{1,3}", p) for p in parts):
        # '2 000 000' → '2000000' (thousands grouping)
        return "".join(parts)
    # Groups are already full numbers: '2000000 850000' → 2850000
    total = 0.0
    for p in parts:
        try:
            total += float(parse_amount(p))
        except Exception:
            return raw.replace(" ", "")
    if float(total).is_integer():
        return str(int(total))
    return str(round(total, 2))


async def _try_save_expenses_fallback(text: str, user_id: int) -> list:
    """Parse and save one or more expenses from text without AI.

    Returns list of (description, amount, currency) actually saved.
    """
    text = _numwords_to_digits(text)
    lowered = text.lower().strip()
    if not re.search(r"\d", text):
        return []

    for w in _NON_EXPENSE_WORDS:
        if w in lowered:
            return []

    segments = [s.strip() for s in _SPLIT_RE.split(text) if s.strip()]
    numbered = [s for s in segments if re.search(r"\d", s)]
    if len(numbered) < 2:
        numbered = [text]

    # "доходы 2000000 850000 донгов": two amounts dictated without a separator
    # become separate items (split only between two digits — a description
    # followed by a number like "заселение 535000 донгов" must NOT be split).
    # Spoken-word numbers are already merged upstream ("два миллиона 850
    # тысяч" → "2850000"), proper grouping like "2 000 000" stays a single
    # number (groups ≤3 digits don't split here).
    expanded = []
    for s in numbered:
        parts = re.split(r"(?<=\d)\s+(?=\d{4,})", s)
        expanded.extend(parts if len(parts) > 1 else [s])
    numbered = expanded

    _INCOME_RE = re.compile(
        r"(?:получ|зарабат|поступ|приход|пришл|зачисл|перечисл|начисл|аванс|"
        r"доход|зарплат|выручк|прибыль|кэшбэк|кэшбек|cashback|"
        r"income|salary|earned|received|wage|paycheck|refund|"
        r"ingreso|salario|salaire|revenu|収入|給料|收入|工资|"
        r"आय|वेतन|salário|renda|رزق|راتب)", re.I,
    )

    _EXPENSE_RE = re.compile(
        r"потратил|потратила|потратили|купил|купила|купили|заплатил|заплатила|"
        r"оплатил|оплатила|оплата|расчёт|расходы|снял|сняла|покупк|платил|платим|долг",
        re.I,
    )

    # Income intent spreads to every item unless a segment names a cost.
    text_is_income = bool(_INCOME_RE.search(text))

    def _is_income(segment: str) -> bool:
        if _EXPENSE_RE.search(segment):
            return False
        if text_is_income:
            return True
        return bool(_INCOME_RE.search(segment))

    saved: list = []
    last_desc = ""
    lang = await get_lang(user_id)
    exp_label = "расход" if lang == "ru" else "expense"
    inc_label = "доход" if lang == "ru" else "income"
    for seg in numbered:
        try:
            raw = _extract_amount(seg)
            if not raw:
                continue
            mult = 1
            for pattern, m in _MULTIPLIERS:
                if re.search(pattern, seg.lower()):
                    mult = m
                    break
            amt = float(parse_amount(raw)) * mult
            amount = str(int(amt)) if amt.is_integer() else str(round(amt, 2))
            user_cur = await get_user_currency(user_id)
            cur = extract_currency(seg) or user_cur or ""
            desc = _CURRENCY_WORDS_CLEANUP.sub("", seg)
            desc = re.sub(r"(?<=\d)\s*k\b", "", desc, flags=re.I)
            desc = re.sub(r"\d[\d.,]*\s*", "", desc)
            desc = re.sub(r"\s+", " ", desc).strip().strip(",-;:")
            if desc:
                last_desc = desc
            elif last_desc:
                # Adjacent number from the same utterance: reuse the previous item's name
                desc = last_desc
            kind = "income" if _is_income(seg) else "expense"
            if not desc:
                # Nothing left after cleanup and no prior item to inherit from:
                # use a generic label instead of the raw number text.
                desc = inc_label if kind == "income" else exp_label
            await add_expense(user_id, desc, amount, kind, currency=cur)
            saved.append((desc, amount, cur, kind))
        except Exception as e:
            logger.error("Fallback save expense failed for user %s: %s", user_id, e)
    return saved


def _format_saved_expenses(items: list) -> str:
    lines = []
    for item in items:
        if len(item) == 4:
            desc, amt, cur, kind = item
        else:
            desc, amt, cur = item
            kind = "expense"
        sym = currency_symbol(cur) if cur else ""
        if kind == "income":
            lines.append(f"💚 {desc}{' : +' + amt + (' ' + sym if sym else '') if amt else ''}")
        else:
            lines.append(f"💰 {desc}{' : ' + amt + (' ' + sym if sym else '') if amt else ''}")
    return "\n".join(lines)


async def _conversion_lines(items: list, lang: str, user_id: int) -> str:
    """'≈ 5 206 610 VND / 16 600 RUB' lines for saved items.

    Targets:
      - ru: USD, RUB and local currency (e.g. VND)
      - other langs: USD, user's home currency and local currency
    Skips the currency the item is already in.
    """
    from app.currency import convert_amount

    targets = ["USD"]
    if lang == "ru":
        targets.append("RUB")
    user_cur = (await get_user_currency(user_id) or "").upper()
    if user_cur and user_cur not in targets:
        targets.append(user_cur)
    try:
        tz = await get_tz(user_id)
        local = _country_from_location(tz)
        if local and local not in targets:
            targets.append(local)
    except Exception:
        pass

    lines = []
    for item in items:
        cur = (item[2] if len(item) >= 3 else "").upper()
        amt = item[1] if len(item) >= 2 else ""
        if not cur or not amt:
            continue
        convs = []
        for t in targets:
            if t == cur:
                continue
            try:
                val = convert_amount(float(amt), cur, t)
            except Exception:
                continue
            if t in ("VND", "JPY"):
                disp = f"{int(round(val)):,}".replace(",", " ")
            else:
                disp = f"{val:,.2f}".replace(",", " ")
            convs.append(f"{disp} {t}")
        if convs:
            lines.append("≈ " + " / ".join(convs))
    return "\n".join(lines)


async def get_tz(user_id: int) -> str:
    if user_id not in _tz_cache:
        tz = await get_user_tz(user_id)
        _tz_cache[user_id] = tz if tz else "UTC"
    return _tz_cache.get(user_id, "UTC")


dashboard_url = config.webhook_url.replace("/webhook", "/dashboard") if config.webhook_url else "https://sasha-dbgw.onrender.com/dashboard"


def _call_signature(tool_call) -> str:
    """Normalized tool-call signature for dedup: same logical call regardless
    of JSON key order/whitespace in arguments (prevents duplicate saves)."""
    name = tool_call.function.name
    args_raw = getattr(tool_call.function, "arguments", "") or ""
    try:
        args = json.loads(args_raw)
        if isinstance(args, dict):
            args_raw = json.dumps(args, sort_keys=True, ensure_ascii=False)
    except Exception:
        pass
    return f"{name}:{args_raw}"
MENU_LABELS = {
    "en": {"howto": "🎤 How it works", "help": "📋 Commands", "dash": "📊 Dashboard", "buy": "💳 Buy subscription", "lang": "🌐 Language", "currency": "💱 Currency"},
    "ru": {"howto": "🎤 Как работать", "help": "📋 Команды", "dash": "📊 Дашборд", "buy": "💳 Купить подписку", "lang": "🌐 Язык", "currency": "💱 Валюта"},
    "es": {"howto": "🎤 Cómo funciona", "help": "📋 Comandos", "dash": "📊 Panel", "buy": "💳 Comprar", "lang": "🌐 Idioma", "currency": "💱 Moneda"},
    "fr": {"howto": "🎤 Comment ça marche", "help": "📋 Commandes", "dash": "📊 Tableau", "buy": "💳 Acheter", "lang": "🌐 Langue", "currency": "💱 Devise"},
    "zh": {"howto": "🎤 使用方法", "help": "📋 命令", "dash": "📊 仪表盘", "buy": "💳 订阅", "lang": "🌐 语言", "currency": "💱 货币"},
    "ar": {"howto": "🎤 كيف يعمل", "help": "📋 الأوامر", "dash": "📊 لوحة", "buy": "💳 اشتراك", "lang": "🌐 اللغة", "currency": "💱 العملة"},
    "pt": {"howto": "🎤 Como funciona", "help": "📋 Comandos", "dash": "📊 Painel", "buy": "💳 Comprar", "lang": "🌐 Idioma", "currency": "💱 Moeda"},
    "de": {"howto": "🎤 So funktioniert's", "help": "📋 Befehle", "dash": "📊 Dashboard", "buy": "💳 Abo", "lang": "🌐 Sprache", "currency": "💱 Währung"},
    "hi": {"howto": "🎤 यह कैसे काम करता है", "help": "📋 कमांड", "dash": "📊 डैशबोर्ड", "buy": "💳 सब्सक्रिप्शन", "lang": "🌐 भाषा", "currency": "💱 मुद्रा"},
    "ja": {"howto": "🎤 使い方", "help": "📋 コマンド", "dash": "📊 ダッシュボード", "buy": "💳 購読", "lang": "🌐 言語", "currency": "💱 通貨"},
}

START_MENU_EN = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=MENU_LABELS["en"]["howto"], callback_data="menu_howto")],
    [InlineKeyboardButton(text=MENU_LABELS["en"]["help"], callback_data="menu_help")],
    [InlineKeyboardButton(text=MENU_LABELS["en"]["dash"], web_app=types.WebAppInfo(url=dashboard_url))],
    [InlineKeyboardButton(text=MENU_LABELS["en"]["buy"], callback_data="buy_show")],
    [InlineKeyboardButton(text=MENU_LABELS["en"]["lang"], callback_data="menu_lang")],
])
START_MENU_RU = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=MENU_LABELS["ru"]["howto"], callback_data="menu_howto")],
    [InlineKeyboardButton(text=MENU_LABELS["ru"]["help"], callback_data="menu_help")],
    [InlineKeyboardButton(text=MENU_LABELS["ru"]["dash"], web_app=types.WebAppInfo(url=dashboard_url))],
    [InlineKeyboardButton(text=MENU_LABELS["ru"]["buy"], callback_data="buy_show")],
    [InlineKeyboardButton(text=MENU_LABELS["ru"]["lang"], callback_data="menu_lang")],
])

def _build_menu(lang: str) -> InlineKeyboardMarkup:
    labels = MENU_LABELS.get(lang, MENU_LABELS["en"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=labels["howto"], callback_data="menu_howto")],
        [InlineKeyboardButton(text=labels["currency"], callback_data="menu_currency")],
        [InlineKeyboardButton(text=labels["dash"], web_app=types.WebAppInfo(url=dashboard_url))],
        [InlineKeyboardButton(text=labels["help"], callback_data="menu_help")],
        [InlineKeyboardButton(text=labels["buy"], callback_data="buy_show")],
        [InlineKeyboardButton(text=labels["lang"], callback_data="menu_lang")],
    ])


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    lang = await get_lang(user_id)
    menu = _build_menu(lang)
    msg = t(lang, "welcome")
    await message.answer(msg, parse_mode="HTML", reply_markup=menu)
    await message.answer(t(lang, "onboarding_voice"), parse_mode="HTML")
    # Enable digest by default at 08:00
    try:
        cfg = await get_digest_config(user_id)
        if not cfg.get("digest_enabled"):
            await set_digest_config(user_id, True, "08:00")
    except Exception:
        pass
    try:
        await message.bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=types.MenuButtonWebApp(
                text="📊 Sasha" if lang != "ru" else "📊 Саша",
                web_app=types.WebAppInfo(url=dashboard_url)
            )
        )
    except Exception as e:
        logger.warning("Failed to set menu button: %s", e)


@router.callback_query(F.data.in_({"menu_howto", "menu_help", "menu_lang", "menu_back", "buy_show", "menu_currency"}))
async def on_menu_callback(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    data = callback.data
    menu = _build_menu(lang)
    if data == "menu_howto":
        back = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Menu" if lang != "ru" else "🏠 Меню", callback_data="menu_back")]
        ])
        await callback.message.edit_text(t(lang, "onboarding_voice"), parse_mode="HTML", reply_markup=back)
    elif data == "menu_currency":
        cur = await get_user_currency(callback.from_user.id)
        sym = currency_symbol(cur) if cur else ""
        popular = [
            [InlineKeyboardButton(text=f"฿ THB", callback_data="cur_THB"),
             InlineKeyboardButton(text=f"₽ RUB", callback_data="cur_RUB"),
             InlineKeyboardButton(text=f"$ USD", callback_data="cur_USD")],
            [InlineKeyboardButton(text=f"€ EUR", callback_data="cur_EUR"),
             InlineKeyboardButton(text=f"£ GBP", callback_data="cur_GBP"),
             InlineKeyboardButton(text=f"₴ UAH", callback_data="cur_UAH")],
            [InlineKeyboardButton(text="🏠 Menu" if lang != "ru" else "🏠 Меню", callback_data="menu_back")],
        ]
        if lang == "ru":
            msg = f"💱 <b>Текущая валюта:</b> {cur or 'не задана'} {sym}\n\nВыбери или напиши /currency КОД\n(THB, RUB, USD, EUR, UAH, KZT...)"
        else:
            msg = f"💱 <b>Your currency:</b> {cur or 'not set'} {sym}\n\nChoose one or type /currency CODE\n(THB, RUB, USD, EUR, UAH, KZT...)"
        await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=popular))
    elif data == "menu_help":
        back = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Menu" if lang != "ru" else "🏠 Меню", callback_data="menu_back")]
        ])
        await callback.message.edit_text(t(lang, "help"), parse_mode="HTML", reply_markup=back)
    elif data == "menu_lang":
        langs = {l: TRANSLATIONS.get(l, {}).get("name", l) for l in LANG_LIST}
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{TRANSLATIONS.get(l, {}).get('flag', '')} {langs[l]}", callback_data=f"lang_{l}")]
            for l in LANG_LIST
        ])
        await callback.message.edit_text(t(lang, "lang_prompt"), reply_markup=kb)
    elif data == "menu_back":
        await callback.message.edit_text(t(lang, "welcome"), reply_markup=menu, parse_mode="HTML")
    elif data == "buy_show":
        btns = [
            [InlineKeyboardButton(text="📊 Weekly $1.49 / 99⭐" if lang != "ru" else "📊 Неделя $1.49 / 99⭐", callback_data="buy_weekly")],
            [InlineKeyboardButton(text="📊 Monthly $3.89 / 299⭐" if lang != "ru" else "📊 Месяц $3.89 / 299⭐", callback_data="buy_monthly")],
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
    # Auto-set default currency from language
    cur_from_lang = LANG_TO_CURRENCY.get(lang, "")
    if cur_from_lang:
        await set_user_currency(callback.from_user.id, cur_from_lang)
    await callback.message.edit_text(t(lang, "lang_changed"))
    menu = _build_menu(lang)
    await callback.message.answer(t(lang, "welcome"), reply_markup=menu, parse_mode="HTML")
    await callback.message.answer(t(lang, "onboarding_voice"), parse_mode="HTML")
    try:
        await callback.bot.set_chat_menu_button(
            chat_id=callback.message.chat.id,
            menu_button=types.MenuButtonWebApp(
                text="📊 Sasha" if lang != "ru" else "📊 Саша",
                web_app=types.WebAppInfo(url=dashboard_url)
            )
        )
    except Exception as e:
        logger.warning("Failed to update menu button: %s", e)


@router.callback_query(F.data.startswith("cur_"))
async def on_currency_choice(callback: CallbackQuery):
    """Handle currency selection from menu buttons."""
    cur = callback.data.split("_", 1)[1].upper()
    lang = await get_lang(callback.from_user.id)
    if cur not in _VALID_CURRENCIES:
        await callback.answer("Invalid currency")
        return
    await set_user_currency(callback.from_user.id, cur)
    sym = currency_symbol(cur)
    menu = _build_menu(lang)
    if lang == "ru":
        await callback.message.edit_text(f"✅ Валюта установлена: {cur} {sym}", reply_markup=menu)
    else:
        await callback.message.edit_text(f"✅ Currency set: {cur} {sym}", reply_markup=menu)
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "help"), parse_mode="HTML")


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "ping"))


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    lang = await get_lang(message.from_user.id)
    langs = {l: TRANSLATIONS.get(l, {}).get("name", l) for l in LANG_LIST}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{TRANSLATIONS.get(l, {}).get('flag', '')} {langs[l]}", callback_data=f"lang_{l}")]
        for l in LANG_LIST
    ])
    await message.answer(t(lang, "lang_prompt"), reply_markup=kb)


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


_VALID_CURRENCIES = frozenset({
    "USD", "EUR", "GBP", "RUB", "THB", "JPY", "CNY", "INR", "SGD", "VND",
    "IDR", "MYR", "PHP", "KRW", "AUD", "CAD", "BRL", "TRY", "AED", "CHF",
    "HKD", "ILS", "MXN", "NZD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
    "UAH", "KZT", "MNT", "GEL", "USDT", "USDC", "BTC",
})


@router.message(Command("currency"))
async def cmd_currency(message: types.Message):
    lang = await get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        cur = await get_user_currency(message.from_user.id)
        sym = currency_symbol(cur) if cur else ""
        if lang == "ru":
            msg = f"Твоя валюта: {cur or 'не задана'} {sym}\nИзменить: /currency USD"
        else:
            msg = f"Your currency: {cur or 'not set'} {sym}\nChange: /currency USD"
        await message.answer(msg)
        return

    cur = parts[1].upper().strip()
    if cur not in _VALID_CURRENCIES:
        if lang == "ru":
            await message.answer(f"Неизвестная валюта: {cur}. Примеры: USD, EUR, THB, RUB, UAH")
        else:
            await message.answer(f"Unknown currency: {cur}. Examples: USD, EUR, THB, RUB, UAH")
        return

    await set_user_currency(message.from_user.id, cur)
    sym = currency_symbol(cur)
    if lang == "ru":
        await message.answer(f"✅ Валюта установлена: {cur} {sym}")
    else:
        await message.answer(f"✅ Currency set: {cur} {sym}")


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


@router.message(Command("undo"))
async def cmd_undo(message: types.Message):
    """Delete the last recorded expense. Useful when receipt scan saved wrong data."""
    lang = await get_lang(message.from_user.id)
    user_id = message.from_user.id
    deleted = await delete_last_expense(user_id)
    if deleted:
        desc = deleted.get("description", "—")
        amt = deleted.get("amount", "")
        if lang == "ru":
            await message.answer(f"❌ <b>Расход удалён:</b> {desc} ({amt})", parse_mode="HTML")
        else:
            await message.answer(f"❌ <b>Expense deleted:</b> {desc} ({amt})", parse_mode="HTML")
    else:
        if lang == "ru":
            await message.answer("Нет расходов для удаления.")
        else:
            await message.answer("No expenses to delete.")


@router.message(Command("export"))
async def cmd_export(message: types.Message):
    """Export expenses as CSV file with currency column."""
    lang = await get_lang(message.from_user.id)
    user_id = message.from_user.id
    from app.database import get_user_items
    import io
    import csv
    from aiogram.types import BufferedInputFile

    items = await get_user_items(user_id, limit=500)
    if not items:
        if lang == "ru":
            await message.answer("Нет расходов для экспорта.")
        else:
            await message.answer("No expenses to export.")
        return

    buf = io.StringIO()
    writer = csv.writer(buf)
    # Header
    writer.writerow(["date", "description", "amount", "currency", "category"])
    for item in items:
        created = item.get("created_at", "")[:10] if item.get("created_at") else ""
        desc = item.get("description", "")
        amt = item.get("amount", "")
        cur = item.get("currency", "")
        cat = item.get("category", "")
        writer.writerow([created, desc, amt, cur, cat])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel
    filename = f"sasha_export_{datetime.now().strftime('%Y%m%d')}.csv"

    try:
        doc = BufferedInputFile(csv_bytes, filename=filename)
        await message.answer_document(
            doc,
            caption=f"📊 {len(items)} записей" if lang == "ru" else f"📊 {len(items)} records exported",
        )
    except Exception as e:
        logger.error("Export failed: %s", e)
        if lang == "ru":
            await message.answer("Ошибка экспорта. Попробуй позже.")
        else:
            await message.answer("Export failed. Try again later.")


@router.callback_query(F.data == "undo_receipt")
async def on_undo_receipt(callback: CallbackQuery):
    """Undo the last receipt-scanned expense."""
    lang = await get_lang(callback.from_user.id)
    user_id = callback.from_user.id
    deleted = await delete_last_expense(user_id)
    if deleted:
        desc = deleted.get("description", "—")
        amt = deleted.get("amount", "")
        if lang == "ru":
            await callback.message.edit_text(
                f"🧾 ~~Чек распознан~~\n\n❌ <b>Расход удалён:</b> {desc} ({amt})",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                f"🧾 ~~Receipt scanned~~\n\n❌ <b>Expense deleted:</b> {desc} ({amt})",
                parse_mode="HTML",
            )
    else:
        if lang == "ru":
            await callback.answer("Нет расходов для удаления", show_alert=True)
        else:
            await callback.answer("No expenses to delete", show_alert=True)


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


@router.my_chat_member()
async def on_chat_member(update: types.ChatMemberUpdated):
    if update.new_chat_member.status == "member":
        name = update.chat.title or update.chat.username or "group"
        await update.bot.send_message(
            update.chat.id,
            f"Hi! I'm Sasha. Say @{BOT_USERNAME} coffee 4 bucks to log an expense, or add a task, or any other voice command.\n\nAdd me to your group and I'll help track expenses for everyone."
        )


@router.message(F.photo)
async def handle_photo(message: types.Message, bot: Bot):
    if _is_group(message):
        caption = (message.caption or "").strip()
        if not message.reply_to_message and not MENTION_RE.match(caption):
            return
    lang = await get_lang(message.from_user.id)
    user_id = message.from_user.id
    caption = message.caption or ""

    await message.answer(t(lang, "thinking"))

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        image_bytes = await bot.download_file(file.file_path)

        # Detect image type from caption keywords
        caption_lower = caption.lower()
        is_bank_statement = any(w in caption_lower for w in
            ["bank", "statement", "выписка", "отчет", "отчёт", "statement", "history", "история"])
        is_receipt = not caption or any(w in caption_lower for w in
            ["receipt", "чек", "счёт", "bill", "invoice", "сумма", "итого", "total"])

        if is_bank_statement:
            # Bank statement: extract multiple transactions
            statement_prompt = (
                "This is a bank statement or transaction history. Extract ALL transactions as a JSON array:\n"
                '[{"date": "YYYY-MM-DD", "description": "merchant or description", '
                '"amount": "number with sign (- for expense, + for income)", "currency": "THB/USD/RUB/etc"}]\n'
                "Return ONLY the JSON array. If you can't identify transactions, return: {\"error\": \"not a statement\"}"
            )
            result = analyze_image(image_bytes.read(), "image/jpeg", statement_prompt)

            try:
                import json as _json
                # Try to parse as array
                arr_match = re.search(r'\[.*\]', result, re.DOTALL)
                obj_match = re.search(r'\{[^{}]+\}', result, re.DOTALL)

                if arr_match:
                    transactions = _json.loads(arr_match.group())
                    saved = 0
                    for tx in transactions[:20]:
                        desc = tx.get("description", "")
                        amount = str(abs(float(str(tx.get("amount", "0")).replace("+", "").replace("-", ""))))
                        is_income = str(tx.get("amount", "")).startswith("+") or float(str(tx.get("amount", "0")).replace("+", "")) > 0
                        cat = "income" if is_income else "expense"
                        tx_cur = str(tx.get("currency", "")).strip().upper() or ""
                        if not tx_cur:
                            tx_cur = await get_user_currency(user_id) or ""
                        try:
                            await add_expense(user_id, desc, amount, cat, currency=tx_cur)
                            saved += 1
                        except Exception:
                            pass
                    if saved > 0:
                        if lang == "ru":
                            reply = f"🏦 <b>Выписка обработана!</b>\n\n📋 {saved} транзакций распознано и записано"
                        else:
                            reply = f"🏦 <b>Statement processed!</b>\n\n📋 {saved} transactions recognized and saved"
                        undo_kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(
                                text="❌ Отменить все" if lang == "ru" else "❌ Undo all",
                                callback_data="undo_receipt"
                            ),
                        ]])
                        await message.answer(reply, parse_mode="HTML", reply_markup=undo_kb)
                        await log_event(user_id, "bank_statement_scanned")
                        return
                elif obj_match:
                    # Single transaction or error
                    data = _json.loads(obj_match.group())
                    if "error" in data:
                        # Not a statement, try as receipt
                        is_receipt = True
                    else:
                        # Single transaction
                        desc = data.get("description", "")
                        amount = str(abs(float(str(data.get("amount", "0")))))
                        is_income = str(data.get("amount", "")).startswith("+")
                        cat = "income" if is_income else "expense"
                        tx_cur = str(data.get("currency", "")).strip().upper() or ""
                        if not tx_cur:
                            tx_cur = await get_user_currency(user_id) or ""
                        await add_expense(user_id, desc, amount, cat, currency=tx_cur)
                        if lang == "ru":
                            reply = f"🏦 <b>Транзакция распознана!</b>\n\n💰 {desc}: {data.get('amount', '')}"
                        else:
                            reply = f"🏦 <b>Transaction recognized!</b>\n\n💰 {desc}: {data.get('amount', '')}"
                        undo_kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(
                                text="❌ Отменить" if lang == "ru" else "❌ Undo",
                                callback_data="undo_receipt"
                            ),
                        ]])
                        await message.answer(reply, parse_mode="HTML", reply_markup=undo_kb)
                        await log_event(user_id, "bank_statement_scanned")
                        return
            except Exception as e:
                logger.warning("Bank statement parsing failed: %s", e)
                # Fall through to receipt mode

        if is_receipt and not is_bank_statement:
            # Receipt mode: extract structured data
            receipt_prompt = (
                "Extract from this receipt/bill image. Return JSON ONLY, no other text:\n"
                '{"store": "store name", "total": "amount with currency", '
                '"date": "date if visible", "items": ["item1 - price1", "item2 - price2"]}\n'
                "If you can't identify a receipt, return: {\"error\": \"not a receipt\"}"
            )
            result = analyze_image(image_bytes.read(), "image/jpeg", receipt_prompt)

            # Try to parse as JSON receipt
            try:
                import json as _json
                json_match = re.search(r'\{[^{}]+\}', result, re.DOTALL)
                if json_match:
                    receipt_data = _json.loads(json_match.group())
                    if "error" not in receipt_data and receipt_data.get("total"):
                        store = receipt_data.get("store", "")
                        total = receipt_data.get("total", "")
                        items = receipt_data.get("items", [])

                        # Extract amount for saving
                        nums = re.findall(r"[\d]+[.,]?[\d]*", total)
                        amount = parse_amount(nums[0]) if nums else ""

                        # Extract currency from total string (e.g. "1,800 THB")
                        receipt_cur = extract_currency(total) or extract_currency(result)
                        user_cur = await get_user_currency(user_id)
                        currency = receipt_cur or user_cur or ""

                        # Save as expense
                        desc = f"{store} ({', '.join(items[:3])})" if items else store
                        await add_expense(user_id, desc, amount, "expense", currency=currency)

                        if lang == "ru":
                            reply = f"🧾 <b>Чек распознан!</b>\n\n🏪 {store}\n💰 {total}"
                            if items:
                                reply += "\n\n📋 " + "\n📋 ".join(items[:5])
                            reply += "\n\n✅ Расход записан"
                        else:
                            reply = f"🧾 <b>Receipt scanned!</b>\n\n🏪 {store}\n💰 {total}"
                            if items:
                                reply += "\n\n📋 " + "\n📋 ".join(items[:5])
                            reply += "\n\n✅ Expense saved"

                        # Add "Undo" button so user can delete if wrong
                        undo_kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(
                                text="❌ Отменить" if lang == "ru" else "❌ Undo",
                                callback_data="undo_receipt"
                            ),
                        ]])
                        await message.answer(reply, parse_mode="HTML", reply_markup=undo_kb)
                        await log_event(user_id, "receipt_scanned")
                        return
            except Exception as e:
                logger.warning("Receipt parsing failed: %s", e)

        # General image analysis (or failed receipt/bank parse)
        if not is_receipt and not is_bank_statement:
            result = analyze_image(image_bytes.read(), "image/jpeg", caption)
        elif not result:
            result = analyze_image(image_bytes.read(), "image/jpeg",
                "Describe what you see. If this is a financial document, extract any amounts.")

        if len(result) > 4000:
            result = result[:4000] + "..."
        await message.answer(result)

        await log_event(user_id, "image_analyzed")
    except Exception as e:
        logger.error("Image analysis error: %s", e)
        await message.answer(t(lang, "error"))


@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    lang = await get_lang(message.from_user.id)
    if not groq:
        await message.answer(t(lang, "not_ready"))
        return

    if _is_group(message) and not message.reply_to_message:
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

        text = transcribe_audio(groq, audio_bytes, language=lang)
        if not text:
            if lang == "ru":
                await message.answer("Не удалось распознать голос. Попробуй ещё раз.")
            else:
                await message.answer("Could not transcribe voice. Try again.")
            return

        tz = await get_tz(message.from_user.id)

        heard_text = text
        norm_text = _numwords_to_digits(text)

        suffix = "" if _is_group(message) else t(lang, "voice_prompt")
        heard = f"\n\n🎤 Вы сказали: «{heard_text}»"
        # Do not let a partial transcription of a long voice note become one
        # wrong expense. Let the tool-calling path interpret complex notes.
        amount_mentions = re.findall(r"\d[\d\s.,]*", norm_text)
        use_fast_fallback = len(amount_mentions) >= 2 or len(norm_text.split()) <= 8
        saved_items = (
            await _try_save_expenses_fallback(norm_text, message.from_user.id)
            if use_fast_fallback else []
        )

        if saved_items:
            response_text = _format_saved_expenses(saved_items)
            conv = await _conversion_lines(saved_items, lang, message.from_user.id)
            if conv:
                response_text += "\n" + conv
            response_text += heard
            await message.answer(response_text + suffix)
            latency = 0
        else:
            result, latency, messages = detect_intent(groq, norm_text, lang=lang)

            if isinstance(result, str):
                response_text = re.sub(r"(?:<function[^>]*>.*?(?:</?function>)?|\{\{.*?\}\})", "", result, flags=re.DOTALL).strip()
                if response_text.startswith("__REPORT__:"):
                    parts = response_text.split(":", 2)
                    fmt = parts[1]
                    path = parts[2]
                    fname = f"report.{fmt}"
                    with open(path, "rb") as f:
                        await message.answer_document(types.BufferedInputFile(f.read(), filename=fname))
                    os.unlink(path)
                else:
                    await message.answer(response_text + suffix)
            else:
                sheet_url = _sheet_cache.get(message.from_user.id)
                all_responses = []
                turn_count = 0
                current = result
                seen_calls = set()
                while turn_count < 10:
                    turn_count += 1
                    for tool_call in current:
                        func_name = tool_call.function.name if hasattr(tool_call, 'function') else "tool"
                        # Dedup by full call signature (name+args), not just name
                        # This allows multiple add_expense calls with different items
                        call_sig = _call_signature(tool_call)
                        if call_sig in seen_calls:
                            continue
                        seen_calls.add(call_sig)
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
                        if func_name in ("get_spending_summary", "generate_report"):
                            resp += "\n[This is read-only data. Do NOT call add_expense or add_income for these amounts.]"
                        messages.append({"role": "user", "content": f"[Result of {func_name}]: {resp}"})
                    if not current:
                        break
                    next_result, messages = chat_turn(groq, messages)
                    if isinstance(next_result, str):
                        next_result = re.sub(r"(?:<function[^>]*>.*?(?:</?function>)?|\{\{.*?\}\})", "", next_result, flags=re.DOTALL).strip()
                        if next_result not in all_responses and next_result:
                            all_responses.append(next_result)
                        break
                    current = next_result
                response_text = all_responses[0] if len(all_responses) == 1 else "\n\n".join(all_responses) if all_responses else "Done."
                if all_responses:
                    await message.answer(response_text + suffix + heard)

        await save_chat(message.from_user.id, text, response_text, int(latency * 1000))
        logger.info("Handled voice in %.2fs", latency)
    except Exception as e:
        logger.error("Voice error: %s", e)
        await message.answer(t(lang, "error"))


@router.message()
async def handle_message(message: types.Message):
    if not message.text:
        return

    if not _should_respond(message):
        return

    lang = await get_lang(message.from_user.id)
    text = _strip_mention(message.text.strip())

    if not text:
        if lang == "ru":
            await message.answer("Скажи, что нужно сделать. Например: кофе 80 бат")
        else:
            await message.answer("What do you need? Say: coffee 4 bucks")
        return

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

    suffix = "" if _is_group(message) else t(lang, "voice_prompt")

    try:
        norm_text = _numwords_to_digits(text)
        saved_items = await _try_save_expenses_fallback(norm_text, message.from_user.id)

        if saved_items:
            response_text = _format_saved_expenses(saved_items)
            conv = await _conversion_lines(saved_items, lang, message.from_user.id)
            if conv:
                response_text += "\n" + conv
            await message.answer(response_text + suffix)
            latency = 0
        else:
            result, latency, messages = detect_intent(groq, norm_text, lang=lang)

            if isinstance(result, str):
                response_text = re.sub(r"(?:<function[^>]*>.*?(?:</?function>)?|\{\{.*?\}\})", "", result, flags=re.DOTALL).strip()
                if response_text.startswith("__REPORT__:"):
                    parts = response_text.split(":", 2)
                    fmt = parts[1]
                    path = parts[2]
                    fname = f"report.{fmt}"
                    with open(path, "rb") as f:
                        await message.answer_document(types.BufferedInputFile(f.read(), filename=fname))
                    os.unlink(path)
                else:
                    await message.answer(response_text + suffix)
            else:
                sheet_url = _sheet_cache.get(message.from_user.id)
                all_responses = []
                turn_count = 0
                current = result
                seen_calls = set()
                while turn_count < 10:
                    turn_count += 1
                    for tool_call in current:
                        func_name = tool_call.function.name if hasattr(tool_call, 'function') else "tool"
                        # Dedup by full call signature (name+args), not just name
                        # This allows multiple add_expense calls with different items
                        call_sig = _call_signature(tool_call)
                        if call_sig in seen_calls:
                            continue
                        seen_calls.add(call_sig)
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
                        if func_name in ("get_spending_summary", "generate_report"):
                            resp += "\n[This is read-only data. Do NOT call add_expense or add_income for these amounts.]"
                        messages.append({"role": "user", "content": f"[Result of {func_name}]: {resp}"})
                    if not current:
                        break
                    next_result, messages = chat_turn(groq, messages)
                    if isinstance(next_result, str):
                        next_result = re.sub(r"(?:<function[^>]*>.*?(?:</?function>)?|\{\{.*?\}\})", "", next_result, flags=re.DOTALL).strip()
                        if next_result not in all_responses and next_result:
                            all_responses.append(next_result)
                        break
                    current = next_result
                response_text = all_responses[0] if len(all_responses) == 1 else "\n\n".join(all_responses) if all_responses else "Done."
                if all_responses:
                    await message.answer(response_text + suffix)

        await save_chat(message.from_user.id, text, response_text, int(latency * 1000))
        logger.info("Handled message in %.2fs", latency)
    except Exception as e:
        logger.error("Text handler error for user %s text=%s: %s", message.from_user.id, text[:100], e)
        await message.answer(t(lang, "error"))
