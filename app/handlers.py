import logging

from aiogram import Bot, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.config import Config
from app.database import get_user_lang, set_user_lang, save_chat, log_event
from app.groq_client import create_groq_client, detect_intent
from app.intents import handle_tool_call
from app.gemini_client import init_gemini, analyze_image
from app.sheets_client import init_sheets, read_sheet, write_sheet, append_row, get_service_email, is_ready as sheets_ready
from app.i18n import t, TRANSLATIONS

logger = logging.getLogger(__name__)
router = Router()

config = Config()
groq = create_groq_client(config.groq_api_key) if config.groq_api_key else None

if config.gemini_api_key:
    init_gemini(config.gemini_api_key)

if config.google_sheets_creds:
    try:
        init_sheets(config.google_sheets_creds)
    except Exception as e:
        logger.warning("Google Sheets init failed: %s. Set GOOGLE_SHEETS_CREDENTIALS via Render Secret File.", e)

LANG_LIST = ["en", "ru", "es", "fr", "zh", "ar", "pt", "de", "hi", "ja"]

LANG_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(
        text=f"{TRANSLATIONS[code]['flag']} {TRANSLATIONS[code]['name']}",
        callback_data=f"lang_{code}"
    )] for code in LANG_LIST
])

_lang_cache: dict[int, str] = {}
_sheet_cache: dict[int, str] = {}


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


@router.message(Command("sheet"))
async def cmd_sheet(message: types.Message):
    lang = await get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        if lang == "ru":
            await message.answer(
                "Отправь ссылку на Google Таблицу:\n"
                "<code>/sheet https://docs.google.com/spreadsheets/d/...</code>\n\n"
                "Не забудь <b>открыть доступ</b> таблице для:\n"
                f"<code>{get_service_email()}</code>"
            )
        else:
            await message.answer(
                "Send your Google Sheet URL:\n"
                "<code>/sheet https://docs.google.com/spreadsheets/d/...</code>\n\n"
                "Make sure to <b>share</b> the sheet with:\n"
                f"<code>{get_service_email()}</code>"
            )
        return

    url = parts[1].strip()
    _sheet_cache[message.from_user.id] = url
    if lang == "ru":
        await message.answer("Google Таблица подключена! Теперь я могу читать и записывать данные.")
    else:
        await message.answer("Google Sheet connected! I can now read and write data.")


@router.message(F.photo)
async def handle_photo(message: types.Message, bot: Bot):
    lang = await get_lang(message.from_user.id)
    caption = message.caption or ""
    prompt = caption if caption else ("What do you see in this image?" if lang != "ru" else "Что ты видишь на этом изображении?")

    await message.answer(t(lang, "thinking"))

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        image_bytes = await bot.download_file(file.file_path)
        result = analyze_image(image_bytes.read(), "image/jpeg", prompt)
        await message.answer(result)
        await log_event(message.from_user.id, "image_analyzed")
    except Exception as e:
        logger.error("Gemini error: %s", e)
        await message.answer(t(lang, "error"))


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
            sheet_url = _sheet_cache.get(message.from_user.id)
            response_text = await handle_tool_call(result, lang=lang, sheet_url=sheet_url)
            await message.answer(response_text)

        await save_chat(message.from_user.id, message.text, response_text, int(latency * 1000))
        logger.info("Handled message in %.2fs", latency)
    except Exception as e:
        logger.error("Groq error: %s", e)
        await message.answer(t(lang, "error"))
