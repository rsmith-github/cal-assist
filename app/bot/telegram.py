import asyncio
import logging
import re

from telegram import BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot import branding
from app.config import settings
from app.database import init_db, user_session
from app.logging_redaction import install_http_client_log_redaction
from app.tracker.service import TrackerService

logger = logging.getLogger(__name__)
_maintenance_pending: dict[int, int] = {}
_maintenance_timeout_tasks: dict[int, asyncio.Task] = {}


def _sync_get_maintenance(user_id: int) -> int | None:
    with user_session(user_id) as session:
        svc = TrackerService(session)
        return svc.get_maintenance_calories(user_id)


def _sync_set_maintenance(user_id: int, calories: int) -> int:
    with user_session(user_id) as session:
        svc = TrackerService(session)
        return svc.set_maintenance_calories(user_id, calories)


def _extract_calories_value(text: str) -> int | None:
    m = re.search(r"(?i)\b(\d{2,5})\b", text)
    if not m:
        return None
    v = int(m.group(1))
    if v < 800 or v > 10000:
        return None
    return v


async def _maintenance_timeout(user_id: int, chat_id: int, application: Application) -> None:
    await asyncio.sleep(10)
    if _maintenance_pending.get(user_id) != chat_id:
        return
    _maintenance_pending.pop(user_id, None)
    _maintenance_timeout_tasks.pop(user_id, None)
    await application.bot.send_message(
        chat_id=chat_id,
        text="No maintenance input received in 10 seconds. Nothing was changed.",
    )


def _clear_maintenance_wait(user_id: int) -> None:
    task = _maintenance_timeout_tasks.pop(user_id, None)
    if task:
        task.cancel()
    _maintenance_pending.pop(user_id, None)


async def _post_init(application: Application) -> None:
    """Set profile name, descriptions, and the / menu (best-effort)."""
    bot = application.bot
    try:
        await bot.set_my_name(branding.BOT_DISPLAY_NAME)
    except TelegramError as e:
        logger.warning("Could not set bot display name (set it in @BotFather if needed): %s", e)
    try:
        await bot.set_my_description(branding.BOT_DESCRIPTION)
        await bot.set_my_short_description(branding.BOT_SHORT_DESCRIPTION)
    except TelegramError as e:
        logger.warning("Could not set bot description: %s", e)
    try:
        await bot.set_my_commands(
            [
                BotCommand("start", "Intro and tips"),
                BotCommand("nd", "Close today, start the next day"),
                BotCommand("undo", "Remove the last logged entry"),
                BotCommand("summary", "Today's calorie totals"),
                BotCommand("week", "Weekly summary (closed days)"),
                BotCommand("maintenance", "Set or update maintenance calories"),
            ]
        )
    except TelegramError as e:
        logger.warning("Could not set bot commands: %s", e)


def _sync_handle(user_id: int, text: str) -> str:
    with user_session(user_id) as session:
        svc = TrackerService(session)
        return svc.handle(user_id, text)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            f"Hi — I'm {branding.BOT_DISPLAY_NAME}, your private calorie and exercise log.\n\n"
            "Log anything in plain text:\n"
            "  2 beers  ·  300 kcal chicken wrap  ·  ran 5km  ·  Muay Thai 1.5 hr\n\n"
            "Commands:\n"
            "  /nd — close today, start the next day\n"
            "  /undo — remove the last logged entry\n"
            "  /summary — today's totals\n"
            "  /week — last 7 days\n"
            "  /maintenance — set maintenance calories\n\n"
            "Corrections:\n"
            "  remove beers\n"
            "  actually 2 beers not 3"
        )


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    reply = await asyncio.to_thread(_sync_handle, update.effective_user.id, "summary")
    await update.message.reply_text(reply)


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    reply = await asyncio.to_thread(_sync_handle, update.effective_user.id, "week")
    await update.message.reply_text(reply)


async def cmd_nd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    reply = await asyncio.to_thread(_sync_handle, update.effective_user.id, "ND")
    await update.message.reply_text(reply)


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    reply = await asyncio.to_thread(_sync_handle, update.effective_user.id, "undo")
    await update.message.reply_text(reply)


async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    current = await asyncio.to_thread(_sync_get_maintenance, user_id)

    _clear_maintenance_wait(user_id)
    _maintenance_pending[user_id] = chat_id
    _maintenance_timeout_tasks[user_id] = asyncio.create_task(
        _maintenance_timeout(user_id, chat_id, context.application)
    )

    if current is None:
        await update.message.reply_text(
            "No maintenance calories set yet. Please send your daily maintenance kcal "
            "within 10 seconds (example: 2400)."
        )
    else:
        await update.message.reply_text(
            f"Your current maintenance is {current} kcal/day.\n"
            "Send a new value within 10 seconds to update it (example: 2400)."
        )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if _maintenance_pending.get(user_id) == chat_id:
        value = _extract_calories_value(update.message.text)
        if value is None:
            _clear_maintenance_wait(user_id)
            await update.message.reply_text(
                "Invalid maintenance value. Please use a number between 800 and 10000."
            )
            return
        saved = await asyncio.to_thread(_sync_set_maintenance, user_id, value)
        _clear_maintenance_wait(user_id)
        await update.message.reply_text(
            f"Maintenance updated successfully: {saved} kcal/day."
        )
        return
    reply = await asyncio.to_thread(
        _sync_handle,
        user_id,
        update.message.text,
    )
    await update.message.reply_text(reply)


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("nd", cmd_nd))
    app.add_handler(CommandHandler("newday", cmd_nd))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))
    app.add_handler(CommandHandler("metabolicrate", cmd_maintenance))
    app.add_handler(CommandHandler("tdee", cmd_maintenance))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def run_bot() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    install_http_client_log_redaction()
    if not settings.telegram_bot_token.strip():
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (see .env.example).")

    init_db()
    logger.info("Starting %s (Telegram)…", branding.BOT_DISPLAY_NAME)
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)
