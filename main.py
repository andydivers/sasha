import logging

import uvicorn
from fastapi import FastAPI, Request
from aiogram.types import Update

from app.config import Config
from app.bot import create_bot, create_dispatcher, setup_sentry
from app.database import init_db
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

app = FastAPI(title="Viktor Bot")


@app.on_event("startup")
async def on_startup():
    if config.supabase_url and config.supabase_key:
        init_db(config.supabase_url, config.supabase_key)
    webhook_url = config.webhook_url
    if webhook_url:
        await bot.set_webhook(url=webhook_url)
        logger.info("Webhook set to %s", webhook_url)


@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()
    logger.info("Bot session closed")


@app.post("/webhook")
async def webhook(request: Request) -> None:
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)


@app.get("/")
async def root():
    return {"status": "ok", "bot": "Viktor"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.port)
