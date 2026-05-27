import logging
from datetime import datetime, timezone, timedelta

from app.database import get_expenses_range

logger = logging.getLogger(__name__)


def _parse_amount(amt: str) -> float:
    try:
        return float(amt.replace("$", "").replace("₽", "").replace("€", "").replace(",", ".").strip())
    except (ValueError, AttributeError):
        return 0.0


async def detect_anomalies(user_id: int, lang: str = "en") -> list[str]:
    today = datetime.now(timezone.utc)
    week1_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    week1_end = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    week2_start = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    week2_end = (today - timedelta(days=8)).strftime("%Y-%m-%d")

    recent = await get_expenses_range(user_id, week1_start, week1_end)
    previous = await get_expenses_range(user_id, week2_start, week2_end)

    alerts = []

    # total comparison
    recent_total = sum(_parse_amount(e.get("amount", "")) for e in recent)
    prev_total = sum(_parse_amount(e.get("amount", "")) for e in previous)
    if prev_total > 0 and recent_total > prev_total * 1.5:
        pct = int((recent_total / prev_total - 1) * 100)
        if lang == "ru":
            alerts.append(f"📈 Расходы за последнюю неделю выросли на <b>{pct}%</b> (было {prev_total:.0f}₽, стало {recent_total:.0f}₽)")
        else:
            alerts.append(f"📈 Spending last week up <b>{pct}%</b> ({prev_total:.0f} vs {recent_total:.0f})")

    # large individual transactions
    all_recent = []
    for e in recent + previous:
        amt = _parse_amount(e.get("amount", ""))
        if amt > 0:
            all_recent.append(amt)
    if all_recent:
        avg = sum(all_recent) / len(all_recent)
        for e in recent:
            amt = _parse_amount(e.get("amount", ""))
            if amt > avg * 2.5 and amt > 20:
                desc = e.get("description", "")
                currency = "₽" if lang == "ru" else "$"
                if lang == "ru":
                    alerts.append(f"⚠️ Крупная трата: «{desc}» — {amt:.0f}{currency} (средняя {avg:.0f}{currency})")
                else:
                    alerts.append(f"⚠️ Large expense: «{desc}» — {amt:.0f}{currency} (avg {avg:.0f}{currency})")

    # unusual category
    cat_count: dict[str, int] = {}
    for e in recent:
        cat = e.get("category", "") or "uncategorized"
        cat_count[cat] = cat_count.get(cat, 0) + 1
    prev_cat_count: dict[str, int] = {}
    for e in previous:
        cat = e.get("category", "") or "uncategorized"
        prev_cat_count[cat] = prev_cat_count.get(cat, 0) + 1
    new_cats = set(cat_count.keys()) - set(prev_cat_count.keys())
    for cat in new_cats:
        label = {"expense": "💰 expense", "note": "📝 note"}.get(cat, cat)
        count = cat_count[cat]
        if lang == "ru":
            alerts.append(f"🆕 Новая категория: {label} ({count} записей)")
        else:
            alerts.append(f"🆕 New category: {label} ({count} items)")

    return alerts
