import logging
import json
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

_gc: gspread.Client | None = None
_service_email: str = ""


def init_sheets(credentials_json: str):
    global _gc, _service_email
    raw = credentials_json.strip().strip("'\"")
    if not raw:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS is empty")
    creds_dict = json.loads(raw)
    _service_email = creds_dict["client_email"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    _gc = gspread.authorize(creds)
    logger.info("Google Sheets initialized as %s", _service_email)


def get_service_email() -> str:
    return _service_email


def is_ready() -> bool:
    return _gc is not None


def read_sheet(sheet_url: str, range_name: str = "A1:Z100") -> list[list[str]]:
    if not _gc:
        raise RuntimeError("Sheets not initialized")
    sheet = _gc.open_by_url(sheet_url).sheet1
    if range_name:
        return sheet.get(range_name)
    return sheet.get_all_values()


def write_sheet(sheet_url: str, values: list[list], range_name: str = "A1"):
    if not _gc:
        raise RuntimeError("Sheets not initialized")
    sheet = _gc.open_by_url(sheet_url).sheet1
    sheet.update(range_name, values)


def append_row(sheet_url: str, values: list):
    if not _gc:
        raise RuntimeError("Sheets not initialized")
    sheet = _gc.open_by_url(sheet_url).sheet1
    sheet.append_row(values)
