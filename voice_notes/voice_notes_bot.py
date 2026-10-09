"""Telegram bot: send it a voice note, get the transcript back, find it in Obsidian."""

import asyncio
from pathlib import Path

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from gcp_util.secrets import get_telegram_user_id
from util.logging_util import setup_logger
from util.timezone import STOCKHOLM
from voice_notes import audio, transcribe, vault

logger = setup_logger(__name__)

TELEGRAM_MAX_MESSAGE = 4096
NO_SPEECH = "_(no speech recognised)_"

# Fetching the file from Telegram is the flaky step: a get_file call once hit
# the 5 s default read timeout and the note was lost. Give each call longer, and
# retry transient network errors (TimedOut is a NetworkError) with a backoff.
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 2.0


async def _download(bot, file_id: str) -> bytes:
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            file = await bot.get_file(file_id, read_timeout=DOWNLOAD_TIMEOUT_SECONDS)
            return bytes(await file.download_as_bytearray(read_timeout=DOWNLOAD_TIMEOUT_SECONDS))
        except NetworkError as e:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise
            logger.warning(f"Voice note download attempt {attempt} failed ({e}); retrying")
            await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)


def _split_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE) -> list[str]:
    """Split on whitespace into pieces Telegram will accept."""
    parts = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if update.effective_user.id != get_telegram_user_id():
        await message.reply_text("Unauthorised.")
        return

    media = message.voice or message.audio
    audio_ext = "ogg"
    if message.audio and message.audio.file_name and Path(message.audio.file_name).suffix:
        audio_ext = Path(message.audio.file_name).suffix.lstrip(".").lower()

    await message.reply_text("Transcribing…")

    try:
        audio_bytes = await _download(context.bot, media.file_id)
    except Exception as e:
        logger.exception("Voice note download failed")
        await message.reply_text(
            f"Couldn't download the voice note from Telegram ({e}) — please send it again."[:500])
        return

    try:
        samples = await asyncio.to_thread(audio.decode, audio_bytes)
        text = await asyncio.to_thread(transcribe.transcribe, samples)
    except Exception as e:
        logger.exception("Voice note transcription failed")
        await message.reply_text(f"Transcription failed: {e}"[:500])
        return

    for part in _split_message(text or "(no speech recognised)"):
        await message.reply_text(part)

    # The transcript is already in the chat, so a failed save loses nothing.
    try:
        saved = await asyncio.to_thread(
            vault.save_note,
            when=message.date.astimezone(STOCKHOLM),
            audio=audio_bytes,
            audio_ext=audio_ext,
            duration_s=audio.duration_seconds(samples),
            model=transcribe.MODEL_LABEL,
            transcript=text or NO_SPEECH,
        )
    except Exception as e:
        logger.exception("Saving voice note to the vault failed")
        await message.reply_text(f"⚠️ Couldn't save to Obsidian: {e}"[:500])
        return

    await message.reply_text(f"📝 Saved to {vault.NOTES_FOLDER}/{saved.note_path.name}")


async def preload_model(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Load Whisper at startup. If it fails here, the first note will try again."""
    try:
        await asyncio.to_thread(transcribe.load)
    except Exception:
        logger.exception("Preloading the Whisper model failed")


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send me a voice note and I'll transcribe it into Obsidian."
    )


def get_handlers():
    return [
        CommandHandler("start", handle_start),
        MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
    ]
