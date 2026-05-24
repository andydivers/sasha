import logging
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
