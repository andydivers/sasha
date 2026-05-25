import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from aiogram.types import Update

from app.config import Config
from app.bot import create_bot, create_dispatcher, setup_sentry
from app.database import init_db, get_due_reminders, mark_reminder_done
from app.sheets_client import init_sheets, is_ready as sheets_ready
from app.calendar_client import init_calendar, is_ready as calendar_ready
from app.crypto_client import verify_webhook
from app.handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

config = Config()
config.validate()

setup_sentry(config)

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

    task = asyncio.create_task(check_reminders())
    logger.info("Reminder checker started")
    yield
    task.cancel()
    await bot.session.close()
    logger.info("Bot session closed")


app = FastAPI(title="Sasha Bot", lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request) -> None:
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)


@app.get("/")
async def root():
    return {"status": "ok", "bot": "Sasha"}


@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "healthy"}


@app.post("/crypto_webhook")
async def crypto_webhook(request: Request):
    body = await request.body()
    data = verify_webhook(body)
    if data and data.get("status") == "paid":
        order_id = data.get("order_id", "")
        try:
            parts = order_id.split("_")
            user_id = int(parts[0])
            await bot.send_message(
                chat_id=user_id,
                text="✅ <b>Payment received!</b>\nThanks for your purchase. How can I help?",
            )
            logger.info("Crypto payment confirmed for user %s", user_id)
        except (IndexError, ValueError) as e:
            logger.warning("Failed to parse order_id: %s", e)
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.port)
