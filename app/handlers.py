import logging

from aiogram import Bot, types, Router
from aiogram.filters import Command
from app.config import Config
from app.groq_client import create_groq_client, detect_intent
from app.intents import handle_tool_call

logger = logging.getLogger(__name__)
router = Router()

config = Config()
groq = create_groq_client(config.groq_api_key) if config.groq_api_key else None


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
async def handle_message(message: types.Message):
    if not groq or not message.text:
        await message.answer("I'm not fully set up yet. Try /help")
        return

    await message.answer("Thinking...")

    try:
        result, latency = detect_intent(groq, message.text)

        if isinstance(result, str):
            await message.answer(result)
        else:
            response = await handle_tool_call(result)
            await message.answer(response)

        logger.info("Handled message in %.2fs", latency)
    except Exception as e:
        logger.error("Groq error: %s", e)
        await message.answer("Sorry, I ran into an issue. Try again in a moment.")
