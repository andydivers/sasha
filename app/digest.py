import logging
from datetime import datetime, timezone, timedelta

from app.database import get_yesterday_expenses, get_today_movements, get_todos, get_user_tz
from app.timezone_utils import format_dual_time, MSK
from app.anomaly import detect_anomalies
from app.database import get_recurring_payments

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

    # recurring payments due this week
    try:
        recurring = await get_recurring_payments(user_id)
        due_soon = [p for p in recurring if p.get("next_due") and p["next_due"][:10] <= (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")]
        if due_soon:
            if lang == "ru":
                lines.append(f"\n🔄 <b>Скоро спишут:</b>")
            else:
                lines.append(f"\n🔄 <b>Due soon:</b>")
            for p in due_soon:
                amt = p.get("amount", 0)
                cur = p.get("currency", "USD")
                name = p.get("name", "")
                due = p.get("next_due", "")[:10]
                lines.append(f"  {name} — {amt:.0f} {cur} ({due})")
    except Exception:
        pass

    # time
    now = format_dual_time(user_tz=tz)
    lines.append(f"\n🕐 {now}")

    # voice prompt
    voice_prompts = {
        "ru": "\n\n🎤 <b>Нажми микрофон и скажи:</b>\n«кофе 300₽» или «я на работе» или «всё ок»\n\nЯ запишу.",
        "en": "\n\n🎤 <b>Tap the mic and say:</b>\n\"coffee $5\" or \"at work\" or \"all good\"\n\nI'll log it.",
        "es": "\n\n🎤 <b>Toca el micrófono y di:</b>\n\"café $5\" o \"en el trabajo\" o \"todo bien\"\n\nLo registraré.",
        "fr": "\n\n🎤 <b>Appuie sur le micro et dis :</b>\n\"café 5€\" ou \"au travail\" ou \"tout va bien\"\n\nJe note.",
        "zh": "\n\n🎤 <b>按下麦克风说：</b>\n“咖啡5美元”或“在工作”或“都好”\n\n我会记录。",
        "ar": "\n\n🎤 <b>اضغط على الميكروفون وقل:</b>\n«قهوة 5 دولارات» أو «في العمل» أو «كل شيء بخير»\n\nسأسجله.",
        "pt": "\n\n🎤 <b>Aperte o mic e diga:</b>\n\"café $5\" ou \"no trabalho\" ou \"tudo bem\"\n\nVou registrar.",
        "de": "\n\n🎤 <b>Tipp aufs Mikro und sag:</b>\n\"Kaffee 5€\" oder \"bei der Arbeit\" oder \"alles gut\"\n\nIch notiere es.",
        "hi": "\n\n🎤 <b>माइक दबाएँ और कहें:</b>\n\"कॉफ़ी ₹400\" या \"काम पर\" या \"सब ठीक\"\n\nमैं लिख लूँगा।",
        "ja": "\n\n🎤 <b>マイクを押して言って：</b>\n「コーヒー5ドル」または「仕事中」または「大丈夫」\n\n記録します。",
    }
    lines.append(voice_prompts.get(lang, voice_prompts["en"]))

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
