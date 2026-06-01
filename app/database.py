import logging
import random
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_db: Client | None = None


def init_db(url: str, key: str) -> Client:
    global _db
    _db = create_client(url, key)
    logger.info("Supabase connected")
    return _db


def get_db() -> Client:
    if _db is None:
        raise RuntimeError("Supabase not initialized")
    return _db


async def get_user_lang(user_id: int) -> str:
    try:
        resp = get_db().table("users").select("language").eq("id", user_id).execute()
        if resp.data:
            return resp.data[0]["language"]
    except Exception as e:
        logger.warning("Failed to get user lang: %s", e)
    return "en"


async def set_user_lang(user_id: int, lang: str):
    try:
        get_db().table("users").upsert({"id": user_id, "language": lang}, on_conflict="id").execute()
    except Exception as e:
        logger.warning("Failed to set user lang: %s", e)


async def get_user_tz(user_id: int) -> str:
    try:
        resp = get_db().table("users").select("timezone").eq("id", user_id).execute()
        if resp.data and resp.data[0].get("timezone"):
            return resp.data[0]["timezone"]
    except Exception as e:
        logger.warning("Failed to get user tz: %s", e)
    return ""


async def set_user_tz(user_id: int, tz: str):
    try:
        get_db().table("users").upsert({"id": user_id, "timezone": tz}, on_conflict="id").execute()
    except Exception as e:
        logger.warning("Failed to set user tz: %s", e)


async def save_chat(user_id: int, message: str, response: str, latency_ms: int):
    try:
        get_db().table("chats").insert({
            "user_id": user_id,
            "message": message,
            "response": response,
            "latency_ms": latency_ms,
        }).execute()
    except Exception as e:
        logger.warning("Failed to save chat: %s", e)


async def log_event(user_id: int, event_type: str, event_data: dict = None):
    try:
        get_db().table("events").insert({
            "user_id": user_id,
            "event_type": event_type,
            "event_data": event_data or {},
        }).execute()
    except Exception as e:
        logger.warning("Failed to log event: %s", e)


async def add_reminder(user_id: int, message: str, next_run: str):
    try:
        get_db().table("scheduled_tasks").insert({
            "user_id": user_id,
            "job_id": f"remind_{user_id}_{int(datetime.now().timestamp())}",
            "task_type": "reminder",
            "config": {"message": message},
            "next_run": next_run,
            "done": False,
        }).execute()
    except Exception as e:
        logger.warning("Failed to add reminder: %s", e)


async def get_due_reminders() -> list[dict]:
    try:
        now_ts = datetime.now(timezone.utc).isoformat()
        resp = get_db().table("scheduled_tasks").select("*").eq("task_type", "reminder").eq("done", False).lte("next_run", now_ts).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get due reminders: %s", e)
        return []


async def mark_reminder_done(task_id: int):
    try:
        get_db().table("scheduled_tasks").update({"done": True}).eq("id", task_id).execute()
    except Exception as e:
        logger.warning("Failed to mark reminder done: %s", e)


async def get_user_sheet(user_id: int) -> str:
    try:
        resp = get_db().table("users").select("sheet_url").eq("id", user_id).execute()
        if resp.data and resp.data[0].get("sheet_url"):
            return resp.data[0]["sheet_url"]
    except Exception as e:
        logger.warning("Failed to get user sheet: %s", e)
    return ""


async def set_user_sheet(user_id: int, url: str):
    try:
        get_db().table("users").upsert({"id": user_id, "sheet_url": url}, on_conflict="id").execute()
    except Exception as e:
        logger.warning("Failed to set user sheet: %s", e)


async def add_todo(user_id: int, title: str):
    try:
        get_db().table("tasks").insert({
            "user_id": user_id,
            "title": title,
            "done": False,
        }).execute()
    except Exception as e:
        logger.warning("Failed to add todo: %s", e)


async def get_todos(user_id: int) -> list[dict]:
    try:
        resp = get_db().table("tasks").select("*").eq("user_id", user_id).eq("done", False).order("created_at").execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get todos: %s", e)
        return []


async def mark_todo_done(todo_id: int) -> bool:
    try:
        resp = get_db().table("tasks").update({"done": True}).eq("id", todo_id).eq("done", False).execute()
        return len(resp.data) > 0
    except Exception as e:
        logger.warning("Failed to mark todo done: %s", e)
        return False


async def create_pending_payment(user_id: int, service: str, amount: float) -> dict | None:
    for attempt in range(5):
        fraction = random.randint(1, 999)
        unique_amount = round(amount + fraction / 1000000, 6)
        try:
            resp = get_db().table("pending_payments").insert({
                "user_id": user_id,
                "service": service,
                "amount": amount,
                "unique_amount": unique_amount,
                "status": "pending",
            }).execute()
            if resp.data:
                return resp.data[0]
        except Exception as e:
            if "idx_pending_amount" in str(e):
                continue
            logger.warning("Failed to create payment: %s", e)
            return None
    return None


