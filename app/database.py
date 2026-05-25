import logging
from datetime import datetime, timezone
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
