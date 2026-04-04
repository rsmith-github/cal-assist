import asyncio
import logging

from telegram import BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot import branding
from app.config import settings
from app.database import SessionLocal, init_db
from app.tracker.service import TrackerService

logger = logging.getLogger(__name__)


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
            ]
        )
    except TelegramError as e:
        logger.warning("Could not set bot commands: %s", e)


def _sync_handle(user_id: int, text: str) -> str:
    with SessionLocal() as session:
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
            "  /week — last 7 days\n\n"
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


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.text:
        return
    reply = await asyncio.to_thread(
        _sync_handle,
        update.effective_user.id,
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
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def run_bot() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    if not settings.telegram_bot_token.strip():
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (see .env.example).")

    init_db()
    logger.info("Starting %s (Telegram)…", branding.BOT_DISPLAY_NAME)
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)
