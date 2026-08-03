import sys, asyncio, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from app import handlers

async def fake_get_currency(uid):
    return ""
async def fake_add_expense(uid, desc, amount, kind, currency=None):
    print(f"    SAVE: desc={desc!r} amount={amount} cur={currency}")
    return True

handlers.get_user_currency = fake_get_currency
handlers.add_expense = fake_add_expense

samples = [
    ("en",  "coffee 80 baht and lunch 15 dollars"),
    ("en",  "1,200.50 dollars for rent"),
    ("ru",  "кофе 80 бат и обед 1500 рублей"),
    ("ru",  "650 000 донгов на жильё и 150 000 донгов на еду"),
    ("es",  "café 80 baht y comida 15 dólares"),
    ("es",  "hotel 1.200,50 euros"),
    ("fr",  "café 80 baht et déjeuner 15 euros"),
    ("de",  "Kaffee 80 Baht und Mittagessen 15 Euro"),
    ("pt",  "café 80 baht e almoço 15 reais"),
    ("zh",  "咖啡 30 元"),
    ("ar",  "قهوة 50 درهم"),
    ("hi",  "चाय 100 रुपये"),
    ("ja",  "コーヒー 500 円"),
    ("vi",  "cà phê 80 nghìn đồng"),
]

for lang, text in samples:
    print(f"[{lang}] {text}")
    asyncio.run(handlers._try_save_expenses_fallback(text, 354703083))
