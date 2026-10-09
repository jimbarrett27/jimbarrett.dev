import asyncio
import signal
from datetime import time as dt_time

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from gcp_util.secrets import get_swedish_bot_key, get_minecraft_bot_key, get_photos_bot_key, get_dnd_bot_key, get_memes_bot_key, get_voice_notes_bot_key
from swedish.database import init_db as init_swedish_db, populate_db
from swedish import swedish_bot
from photos.photos_bot import get_handlers as get_photo_handlers
from voice_notes.voice_notes_bot import get_handlers as get_voice_notes_handlers, preload_model
from handwritten_notes.handwritten_bot import get_handlers as get_handwritten_notes_handlers
from dnd.database import init_db as init_dnd_db
from dnd.dnd_bot import get_handlers as get_dnd_handlers
from memes.daily_hn_meme import send_daily_hn_meme
from minecraft.react_to_logs import react_to_logs as react_to_minecraft_logs
from minecraft.healthcheck import run_healthcheck, run_on_demand_check, run_daily_summary
from content_screening.scanner import run_full_scan
from tapestry.daily import daily_tapestry_task
from fitness.daily import REFRESH_INTERVAL_SECONDS, fitness_panel_task
from swedish import daily as swedish_panel
from telegram_bot.telegram_bot import TelegramBot
from util.logging_util import configure_root_logging, setup_logger, log_telegram_message_received
from util.timezone import stockholm_time, stockholm_now

logger = setup_logger(__name__)

def is_weekend() -> bool:
    """True if it's currently Saturday or Sunday in Stockholm."""
    # datetime.weekday(): Monday=0 ... Saturday=5, Sunday=6.
    return stockholm_now().weekday() >= 5


# --- Swedish bot handlers ---

async def swedish_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome! I can help you practise Swedish.",
        reply_markup=swedish_bot.MAIN_MENU_KEYBOARD,
    )


async def swedish_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """🇸🇪 Swedish Learning:
• 🇸🇪 Practise - Practice a random flashcard
• 📝 Add Word - Add a new word to your dictionary
• sv add <type> <word> - Add word directly (type: noun, verb, adj, auto)
• sv practise - Start practice directly"""
    await update.message.reply_text(help_text, reply_markup=swedish_bot.MAIN_MENU_KEYBOARD)


async def swedish_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    log_telegram_message_received(logger, str(update.effective_chat.id),
                                  update.effective_user.username or "unknown", text)
    rest = ' '.join(text.split()[1:]).strip()
    await swedish_bot.handle_text_command_async(update, context, rest)


async def swedish_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_telegram_message_received(logger, str(update.effective_chat.id),
                                  update.effective_user.username or "unknown",
                                  update.message.text)
    await update.message.reply_text(
        "I didn't understand that. Use the menu buttons or type 'sv help'.",
        reply_markup=swedish_bot.MAIN_MENU_KEYBOARD,
    )


# --- Minecraft bot handlers ---

async def minecraft_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Minecraft server monitor bot.\n\n"
        "Use /status to check server health.",
    )


async def minecraft_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """Available commands:

🖥️ Minecraft Server:
• /status - Check server & tunnel health
• Automatic alerts when server state changes
• Daily summary at 10am"""
    await update.message.reply_text(help_text)


async def minecraft_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_telegram_message_received(logger, str(update.effective_chat.id),
                                  update.effective_user.username or "unknown",
                                  update.message.text)
    await update.message.reply_text("Checking server status...")
    msg = run_on_demand_check()
    await update.message.reply_text(msg)