async def get_pending_payments() -> list[dict]:
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        resp = get_db().table("pending_payments").select("*").eq("status", "pending").gte("created_at", cutoff).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get pending payments: %s", e)
        return []


async def expire_old_payments():
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        get_db().table("pending_payments").update({"status": "expired"}).eq("status", "pending").lt("created_at", cutoff).execute()
    except Exception as e:
        logger.warning("Failed to expire payments: %s", e)


async def confirm_payment(payment_id: int, network: str, txid: str):
    try:
        get_db().table("pending_payments").update({
            "status": "confirmed",
            "network": network,
            "txid": txid,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", payment_id).execute()
    except Exception as e:
        logger.warning("Failed to confirm payment: %s", e)


async def is_payment_confirmed(payment_id: int) -> bool:
    try:
        resp = get_db().table("pending_payments").select("status").eq("id", payment_id).single().execute()
        return resp.data and resp.data.get("status") == "confirmed"
    except Exception:
        return False


async def add_movement(user_id: int, location: str, description: str = ""):
    try:
        get_db().table("movements").insert({
            "user_id": user_id,
            "location": location,
            "description": description,
        }).execute()
    except Exception as e:
        logger.warning("Failed to add movement: %s", e)


async def get_movements(user_id: int, limit: int = 20) -> list[dict]:
    try:
        resp = get_db().table("movements").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get movements: %s", e)
        return []


async def get_calendar_events(user_id: int, limit: int = 20) -> list[dict]:
    try:
        resp = get_db().table("events").select("*").eq("user_id", user_id).eq("event_type", "calendar_event").order("created_at", desc=True).limit(limit).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get calendar events: %s", e)
        return []


async def add_expense(user_id: int, description: str, amount: str = "", category: str = ""):
    try:
        get_db().table("expenses").insert({
            "user_id": user_id,
            "description": description,
            "amount": amount,
            "category": category,
        }).execute()
    except Exception as e:
        logger.warning("Failed to add expense: %s", e)


async def get_user_items(user_id: int, category: str | None = None, limit: int = 20) -> list[dict]:
    try:
        q = get_db().table("expenses").select("*").eq("user_id", user_id)
        if category:
            q = q.eq("category", category)
        resp = q.order("created_at", desc=True).limit(limit).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get user items: %s", e)
        return []


async def get_expense_stats(user_id: int) -> dict:
    try:
        resp = get_db().table("expenses").select("amount,description").eq("user_id", user_id).execute()
        if not resp.data:
            return {"total": 0, "count": 0, "categories": {}}
        total = 0
        count = len(resp.data)
        for row in resp.data:
            amt = row.get("amount", "")
            try:
                total += float(amt.replace("$", "").replace("₽", "").replace("€", "").strip())
            except (ValueError, AttributeError):
                pass
        return {"total": round(total, 2), "count": count}
    except Exception as e:
        logger.warning("Failed to get expense stats: %s", e)
        return {"total": 0, "count": 0}


async def has_seen_sheet_offer(user_id: int) -> bool:
    try:
        resp = get_db().table("users").select("has_seen_sheet_offer").eq("id", user_id).execute()
        if resp.data:
            return resp.data[0].get("has_seen_sheet_offer", False)
    except Exception:
        pass
    return False


async def get_unsynced_items(user_id: int) -> list[dict]:
    try:
        resp = get_db().table("expenses").select("id,description,amount,category,created_at").eq("user_id", user_id).eq("synced", False).order("created_at").execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get unsynced items: %s", e)
        return []


async def get_expenses_range(user_id: int, start: str, end: str) -> list[dict]:
    try:
        resp = get_db().table("expenses").select("*").eq("user_id", user_id).gte("created_at", "T".join([start, "00:00:00"])).lte("created_at", "T".join([end, "23:59:59"])).order("created_at").execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get expenses range: %s", e)
        return []


async def mark_items_synced(item_ids: list[int]):
    try:
        get_db().table("expenses").update({"synced": True}).in_("id", item_ids).execute()
    except Exception as e:
        logger.warning("Failed to mark items synced: %s", e)


async def get_digest_config(user_id: int) -> dict:
    try:
        resp = get_db().table("users").select("digest_enabled,digest_time").eq("id", user_id).execute()
        if resp.data:
            return resp.data[0]
    except Exception:
        pass
    return {"digest_enabled": False, "digest_time": "09:00"}


async def set_digest_config(user_id: int, enabled: bool, time: str = "09:00"):
    try:
        get_db().table("users").upsert({"id": user_id, "digest_enabled": enabled, "digest_time": time}, on_conflict="id").execute()
    except Exception as e:
        logger.warning("Failed to set digest config: %s", e)


async def get_digest_users() -> list[dict]:
    try:
        resp = get_db().table("users").select("id,digest_time,timezone").eq("digest_enabled", True).not_.is_("digest_time", "null").execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get digest users: %s", e)
        return []


async def get_yesterday_expenses(user_id: int) -> list[dict]:
    try:
        from datetime import datetime, timezone, timedelta
        start = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00+00:00")
        end = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
        resp = get_db().table("expenses").select("*").eq("user_id", user_id).gte("created_at", start).lt("created_at", end).order("created_at").execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get yesterday expenses: %s", e)
        return []


async def get_today_movements(user_id: int) -> list[dict]:
    try:
        from datetime import datetime, timezone, timedelta
        start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
        resp = get_db().table("movements").select("*").eq("user_id", user_id).gte("created_at", start).order("created_at").execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get today movements: %s", e)
        return []


async def add_recurring_payment(user_id: int, name: str, amount: float, currency: str = "USD", frequency: str = "monthly", day_of_month: int = 1):
    try:
        from datetime import date, timedelta
        today = date.today()
        next_due = today.replace(day=min(day_of_month, 28))
        if next_due <= today:
            if next_due.month == 12:
                next_due = next_due.replace(year=next_due.year + 1, month=1)
            else:
                next_due = next_due.replace(month=next_due.month + 1)
        get_db().table("recurring_payments").insert({
            "user_id": user_id, "name": name, "amount": amount,
            "currency": currency, "frequency": frequency,
            "day_of_month": day_of_month, "next_due": next_due.isoformat(),
        }).execute()
    except Exception as e:
        logger.warning("Failed to add recurring payment: %s", e)


async def get_recurring_payments(user_id: int) -> list[dict]:
    try:
        resp = get_db().table("recurring_payments").select("*").eq("user_id", user_id).eq("active", True).order("next_due").execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get recurring payments: %s", e)
        return []


async def delete_recurring_payment(payment_id: int):
    try:
        get_db().table("recurring_payments").update({"active": False}).eq("id", payment_id).execute()
    except Exception as e:
        logger.warning("Failed to delete recurring payment: %s", e)


async def get_due_recurring_payments() -> list[dict]:
    try:
        from datetime import date
        today = date.today().isoformat()
        resp = get_db().table("recurring_payments").select("*,users!inner(id)").eq("active", True).lte("next_due", today).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get due recurring payments: %s", e)
        return []


async def bump_recurring_payment(payment_id: int):
    try:
        from datetime import date, timedelta
        now = date.today()
        resp = get_db().table("recurring_payments").select("day_of_month,frequency").eq("id", payment_id).single().execute()
        if resp.data:
            day = resp.data.get("day_of_month", 1)
            next_due = now.replace(day=min(day, 28))
            if next_due <= now:
                if next_due.month == 12:
                    next_due = next_due.replace(year=next_due.year + 1, month=1)
                else:
                    next_due = next_due.replace(month=next_due.month + 1)
            get_db().table("recurring_payments").update({"next_due": next_due.isoformat()}).eq("id", payment_id).execute()
    except Exception as e:
        logger.warning("Failed to bump recurring payment: %s", e)


async def get_inactive_users(days: int = 3) -> list[dict]:
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = get_db().table("chats").select("user_id, MAX(created_at) as last_seen").group("user_id").having("MAX(created_at) <", cutoff).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get inactive users: %s", e)
        return []


async def get_candidates_for_reengagement() -> list[dict]:
    try:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc).isoformat()
        # users who have chatted but never got re-engagement, or last got it 7+ days ago
        resp = get_db().table("users").select("id,language,last_reengagement").is_("last_reengagement", "null").or_("last_reengagement.lt." + (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Failed to get re-engagement candidates: %s", e)
        return []


async def mark_reengagement_sent(user_id: int):
    try:
        from datetime import datetime, timezone
        get_db().table("users").upsert({"id": user_id, "last_reengagement": datetime.now(timezone.utc).isoformat()}, on_conflict="id").execute()
    except Exception as e:
        logger.warning("Failed to mark re-engagement: %s", e)


async def mark_seen_sheet_offer(user_id: int):
    try:
        get_db().table("users").upsert({"id": user_id, "has_seen_sheet_offer": True}, on_conflict="id").execute()
    except Exception as e:
        logger.warning("Failed to mark sheet offer: %s", e)
