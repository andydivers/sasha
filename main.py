import asyncio
import json
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from aiogram.types import Update

from app.config import Config
from app.bot import create_bot, create_dispatcher
from app.database import init_db, get_due_reminders, mark_reminder_done, get_pending_payments, confirm_payment, is_payment_confirmed, expire_old_payments
from app.sheets_client import init_sheets, is_ready as sheets_ready
from app.calendar_client import init_calendar, is_ready as calendar_ready
from app.crypto_client import fetch_incoming_usdc_transfers
from app.digest import is_digest_due
from app.database import get_digest_users, get_user_lang, get_due_recurring_payments, bump_recurring_payment, get_candidates_for_reengagement, mark_reengagement_sent
from app.reengagement import get_reengagement_message
from app.handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

config = Config()
config.validate()

bot = create_bot(config)
dp = create_dispatcher()
dp.include_router(router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.supabase_url and config.supabase_key:
        init_db(config.supabase_url, config.supabase_key)
    if config.google_sheets_creds:
        try:
            init_sheets(config.google_sheets_creds)
        except Exception as e:
            logger.warning("Sheets init from env var failed: %s", e)
    if not sheets_ready():
        try:
            init_sheets()
            logger.info("Sheets initialized from secret file")
        except Exception as e:
            logger.warning("Sheets init from secret file also failed: %s", e)
    if not calendar_ready():
        try:
            init_calendar()
            logger.info("Calendar initialized")
        except Exception as e:
            logger.warning("Calendar init failed: %s", e)
    try:
        dashboard_url = (config.webhook_url.replace("/webhook", "/dashboard") if config.webhook_url else "https://sasha-dbgw.onrender.com/dashboard")
        from aiogram.types import MenuButtonWebApp, WebAppInfo
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="📊 Sasha", web_app=WebAppInfo(url=dashboard_url)))
        logger.info("Menu button set globally")
    except Exception as e:
        logger.warning("Failed to set global menu button: %s", e)

    webhook_url = config.webhook_url
    if webhook_url:
        await bot.set_webhook(url=webhook_url)
        logger.info("Webhook set to %s", webhook_url)

    async def check_reminders():
        while True:
            try:
                reminders = await get_due_reminders()
                for r in reminders:
                    msg = r["config"].get("message", "Reminder!")
                    try:
                        await bot.send_message(chat_id=r["user_id"], text=f"⏰ <b>Reminder:</b> {msg}")
                        await mark_reminder_done(r["id"])
                    except Exception as e:
                        logger.warning("Failed to send reminder to %s: %s", r["user_id"], e)
            except Exception as e:
                logger.warning("Reminder check error: %s", e)
            await asyncio.sleep(30)

    async def check_payments():
        seen_txids: set[str] = set()
        notified_ids: set[int] = set()
        while True:
            await asyncio.sleep(60)
            if not config.etherscan_api_key:
                continue
            try:
                await expire_old_payments()
                pending = await get_pending_payments()
                if not pending:
                    continue
                transfers = fetch_incoming_usdc_transfers(config.usdc_address, config.etherscan_api_key)
                for tx in transfers:
                    if tx["txid"] in seen_txids:
                        continue
                    seen_txids.add(tx["txid"])
                    if len(seen_txids) > 10000:
                        seen_txids.clear()
                    confirmed_this_tx = False
                    for p in pending:
                        if p["id"] in notified_ids:
                            continue
                        if await is_payment_confirmed(p["id"]):
                            notified_ids.add(p["id"])
                            continue
                        if abs(tx["value"] - p["unique_amount"]) < 0.000001:
                            notified_ids.add(p["id"])
                            if len(notified_ids) > 10000:
                                notified_ids.clear()
                            await confirm_payment(p["id"], tx["network"], tx["txid"])
                            await bot.send_message(
                                chat_id=p["user_id"],
                                text=(
                                    f"✅ <b>Payment confirmed!</b>\n"
                                    f"Service: {p['service']}\n"
                                    f"Amount: {tx['value']} USDC\n"
                                    f"Network: {tx['network']}"
                                ),
                            )
                            logger.info("Payment %s confirmed for user %s", p["id"], p["user_id"])
                            confirmed_this_tx = True
                            break
                    if confirmed_this_tx:
                        break
            except Exception as e:
                logger.warning("Payment check error: %s", e)

    async def check_digests():
        sent_today: set[int] = set()
        last_reset_day = 0
        while True:
            await asyncio.sleep(180)
            # Reset sent_today once per day (at midnight UTC)
            today_day = datetime.now(timezone.utc).day
            if today_day != last_reset_day:
                sent_today.clear()
                last_reset_day = today_day
            try:
                users = await get_digest_users()
                for u in users:
                    uid = u["id"]
                    if uid in sent_today:
                        continue
                    tz = u.get("timezone", "")
                    dt = u.get("digest_time", "09:00")
                    if is_digest_due(tz, dt):
                        from app.digest import generate_digest
                        lang = await get_user_lang(uid) or "en"
                        text = await generate_digest(uid, lang)
                        try:
                            msg = await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
                            await bot.pin_chat_message(chat_id=uid, message_id=msg.message_id)
                            sent_today.add(uid)
                            logger.info("Digest sent to user %s", uid)
                        except Exception as e:
                            logger.warning("Failed to send digest to %s: %s", uid, e)
            except Exception as e:
                logger.warning("Digest check error: %s", e)

    async def check_recurring():
        notified: set[int] = set()
        while True:
            await asyncio.sleep(300)
            try:
                due = await get_due_recurring_payments()
                for p in due:
                    pid = p["id"]
                    if pid in notified:
                        continue
                    name = p.get("name", "")
                    amt = p.get("amount", 0)
                    cur = p.get("currency", "USD")
                    uid = p.get("user_id", 0)
                    if uid:
                        notified.add(pid)
                        await bump_recurring_payment(pid)
                        try:
                            await bot.send_message(
                                chat_id=uid,
                                text=f"🔄 <b>Payment due:</b> {name} — {amt:.0f} {cur}",
                                parse_mode="HTML",
                            )
                            logger.info("Recurring reminder sent to user %s: %s", uid, name)
                        except Exception as e:
                            logger.warning("Failed to send recurring reminder: %s", e)
            except Exception as e:
                logger.warning("Recurring check error: %s", e)

    async def check_reengagement():
        index = 0
        while True:
            await asyncio.sleep(3600)
            try:
                candidates = await get_candidates_for_reengagement()
                if not candidates:
                    continue
                sent = 0
                for u in candidates:
                    if sent >= 5:
                        break
                    uid = u["id"]
                    lang = u.get("language", "en") or "en"
                    try:
                        msg = get_reengagement_message(lang, index)
                        await bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                        await mark_reengagement_sent(uid)
                        sent += 1
                        logger.info("Re-engagement sent to user %s", uid)
                    except Exception as e:
                        logger.warning("Re-engagement failed for %s: %s", uid, e)
                index += 1
            except Exception as e:
                logger.warning("Re-engagement check error: %s", e)

    task = asyncio.create_task(check_reminders())
    logger.info("Reminder checker started")
    task2 = asyncio.create_task(check_payments())
    logger.info("Payment checker started")
    task3 = asyncio.create_task(check_digests())
    logger.info("Digest checker started")
    task4 = asyncio.create_task(check_recurring())
    logger.info("Recurring checker started")
    task5 = asyncio.create_task(check_reengagement())
    logger.info("Re-engagement checker started")
    yield
    task.cancel()
    task2.cancel()
    task3.cancel()
    task4.cancel()
    task5.cancel()
    await bot.session.close()
    logger.info("Bot session closed")


