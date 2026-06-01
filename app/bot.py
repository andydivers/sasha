import logging

import sentry_sdk
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Config

logger = logging.getLogger(__name__)


def create_bot(config: Config) -> Bot:
    return Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    return Dispatcher()


def setup_sentry(config: Config):
    if config.sentry_dsn:
        sentry_sdk.init(
            dsn=config.sentry_dsn,
            enable_tracing=True,
            traces_sample_rate=1.0,
        )
        logger.info("Sentry initialized")
