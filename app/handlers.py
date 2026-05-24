import logging

from aiogram import Bot, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.config import Config
from app.database import get_user_lang, set_user_lang, save_chat, log_event
from app.groq_client import create_groq_client, detect_intent
from app.intents import handle_tool_call
from app.i18n import t, TRANSLATIONS

logger = logging.getLogger(__name__)
router = Router()

config = Config()
groq = create_groq_client(config.groq_api_key) if config.groq_api_key else None

LANG_LIST = ["en", "ru", "es", "fr", "zh", "ar", "pt", "de", "hi", "ja"]

LANG_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(
        text=f"{TRANSLATIONS[code]['flag']} {TRANSLATIONS[code]['name']}",
        callback_data=f"lang_{code}"
    )] for code in LANG_LIST
])

_lang_cache: dict[int, str] = {}


async def get_lang(user_id: int) -> str:
    if user_id not in _lang_cache:
        _lang_cache[user_id] = await get_user_lang(user_id)
    return _lang_cache.get(user_id, "en")


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "lang_prompt"), reply_markup=LANG_KEYBOARD)


@router.callback_query(F.data.startswith("lang_"))
async def on_lang_choice(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    _lang_cache[callback.from_user.id] = lang
    await set_user_lang(callback.from_user.id, lang)
    await callback.message.edit_text(t(lang, "lang_changed"))
    await callback.message.answer(t(lang, "welcome"))


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "help"))


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer(t(await get_lang(message.from_user.id), "ping"))


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    await message.answer(t("en", "lang_prompt"), reply_markup=LANG_KEYBOARD)


@router.message(Command("webhook"))
async def cmd_webhook(message: types.Message, bot: Bot):
    info = await bot.get_webhook_info()
    lang = await get_lang(message.from_user.id)
    await message.answer(t(lang, "webhook",
        url=info.url or t(lang, "webhook_not_set"),
        errors=info.last_error_message or t(lang, "webhook_no_errors"),
    ))


@router.message(F.photo)
async def handle_photo(message: types.Message):
    lang = await get_lang(message.from_user.id)
    if lang == "ru":
        await message.answer("Изображение получено! Анализ скриншотов через мультимодальный AI — в День 4. Пока я могу работать только с текстом.")
    else:
        await message.answer("Image received! Screenshot analysis via multimodal AI comes on Day 4. For now I can only work with text.")


@router.message()
async def handle_message(message: types.Message):
    if not groq or not message.text:
        lang = await get_lang(message.from_user.id)
        await message.answer(t(lang, "not_ready"))
        return

    lang = await get_lang(message.from_user.id)
    await message.answer(t(lang, "thinking"))

    try:
        result, latency = detect_intent(groq, message.text, lang=lang)

        if isinstance(result, str):
            response_text = result
            await message.answer(response_text)
        else:
            response_text = await handle_tool_call(result, lang=lang)
            await message.answer(response_text)

        await save_chat(message.from_user.id, message.text, response_text, int(latency * 1000))
        logger.info("Handled message in %.2fs", latency)
    except Exception as e:
        logger.error("Groq error: %s", e)
        await message.answer(t(lang, "error"))
