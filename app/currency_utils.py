"""Currency detection and conversion utilities for Sasha bot.

Handles:
- Extracting currency from text (₽, $, €, ฿, etc.)
- Currency symbols ↔ ISO codes mapping
- Exchange rate fetching (cached for 1 hour)
- Amount formatting with currency symbol
"""

import re
import time
import logging
import urllib.request
import json as _json

logger = logging.getLogger(__name__)

# ─── Symbol → ISO code mapping ──────────────────────────────
CURRENCY_SYMBOLS = {
    # Symbols that appear in text
    "₽": "RUB", "rub": "RUB", "руб": "RUB", "рублей": "RUB",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD", "доллар": "USD", "долларов": "USD",
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "евро": "EUR",
    "฿": "THB", "thb": "THB", "бат": "THB", "baht": "THB", "bath": "THB",
    "£": "GBP", "gbp": "GBP", "pound": "GBP", "фунт": "GBP", "фунтов": "GBP",
    "¥": "JPY", "jpy": "JPY", "yen": "JPY", "иена": "JPY",
    "₴": "UAH", "uah": "UAH", "гривн": "UAH",
    "₸": "KZT", "kzt": "KZT", "тенге": "KZT",
    "₮": "MNT", "mnt": "MNT", "тугрик": "MNT",
    "₩": "KRW", "krw": "KRW",
    "AED": "AED", "د.إ": "AED", "дирхам": "AED",
    "CNY": "CNY", "юань": "CNY", "yuan": "CNY",
    "INR": "INR", "₹": "INR", "рупи": "INR",
    "VND": "VND", "₫": "VND", "донг": "VND",
    "SGD": "SGD",
    "MYR": "MYR", "рингит": "MYR",
    "PHP": "PHP", "песо": "PHP",
    "TRY": "TRY", "лир": "TRY", "lira": "TRY",
    "CHF": "CHF", "франк": "CHF",
    "BRL": "BRL", "real": "BRL", "reais": "BRL",
    "BTC": "BTC", "биткоин": "BTC",
    "USDT": "USDT", "USDC": "USDC",
}

# ISO code → display symbol
CURRENCY_DISPLAY = {
    "RUB": "₽", "USD": "$", "EUR": "€", "THB": "฿", "GBP": "£",
    "JPY": "¥", "UAH": "₴", "KZT": "₸", "KRW": "₩", "AED": "د.إ",
    "CNY": "¥", "INR": "₹", "VND": "₫", "SGD": "S$", "MYR": "RM",
    "PHP": "₱", "TRY": "₺", "CHF": "CHF", "BRL": "R$",
    "BTC": "₿", "USDT": "₮", "USDC": "USD",
}

# Patterns for extracting currency from text
_CURRENCY_PATTERNS = [
    # Currency code after number: "1800 THB", "50 USD"
    (re.compile(r'(?:^|\s)(?:USD|EUR|THB|RUB|GBP|JPY|UAH|KZT|KRW|AED|CNY|INR|VND|SGD|MYR|PHP|TRY|CHF|BTC|USDT|USDC)\b', re.I), None),
    # Symbol before number: "$50", "€100"
    (re.compile(r'[$€₽฿£¥₴₸₩₹₫₱₺₿₮]\s*[\d]', re.U), None),
    # Number then symbol: "50$", "100₽"
    (re.compile(r'[\d]\s*[$€₽฿£¥₴₸₩₹₫₱₺₿₮]', re.U), None),
    # Russian words: "руб", "бат", "доллар"
    (re.compile(r'\b(?:руб|рубл|бат|доллар|евро|тенге|гривн|юань|лир|франк|рупи|донг|песо|дирхам|биткоин)\b', re.I), None),
    # English words: "baht", "dollars", "euros"
    (re.compile(r'\b(?:baht|bath|dollars?|euros?|pounds?|yen|yuan|won|rupees?|dong|peso|dirham|franc|lira|bitcoin)\b', re.I), None),
]


def extract_currency(text: str) -> str:
    """Extract ISO currency code from text like '1,800 THB' or 'кофе 300₽'.

    Returns uppercase ISO code (e.g., 'THB', 'RUB', 'USD') or empty string.
    """
    if not text:
        return ""

    text_lower = text.lower()

    # Check each symbol mapping
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol.lower() in text_lower:
            return code

    return ""


def currency_symbol(code: str) -> str:
    """Get display symbol for currency code. 'THB' → '฿', 'RUB' → '₽'"""
    if not code:
        return ""
    return CURRENCY_DISPLAY.get(code.upper(), code.upper())


def format_amount_with_currency(amount: str, currency: str = "") -> str:
    """Format amount with currency symbol: '1800' + 'THB' → '1,800 ฿'"""
    if not amount:
        return ""
    sym = currency_symbol(currency)
    if sym and sym not in amount:
        return f"{amount} {sym}"
    return amount


# ─── Exchange rates (cached) ────────────────────────────────

_rates_cache: dict[str, dict[str, float]] = {}
_rates_cache_time: float = 0.0
_RATES_TTL: float = 3600.0  # 1 hour


def _fetch_rates(base: str = "USD") -> dict[str, float]:
    """Fetch exchange rates from open.er-api.com (free, no key needed)."""
    global _rates_cache, _rates_cache_time
    now = time.time()
    if now - _rates_cache_time < _RATES_TTL and base in _rates_cache:
        return _rates_cache[base]

    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = _json.loads(resp.read())
        if data.get("result") == "success":
            rates = data.get("rates", {})
            _rates_cache[base] = rates
            _rates_cache_time = now
            return rates
    except Exception as e:
        logger.warning("Failed to fetch exchange rates: %s", e)
    return {}


def convert_currency(amount: float, from_cur: str, to_cur: str) -> float | None:
    """Convert amount from one currency to another.

    Returns converted amount or None if rates unavailable.
    """
    from_cur = from_cur.upper()
    to_cur = to_cur.upper()
    if from_cur == to_cur:
        return amount

    # Try direct conversion via USD rates
    rates = _fetch_rates("USD")
    if not rates:
        return None

    from_rate = rates.get(from_cur)
    to_rate = rates.get(to_cur)
    if not from_rate or not to_rate:
        return None

    # Convert: amount → USD → target
    usd_amount = amount / from_rate
    return usd_amount * to_rate


def get_user_currency_fallback(tz: str = "", location: str = "") -> str:
    """Guess user's default currency from timezone or location."""
    from app.intents import _country_from_location
    if location:
        cur = _country_from_location(location)
        if cur:
            return cur
    if tz:
        tz_lower = tz.lower()
        if "moscow" in tz_lower or "europe" in tz_lower:
            return "RUB"
        if "bangkok" in tz_lower or "asia/bangkok" in tz_lower:
            return "THB"
        if "new_york" in tz_lower or "chicago" in tz_lower or "los_angeles" in tz_lower:
            return "USD"
        if "london" in tz_lower:
            return "GBP"
        if "berlin" in tz_lower or "paris" in tz_lower or "europe" in tz_lower:
            return "EUR"
    return "USD"
