import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request as AuthRequest
import httpx

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
API_BASE = "https://www.googleapis.com/calendar/v3"

_creds: Credentials | None = None
_calendar_id: str = "primary"


def init_calendar(credentials_json: str = ""):
    global _creds, _calendar_id
    raw = credentials_json.strip().strip("'\"") if credentials_json else ""
    if not raw:
        path = "/etc/secrets/google_sheets_credentials.json"
        try:
            with open(path) as f:
                raw = f.read().strip()
        except FileNotFoundError:
            raise ValueError("No credentials for calendar")
    creds_dict = json.loads(raw)
    _creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

    token = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    cal_list = httpx.get(f"{API_BASE}/users/me/calendarList", headers=headers).json()
    for cal in cal_list.get("items", []):
        if cal.get("summary") == "Sasha Bot":
            _calendar_id = cal["id"]
            logger.info("Found existing Sasha Bot calendar: %s", _calendar_id)
            return
    body = {"summary": "Sasha Bot", "description": "Events created by Sasha Telegram bot"}
    r = httpx.post(f"{API_BASE}/calendars", headers=headers, json=body)
    r.raise_for_status()
    _calendar_id = r.json()["id"]
    acl_body = {"role": "reader", "scope": {"type": "default"}}
    httpx.post(f"{API_BASE}/calendars/{_calendar_id}/acl", headers=headers, json=acl_body)
    cal_link = f"https://calendar.google.com/calendar/u/0?cid={_calendar_id}"
    logger.info("Created Sasha Bot calendar: %s", cal_link)


def _get_token() -> str:
    if not _creds:
        raise RuntimeError("Calendar not initialized")
    _creds.refresh(AuthRequest())
    return _creds.token


def is_ready() -> bool:
    return _creds is not None


def create_event(summary: str, date: str, time: str = "10:00", tz: str = "UTC", duration_min: int = 60) -> str:
    token = _get_token()
    local_str = f"{date}T{time}:00"
    try:
        local_tz = ZoneInfo(tz)
    except (KeyError, TypeError):
        local_tz = timezone.utc
    local_dt = datetime.fromisoformat(local_str).replace(tzinfo=local_tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    dt_end = utc_dt + timedelta(minutes=duration_min)
    body = {
        "summary": summary,
        "start": {"dateTime": utc_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": dt_end.isoformat(), "timeZone": "UTC"},
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = httpx.post(f"{API_BASE}/calendars/{_calendar_id}/events", headers=headers, json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"Calendar API {r.status_code}: {r.text}")
    data = r.json()
    link = data.get("htmlLink", "")
    logger.info("Created event: %s", link)
    return link


def get_calendar_link() -> str:
    return f"https://calendar.google.com/calendar/u/0?cid={_calendar_id}"


def get_calendar_id() -> str:
    return _calendar_id


def list_events(max_results: int = 10) -> list[dict]:
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "maxResults": max_results,
        "orderBy": "startTime",
        "singleEvents": "true",
        "timeMin": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
    }
    r = httpx.get(f"{API_BASE}/calendars/{_calendar_id}/events", headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("items", [])


def delete_event(event_id: str) -> None:
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    r = httpx.delete(f"{API_BASE}/calendars/{_calendar_id}/events/{event_id}", headers=headers)
    if r.status_code >= 400:
        raise RuntimeError(f"Calendar API {r.status_code}: {r.text}")
