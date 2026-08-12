"""Currency detection, conversion, and formatting utilities."""

import re
import time
import logging
import urllib.request
import json

logger = logging.getLogger(__name__)

# ─── Currency detection from text ─────────────────────

CURRENCY_PATTERNS = [
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:бат|bath|baths|฿|thb)", re.I), "THB"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:₽|руб|rub|ruble|rubles)", re.I), "RUB"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:\$|usd|dollar|dollars|доллар|долларов)", re.I), "USD"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:€|eur|euro|евро)", re.I), "EUR"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:£|gbp|pound|фунт|фунтов)", re.I), "GBP"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:¥|jpy|yen|иен)", re.I), "JPY"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:元|cny|rmb|юан)", re.I), "CNY"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:₺|try|lira|лир)", re.I), "TRY"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:₴|uah|гривн)", re.I), "UAH"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:₩|krw|won)", re.I), "KRW"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:₫|vnd|донг|донгов|dong)", re.I), "VND"),
    (re.compile(r"(?:^|\s)(\d+[\.,]?\d*)\s*(?:R\$|brl|real|reais)", re.I), "BRL"),
]

# Currency symbols for display
CURRENCY_SYMBOLS = {
    "THB": "฿", "RUB": "₽", "USD": "$", "EUR": "€", "GBP": "£",
    "JPY": "¥", "CNY": "¥", "TRY": "₺", "UAH": "₴", "KRW": "₩",
    "SGD": "S$", "INR": "₹", "AUD": "A$", "CAD": "C$", "CHF": "CHF",
    "VND": "₫", "IDR": "Rp", "MYR": "RM", "PHP": "₱", "BRL": "R$",
    "AED": "د.إ", "HKD": "HK$", "ILS": "₪",
}

COUNTRY_TO_CURRENCY = {
    "thailand": "THB", "таиланд": "THB", "тайланд": "THB", "bangkok": "THB", "phuket": "THB", "pattaya": "THB",
    "russia": "RUB", "россия": "RUB", "moscow": "RUB", "москва": "RUB", "spb": "RUB",
    "usa": "USD", "united states": "USD", "new york": "USD", "los angeles": "USD",
    "europe": "EUR", "germany": "EUR", "france": "EUR", "spain": "EUR", "italy": "EUR",
    "berlin": "EUR", "paris": "EUR", "madrid": "EUR", "rome": "EUR",
    "uk": "GBP", "united kingdom": "GBP", "london": "GBP", "england": "GBP",
    "japan": "JPY", "tokyo": "JPY", "osaka": "JPY",
    "china": "CNY", "beijing": "CNY", "shanghai": "CNY",
    "india": "INR", "mumbai": "INR", "delhi": "INR",
    "singapore": "SGD",
    "vietnam": "VND", "hanoi": "VND", "ho chi minh": "VND",
    "indonesia": "IDR", "bali": "IDR", "jakarta": "IDR",
    "malaysia": "MYR", "kuala lumpur": "MYR",
    "philippines": "PHP", "manila": "PHP",
    "south korea": "KRW", "seoul": "KRW",
    "australia": "AUD", "sydney": "AUD", "melbourne": "AUD",
    "canada": "CAD", "toronto": "CAD", "vancouver": "CAD",
    "brazil": "BRL", "rio": "BRL",
    "turkey": "TRY", "istanbul": "TRY",
    "uae": "AED", "dubai": "AED",
    "switzerland": "CHF", "zurich": "CHF",
    "hong kong": "HKD",
    "israel": "ILS", "tel aviv": "ILS",
}


def detect_currency_from_text(text: str) -> str:
    """Detect currency from text like '1,800 THB' or 'кофе 300₽'.
    Returns 3-letter currency code or empty string.
    """
    for pattern, cur in CURRENCY_PATTERNS:
        if pattern.search(text):
            return cur
    return ""


def currency_from_location(location: str) -> str | None:
    """Get currency code from a location string like 'Bangkok' or 'Москва'."""
    loc = location.lower().strip()
    for key, cur in sorted(COUNTRY_TO_CURRENCY.items(), key=lambda x: -len(x[0])):
        if key in loc:
            return cur
    return None


def currency_symbol(code: str) -> str:
    """Get display symbol for currency code: THB → ฿, RUB → ₽"""
    return CURRENCY_SYMBOLS.get(code.upper(), code)


# ─── Exchange rates ───────────────────────────────────

_RATES_CACHE: dict[str, float] = {}
_RATES_CACHE_TIME = 0.0


def get_exchange_rate(from_cur: str, to_cur: str) -> float:
    """Get exchange rate from one currency to another.
    Always converts through USD. Caches for 1 hour. Returns 1.0 if can't fetch.
    """
    from_cur = from_cur.upper()
    to_cur = to_cur.upper()
    if from_cur == to_cur:
        return 1.0
    global _RATES_CACHE, _RATES_CACHE_TIME
    now_ts = time.time()
    if now_ts - _RATES_CACHE_TIME > 3600:
        try:
            url = "https://open.er-api.com/v6/latest/USD"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            _RATES_CACHE = data.get("rates", {})
            _RATES_CACHE_TIME = now_ts
        except Exception as e:
            logger.warning("Failed to fetch exchange rates: %s", e)
    from_rate = 1.0 if from_cur == "USD" else _RATES_CACHE.get(from_cur)
    to_rate = 1.0 if to_cur == "USD" else _RATES_CACHE.get(to_cur)
    if from_rate and to_rate:
        return to_rate / from_rate
    return 1.0


def convert_amount(amount: float, from_cur: str, to_cur: str) -> float:
    """Convert amount from one currency to another."""
    if from_cur == to_cur or not from_cur or not to_cur:
        return amount
    rate = get_exchange_rate(from_cur, to_cur)
    return amount * rate