app = FastAPI(title="Sasha Bot", lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.body()
        update = Update.model_validate(json.loads(body), context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error("Webhook error: %s", e, exc_info=True)
    return Response(content="ok", status_code=200)


@app.get("/")
async def root():
    return {"status": "ok", "bot": "Sasha"}

@app.get("/dashboard")
async def dashboard():
    from pathlib import Path
    html = Path(__file__).parent / "app" / "dashboard.html"
    if html.exists():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html.read_text(encoding="utf-8"))
    return {"error": "not found"}

@app.get("/api/dashboard")
async def api_dashboard(user_id: int, token: str = ""):
    """Dashboard API with token-based auth.
    Token = bot sends a verification message with a one-time link.
    For now, require a secret token from env DASHBOARD_TOKEN or user's chat_id hashed.
    """
    from app.database import get_user_items, get_movements, get_todos, get_user_lang, get_calendar_events
    from fastapi.responses import JSONResponse
    import hashlib, os

    # Simple auth: token must match SHA256(user_id + secret)
    dashboard_secret = os.getenv("DASHBOARD_SECRET", "sasha-dashboard-2026")
    expected_token = hashlib.sha256(f"{user_id}{dashboard_secret}".encode()).hexdigest()[:16]
    if token != expected_token:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    try:
        expenses = await get_user_items(user_id) or []
        movements = await get_movements(user_id) or []
        todos = await get_todos(user_id) or []
        events = await get_calendar_events(user_id) or []
        lang = await get_user_lang(user_id) or "en"
        return JSONResponse({"ok": True, "lang": lang, "expenses": expenses, "movements": movements, "todos": todos, "events": events})
    except Exception as e:
        logger.error("Dashboard API error: %s", e)
        return JSONResponse({"ok": False, "error": str(e)})


def _verify_dashboard_token(user_id: int, token: str) -> bool:
    """Verify dashboard auth token."""
    import hashlib, os
    dashboard_secret = os.getenv("DASHBOARD_SECRET", "sasha-dashboard-2026")
    expected_token = hashlib.sha256(f"{user_id}{dashboard_secret}".encode()).hexdigest()[:16]
    return token == expected_token


@app.post("/api/dashboard/delete_expense")
async def api_delete_expense(user_id: int, token: str, expense_id: int):
    """Delete an expense from the dashboard."""
    from app.database import delete_expense
    from fastapi.responses import JSONResponse

    if not _verify_dashboard_token(user_id, token):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    try:
        ok = await delete_expense(expense_id)
        if ok:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": "Not found"}, status_code=404)
    except Exception as e:
        logger.error("Dashboard delete expense error: %s", e)
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/dashboard/toggle_todo")
async def api_toggle_todo(user_id: int, token: str, todo_id: int):
    """Toggle a todo's done status from the dashboard."""
    from app.database import get_todos, mark_todo_done
    from fastapi.responses import JSONResponse

    if not _verify_dashboard_token(user_id, token):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    try:
        todos = await get_todos(user_id)
        todo = next((t for t in todos if t.get("id") == todo_id), None)
        if not todo:
            return JSONResponse({"ok": False, "error": "Not found"}, status_code=404)
        new_done = not todo.get("done", False)
        await mark_todo_done(todo_id)
        return JSONResponse({"ok": True, "done": new_done})
    except Exception as e:
        logger.error("Dashboard toggle todo error: %s", e)
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.port)