async def periodic_tasks(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        react_to_minecraft_logs(context.bot_data["minecraft_bot"])
    except Exception as e:
        logger.error(f"Error in periodic tasks: {e}")


async def healthcheck_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        run_healthcheck(context.bot_data["minecraft_bot"])
    except Exception as e:
        logger.error(f"Error in healthcheck: {e}")


async def daily_summary_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        run_daily_summary(context.bot_data["minecraft_bot"])
    except Exception as e:
        logger.error(f"Error in daily summary: {e}")


async def daily_paper_scan_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scan the paper feeds once a day, pinging only if something looks broken.

    The scan does blocking network + LLM work, so it runs in a worker thread to
    avoid stalling the bots' event loop. Papers flow silently into the triage
    queue; a healthy run sends nothing. The notify bot speaks up when the scan
    raises, or when every feed comes back empty on a weekday -- the fetchers
    swallow per-feed errors, so that is what a broken network or feed looks like.
    Weekends are exempt from the empty check because arXiv doesn't announce then.
    """
    notify = context.bot_data["minecraft_bot"].send_message_to_me
    try:
        counts = await asyncio.to_thread(run_full_scan)
    except Exception as e:
        logger.exception("Error in daily paper scan")
        notify(f"📚 Daily paper scan failed: {e}"[:500])
        return
    logger.info(f"Daily paper scan: {counts}")
    if counts["found"] == 0 and not is_weekend():
        notify("📚 Daily paper scan got nothing back from any feed — they may be broken")


# --- App setup ---

def build_swedish_app() -> Application:
    app = Application.builder().token(get_swedish_bot_key()).build()

    app.add_handler(CommandHandler("start", swedish_start))
    app.add_handler(CommandHandler("help", swedish_help))
    app.add_handler(swedish_bot.get_practice_conversation_handler())
    app.add_handler(swedish_bot.get_add_word_conversation_handler())
    app.add_handler(MessageHandler(
        filters.Regex(r"^❓ Help$"), swedish_help
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"(?i)^(sv|🇸🇪)\s") & filters.TEXT,
        swedish_text_command,
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        swedish_fallback,
    ))

    return app


def build_dnd_app() -> Application:
    app = Application.builder().token(get_dnd_bot_key()).build()
    for handler in get_dnd_handlers():
        app.add_handler(handler)
    return app


def build_photos_app() -> Application:
    app = Application.builder().token(get_photos_bot_key()).build()
    for handler in get_photo_handlers():
        app.add_handler(handler)
    return app


def build_voice_notes_app() -> Application:
    app = Application.builder().token(get_voice_notes_bot_key()).build()
    # Voice notes and photos of handwritten notes share one bot, one chat.
    for handler in get_voice_notes_handlers() + get_handwritten_notes_handlers():
        app.add_handler(handler)
    if app.job_queue:
        # Whisper takes ~20 s to load; do it now rather than on the first note.
        app.job_queue.run_once(preload_model, when=0)
    return app


def build_memes_app() -> Application:
    app = Application.builder().token(get_memes_bot_key()).build()
    if app.job_queue:
        # Every day, not just weekdays: the meme also feeds the TRMNL panel, and
        # a weekday-only job left Friday's meme on the wall all weekend.
        app.job_queue.run_daily(send_daily_hn_meme, time=stockholm_time(9, 45))
    else:
        logger.warning("JobQueue not available - daily meme disabled.")
    return app


def build_minecraft_app() -> Application:
    app = Application.builder().token(get_minecraft_bot_key()).build()
    # Kept as the personal "notify" bot (alerts when the daily paper scan or
    # tapestry go wrong) even though the Minecraft server itself was sunsetted (2026-06-02).
    app.bot_data["minecraft_bot"] = TelegramBot(get_minecraft_bot_key())

    app.add_handler(CommandHandler("start", minecraft_start))
    app.add_handler(CommandHandler("help", minecraft_help))
    app.add_handler(CommandHandler("status", minecraft_status))

    if app.job_queue:
        # Minecraft server monitoring disabled — server sunsetted 2026-06-02.
        # app.job_queue.run_repeating(periodic_tasks, interval=60, first=10)
        # app.job_queue.run_repeating(healthcheck_task, interval=300, first=30)
        # app.job_queue.run_daily(daily_summary_task, time=dt_time(hour=10, minute=0))
        # Daily paper feed scan → papers land in the triage queue; the bot only
        # messages if the scan looks broken.
        app.job_queue.run_daily(daily_paper_scan_task, time=stockholm_time(7, 30))
        # Daily news-tapestry panel → generated + uploaded to GCS for the website.
        app.job_queue.run_daily(daily_tapestry_task, time=stockholm_time(9, 0))
        # Self-heal: also try on startup so a restart during the daily run (e.g.
        # an unattended-upgrade killing the bot mid-generation) doesn't skip the
        # day. generate_next_panel is idempotent — a no-op if today already exists.
        app.job_queue.run_once(daily_tapestry_task, when=60)
        # TRMNL fitness panel → refreshed on a fixed interval so the device
        # always finds current data, whenever the watch happens to sync.
        app.job_queue.run_repeating(
            fitness_panel_task, interval=REFRESH_INTERVAL_SECONDS, first=30
        )
        # TRMNL Swedish word panel → hourly, on the hour, cycling through the
        # day's words; the first run of a day generates them. Also once on
        # startup so a restart doesn't leave the panel an hour behind.
        app.job_queue.run_repeating(
            swedish_panel.swedish_panel_task,
            interval=swedish_panel.REFRESH_INTERVAL_SECONDS,
            first=swedish_panel.seconds_to_next_hour(),
        )
        app.job_queue.run_once(swedish_panel.swedish_panel_task, when=45)
    else:
        logger.warning("JobQueue not available - daily paper scan disabled.")

    return app


async def run():
    swedish_app = build_swedish_app()
    minecraft_app = build_minecraft_app()
    photos_app = build_photos_app()
    dnd_app = build_dnd_app()
    memes_app = build_memes_app()
    voice_notes_app = build_voice_notes_app()

    async with swedish_app, minecraft_app, photos_app, dnd_app, memes_app, voice_notes_app:
        await swedish_app.start()
        await swedish_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await minecraft_app.start()
        await minecraft_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await photos_app.start()
        await photos_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await dnd_app.start()
        await dnd_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await memes_app.start()
        await memes_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await voice_notes_app.start()
        await voice_notes_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        logger.info("All bots are running.")
        print("All bots are running...")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        await stop_event.wait()

        print("Shutting down...")
        await swedish_app.updater.stop()
        await swedish_app.stop()
        await minecraft_app.updater.stop()
        await minecraft_app.stop()
        await photos_app.updater.stop()
        await photos_app.stop()
        await dnd_app.updater.stop()
        await dnd_app.stop()
        await memes_app.updater.stop()
        await memes_app.stop()
        await voice_notes_app.updater.stop()
        await voice_notes_app.stop()


def main():
    configure_root_logging()
    print("Starting telegram bots...")
    init_swedish_db()
    init_dnd_db()
    populate_db()
    asyncio.run(run())


if __name__ == "__main__":
    main()
