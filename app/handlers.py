import logging

from aiogram import Bot, types, Router
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Hi! I'm <b>Viktor</b> — your AI assistant.\n\n"
        "I can:\n"
        "• Analyze screenshots\n"
        "• Work with Google Sheets\n"
        "• Create calendar events\n"
        "• Generate reports\n\n"
        "What would you like to do?"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "/start — Restart\n"
        "/help — This help\n"
        "/ping — Ping test\n"
        "/webhook — Webhook status"
    )


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("Pong!")


@router.message(Command("webhook"))
async def cmd_webhook(message: types.Message, bot: Bot):
    info = await bot.get_webhook_info()
    await message.answer(
        f"<b>Webhook:</b>\n"
        f"URL: {info.url or 'Not set'}\n"
        f"Errors: {info.last_error_message or 'None'}"
    )


@router.message()
async def echo(message: types.Message):
    await message.answer(
        f"You wrote: <i>{message.text}</i>\n\n"
        f"For now I only know /start, /help, /ping"
    )
