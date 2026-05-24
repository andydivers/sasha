import logging

from groq import Groq

logger = logging.getLogger(__name__)


async def handle_tool_call(tool_call) -> str:
    import json

    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    handlers = {
        "analyze_screenshot": _handle_analyze_screenshot,
        "manage_sheets": _handle_manage_sheets,
        "create_event": _handle_create_event,
        "generate_report": _handle_generate_report,
    }

    handler = handlers.get(name)
    if handler:
        return handler(args)
    return f"I don't know how to handle {name} yet."


def _handle_analyze_screenshot(args: dict) -> str:
    query = args.get("query", "")
    return (
        f"Got it! I'll analyze that screenshot for you. "
        f"I can look for: {query if query else 'everything in the image'}. "
        f"Send me the image and I'll process it."
    )


def _handle_manage_sheets(args: dict) -> str:
    action = args.get("action", "read")
    description = args.get("description", "")
    if action == "write":
        return (
            f"Sure! I'll write to your Google Sheet: {description}. "
            f"Connecting to Google Sheets now (Day 5 will add full integration)."
        )
    return (
        f"Let me check your spreadsheet for: {description}. "
        f"Reading from Google Sheets (coming in Day 5)."
    )


def _handle_create_event(args: dict) -> str:
    summary = args.get("summary", "Event")
    date = args.get("date", "not specified")
    time = args.get("time", "not specified")
    return (
        f"Calendar event created: <b>{summary}</b>\n"
        f"Date: {date}\n"
        f"Time: {time}\n\n"
        f"(Full Google Calendar integration comes Day 6)"
    )


def _handle_generate_report(args: dict) -> str:
    fmt = args.get("format", "pdf")
    topic = args.get("topic", "")
    return (
        f"Generating <b>{fmt.upper()}</b> report on: {topic}\n"
        f"Your report will be ready shortly (full implementation Day 8)."
    )
