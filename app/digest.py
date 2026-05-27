import logging
from datetime import datetime, timezone, timedelta

from app.database import get_yesterday_expenses, get_today_movements, get_todos, get_user_tz
from app.timezone_utils import format_dual_time, MSK
from app.anomaly import detect_anomalies

logger = logging.getLogger(__name__)


def _make_utc_dt(hour: int, tz_str: str) -> datetime:
    try:
        import zoneinfo
        local = zoneinfo.ZoneInfo(tz_str)
        now_local = datetime.now(local)
        target = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
        return target.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


async def generate_digest(user_id: int, lang: str = "en") -> str:
    tz = await get_user_tz(user_id) or "UTC"
    expenses = await get_yesterday_expenses(user_id)
    movements = await get_today_movements(user_id)
    todos = await get_todos(user_id)

    lines = []
    lines.append("📋 <b>Daily Digest</b>")

    # expenses
    total = 0
    exp_lines = []
    for e in expenses:
        amt = e.get("amount", "")
        desc = e.get("description", "")
        try:
            total += float(amt.replace("$", "").replace("₽", "").replace("€", "").strip())
        except (ValueError, AttributeError):
            pass
        exp_lines.append(f"  {desc} — {amt}" if amt else f"  {desc}")
    if exp_lines:
        currency = "₽" if lang == "ru" else "$"
        lines.append(f"\n💰 <b>{'Yesterday' if lang != 'ru' else 'Вчера'}:</b> {total:.0f}{currency}")
        lines.extend(exp_lines[:5])
    else:
        if lang == "ru":
            lines.append(f"\n💰 <b>Вчера:</b> расходов нет")
        else:
            lines.append(f"\n💰 <b>Yesterday:</b> no expenses")

    # anomalies
    try:
        anomalies = await detect_anomalies(user_id, lang)
        if anomalies:
            lines.append(f"\n🔍 <b>{'Anomalies' if lang != 'ru' else 'Аномалии'}:</b>")
            lines.extend(f"  {a}" for a in anomalies[:3])
    except Exception:
        pass

    # movements
    if movements:
        if lang == "ru":
            lines.append(f"\n📍 <b>Сегодня:</b>")
        else:
            lines.append(f"\n📍 <b>Today:</b>")
        for m in movements[:5]:
            loc = m.get("location", "")
            dt_raw = m.get("created_at", "")
            desc = m.get("description", "")
            t = ""
            if dt_raw:
                try:
                    dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
                    t = format_dual_time(dt, tz, "%H:%M")
                except Exception:
                    pass
            note = f" — {desc}" if desc else ""
            lines.append(f"  {loc} ({t}){note}")
    else:
        if lang == "ru":
            lines.append(f"\n📍 <b>Сегодня:</b> перемещений нет")
        else:
            lines.append(f"\n📍 <b>Today:</b> no movements")

    # todos
    if todos:
        if lang == "ru":
            lines.append(f"\n✅ <b>Задачи ({len(todos)}):</b>")
        else:
            lines.append(f"\n✅ <b>Todos ({len(todos)}):</b>")
        for t in todos[:5]:
            title = t.get("title", "")
            lines.append(f"  ☐ {title}")
    else:
        if lang == "ru":
            lines.append(f"\n✅ <b>Задачи:</b> всё выполнено!")
        else:
            lines.append(f"\n✅ <b>Todos:</b> all done!")

    # time
    now = format_dual_time(user_tz=tz)
    if lang == "ru":
        lines.append(f"\n🕐 {now}")
    else:
        lines.append(f"\n🕐 {now}")

    return "\n".join(lines)


def is_digest_due(user_tz: str | None, digest_time: str) -> bool:
    if not user_tz or user_tz == "UTC":
        return False
    try:
        import zoneinfo
        local = zoneinfo.ZoneInfo(user_tz)
        now_local = datetime.now(local)
        parts = digest_time.split(":")
        target_hour = int(parts[0])
        target_min = int(parts[1]) if len(parts) > 1 else 0
        diff = (now_local.hour - target_hour) * 60 + (now_local.minute - target_min)
        return 0 <= diff < 5
    except Exception:
        return False
