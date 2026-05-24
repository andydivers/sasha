import logging

from aiogram import Bot, types, Router
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я <b>Viktor</b> — твой AI-ассистент.\n\n"
        "Я умею:\n"
        "• Анализировать скриншоты\n"
        "• Работать с Google Таблицами\n"
        "• Создавать события в календаре\n"
        "• Формировать отчёты\n\n"
        "Что хочешь сделать?"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "/start — Начать\n"
        "/help — Эта справка\n"
        "/ping — Проверка работы\n"
        "/webhook — Статус вебхука"
    )


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("Pong!")


@router.message(Command("webhook"))
async def cmd_webhook(message: types.Message, bot: Bot):
    info = await bot.get_webhook_info()
    await message.answer(
        f"<b>Вебхук:</b>\n"
        f"URL: {info.url or 'Не установлен'}\n"
        f"Ошибок: {info.last_error_message or 'Нет'}"
    )


@router.message()
async def echo(message: types.Message):
    await message.answer(
        f"Ты написал: <i>{message.text}</i>\n\n"
        f"Пока я знаю только /start, /help, /ping"
    )
