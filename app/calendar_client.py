import json
import logging
from datetime import datetime, timedelta

from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request as AuthRequest
import httpx

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
API_BASE = "https://www.googleapis.com/calendar/v3"

_creds: Credentials | None = None


def init_calendar(credentials_json: str = ""):
    global _creds
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


def _get_token() -> str:
    if not _creds:
        raise RuntimeError("Calendar not initialized")
    _creds.refresh(AuthRequest())
    return _creds.token


def is_ready() -> bool:
    return _creds is not None


def create_event(summary: str, date: str, time: str = "10:00", duration_min: int = 60) -> str:
    token = _get_token()
    dt_start = datetime.fromisoformat(f"{date}T{time}:00")
    dt_end = dt_start + timedelta(minutes=duration_min)
    body = {
        "summary": summary,
        "start": {"dateTime": dt_start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": dt_end.isoformat(), "timeZone": "UTC"},
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = httpx.post(f"{API_BASE}/calendars/primary/events", headers=headers, json=body)
    r.raise_for_status()
    data = r.json()
    link = data.get("htmlLink", "")
    logger.info("Created event: %s", link)
    return link


def list_events(max_results: int = 10) -> list[dict]:
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"maxResults": max_results, "orderBy": "startTime", "singleEvents": "true"}
    r = httpx.get(f"{API_BASE}/calendars/primary/events", headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("items", [])
