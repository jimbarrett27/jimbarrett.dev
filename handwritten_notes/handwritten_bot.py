"""Photos of handwritten notes → transcript in the chat → note in Obsidian.

Lives on the voice notes bot, so one chat catches everything captured on the go.
An album of photos is one note: Telegram delivers each photo as its own update
sharing a ``media_group_id``, so pages are buffered and the group is processed
once the album has had time to arrive.

Notebooks emailed from the reMarkable come in through :mod:`handwritten_notes.remarkable`
and join at :func:`transcribe_and_file`.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from telegram import Message, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from gcp_util.secrets import get_telegram_user_id
from handwritten_notes import figures, transcribe, vault
from notes_routing import telegram as routing
from util.logging_util import setup_logger
from util.timezone import STOCKHOLM
from voice_notes.voice_notes_bot import download, split_message

logger = setup_logger(__name__)

# Document mime types the vision models accept, and the extension they're filed under.
SUPPORTED_DOCUMENTS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
ALBUM_WAIT_SECONDS = 2.5
ALBUMS_KEY = "handwritten_albums"


@dataclass(frozen=True)
class Page:
    message: Message
    file_id: str
    mime: str
    ext: str


@dataclass(frozen=True)
class PageImage:
    """One page's image, wherever it came from."""
    data: bytes
    mime: str
    ext: str


def _page(message: Message) -> Page | None:
    if message.photo:
        largest = message.photo[-1]
        return Page(message, largest.file_id, "image/jpeg", "jpg")
    ext = SUPPORTED_DOCUMENTS.get(message.document.mime_type)
    if ext is None:
        return None
    return Page(message, message.document.file_id, message.document.mime_type, ext)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if update.effective_user.id != get_telegram_user_id():
        await message.reply_text("Unauthorised.")
        return

    page = _page(message)
    if page is None:
        await message.reply_text(
            f"I can't read {message.document.mime_type} images — send it as a photo, "
            "or as a JPEG/PNG file.")
        return

    if message.media_group_id is None:
        await process([page], context.bot)
        return

    albums = context.bot_data.setdefault(ALBUMS_KEY, {})
    if message.media_group_id not in albums:
        albums[message.media_group_id] = []
        context.job_queue.run_once(_flush_album, ALBUM_WAIT_SECONDS, data=message.media_group_id)
    albums[message.media_group_id].append(page)


async def _flush_album(context: ContextTypes.DEFAULT_TYPE) -> None:
    pages = context.bot_data.get(ALBUMS_KEY, {}).pop(context.job.data, [])
    if pages:
        await process(pages, context.bot)


async def process(pages: list[Page], bot) -> None:
    pages = sorted(pages, key=lambda p: p.message.message_id)
    first = pages[0].message
    caption = next((p.message.caption for p in pages if p.message.caption), None)

    await first.reply_text(
        "Transcribing…" if len(pages) == 1 else f"Transcribing {len(pages)} pages…")

    try:
        images = [await download(bot, p.file_id, what="photo") for p in pages]
    except Exception as e:
        logger.exception("Handwritten note download failed")
        await first.reply_text(
            f"Couldn't download the photo from Telegram ({e}) — please send it again."[:500])
        return

    await transcribe_and_file(
        first, [PageImage(data, p.mime, p.ext) for data, p in zip(images, pages)],
        caption=caption, when=first.date.astimezone(STOCKHOLM))


async def transcribe_and_file(reply_to: Message, pages: list[PageImage], *, caption: str | None,
                              when: datetime, origin: str = "telegram",
                              routing_source: str = "handwritten") -> bool:
    """Transcribe pages already in hand, post the transcript and file the note.

    Every step reports into the chat as a reply to ``reply_to``. Returns False only if
    no transcript came out, the one failure worth retrying; after that the transcript
    is in the chat, so later failures lose nothing.
    """
    images = [(p.data, p.mime) for p in pages]
    try:
        text = await asyncio.to_thread(transcribe.transcribe, images, caption)
    except Exception as e:
        logger.exception("Handwritten note transcription failed")
        await reply_to.reply_text(f"Transcription failed: {e}"[:500])
        return False

    svgs, previews = [], []
    if wanted := figures.find_figures(text, len(pages)):
        await reply_to.reply_text(
            "Redrawing the figure…" if len(wanted) == 1 else f"Redrawing {len(wanted)} figures…")
        # redraw_all degrades marker by marker, so this only guards the unexpected.
        try:
            redrawn = await asyncio.to_thread(figures.redraw_all, text, images)
            text, svgs, previews = redrawn.transcript, redrawn.svgs, redrawn.previews
        except Exception:
            logger.exception("Redrawing figures failed")

    # A page that's only a drawing has no text left once its figure becomes a preview.
    chat = figures.for_chat(text)
    if chat or not previews:
        for part in split_message(chat or "(no text recognised)"):
            await reply_to.reply_text(part)

    # Previews are a nicety for the chat; the note has the real thing.
    for preview in previews:
        try:
            await reply_to.reply_photo(preview.png, caption=preview.description[:1024])
        except Exception:
            logger.exception("Sending a figure preview failed")

    # The transcript is already in the chat, so a failed save loses nothing.
    try:
        saved = await asyncio.to_thread(
            vault.save_note,
            when=when,
            pages=[(p.data, p.ext) for p in pages],
            model=transcribe.MODEL,
            caption=caption,
            transcript=text or "_(no text recognised)_",
            figures=svgs,
            origin=origin,
        )
    except Exception as e:
        logger.exception("Saving handwritten note to the vault failed")
        await reply_to.reply_text(f"⚠️ Couldn't save to Obsidian: {e}"[:500])
        return True

    await routing.route_and_reply(reply_to, saved.note_path,
                                  transcript=text or "_(no text recognised)_",
                                  hint=caption, source=routing_source)
    return True


def get_handlers():
    return [MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image)]
