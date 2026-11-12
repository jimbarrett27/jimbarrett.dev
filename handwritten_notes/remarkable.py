"""reMarkable notebooks emailed to the photos inbox → the handwritten notes pipeline.

The tablet's "send by email" goes to ``<photos address>+remarkable@gmail.com``, one PNG
per page. We poll that inbox over IMAP and hand each email to
:func:`handwritten_bot.transcribe_and_file`, so an emailed notebook gets the same
transcript, figure redraws, vault note and routing buttons as photos sent in the chat.
There's no chat message to reply to, so the bot starts one.

Only mail sent to the ``+remarkable`` address, from reMarkable's sender, that Gmail
has checked really did come from reMarkable is processed: every email costs a
vision call, so a stranger who learns the address mustn't be able to run that up.

An email is marked read once handled. If transcription fails it stays unread and is
retried on the next poll, up to :data:`MAX_ATTEMPTS` times.
"""

import asyncio
import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from telegram.ext import ContextTypes

from gcp_util.secrets import get_photo_email_address, get_photo_email_password, get_telegram_user_id
from handwritten_notes.handwritten_bot import PageImage, transcribe_and_file
from util.logging_util import setup_logger
from util.timezone import STOCKHOLM, stockholm_now

logger = setup_logger(__name__)

IMAP_HOST = "imap.gmail.com"
ADDRESS_TAG = "+remarkable"
SENDER = "my@remarkable.com"
SENDER_DOMAIN = "remarkable.com"
SUBJECT_PREFIX = "Document from my reMarkable:"
POLL_INTERVAL_SECONDS = 120
MAX_ATTEMPTS = 3
ORIGIN = "remarkable"

PAGE_NUMBER = re.compile(r"page (\d+)\.png$", re.IGNORECASE)
# Gmail adds its own Authentication-Results on top of whatever the sender put there.
GMAIL_VERDICT = re.compile(r"^\s*mx\.google\.com;")
DMARC_PASS = re.compile(rf"\bdmarc=pass\b.*\bheader\.from={re.escape(SENDER_DOMAIN)}\b", re.DOTALL)


@dataclass(frozen=True)
class Notebook:
    title: str | None
    when: datetime
    pages: list[PageImage]


def is_trusted(msg: Message) -> bool:
    """Sent to the +remarkable address, from reMarkable, and Gmail agrees it's genuine."""
    recipients = getaddresses(msg.get_all("To", []) + msg.get_all("Cc", []))
    if not any(f"{ADDRESS_TAG}@" in addr.lower() for _, addr in recipients):
        return False
    if parseaddr(msg.get("From", ""))[1].lower() != SENDER:
        return False
    verdicts = msg.get_all("Authentication-Results", [])
    return bool(verdicts) and bool(GMAIL_VERDICT.match(verdicts[0])) \
        and bool(DMARC_PASS.search(verdicts[0]))


def _title(msg: Message) -> str | None:
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    if subject.startswith(SUBJECT_PREFIX):
        subject = subject[len(SUBJECT_PREFIX):]
    return subject.strip() or None


def _when(msg: Message) -> datetime:
    try:
        return parsedate_to_datetime(msg["Date"]).astimezone(STOCKHOLM)
    except (TypeError, ValueError):
        return stockholm_now()


def _pages(msg: Message) -> list[PageImage]:
    """The PNG attachments, in page order ("Notebook - page 2.png")."""
    found = []
    for i, part in enumerate(msg.walk()):
        if part.get_content_type() != "image/png":
            continue
        number = PAGE_NUMBER.search(part.get_filename() or "")
        found.append(((int(number.group(1)) if number else float("inf"), i),
                      PageImage(part.get_payload(decode=True), "image/png", "png")))
    return [page for _, page in sorted(found, key=lambda f: f[0])]


def parse(raw: bytes) -> Notebook | None:
    """The notebook in a reMarkable email, or None if the email isn't one we trust."""
    msg = email.message_from_bytes(raw)
    if not is_trusted(msg):
        return None
    return Notebook(title=_title(msg), when=_when(msg), pages=_pages(msg))


def _login() -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(get_photo_email_address(), get_photo_email_password())
    imap.select("INBOX")
    return imap


def fetch_unseen() -> list[tuple[str, bytes]]:
    """(uid, raw email) for each unread email to the +remarkable address, without marking it read."""
    with _login() as imap:
        _, data = imap.uid("SEARCH", None, "UNSEEN", "TO", f'"{ADDRESS_TAG}"')
        found = []
        for uid in data[0].split():
            _, parts = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            found.append((uid.decode(), parts[0][1]))
        return found


def mark_seen(uid: str) -> None:
    with _login() as imap:
        imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")


_busy = asyncio.Lock()
_attempts: dict[str, int] = {}


async def handle(bot, uid: str, raw: bytes) -> bool:
    """Process one email; True once it's dealt with and can be marked read."""
    notebook = parse(raw)
    if notebook is None:
        logger.warning(f"Ignoring untrusted email {uid} to the reMarkable address")
        return True

    chat_id = get_telegram_user_id()
    name = notebook.title or "a notebook"
    if not notebook.pages:
        await bot.send_message(chat_id, f"📧 The reMarkable sent {name} without any PNG pages — "
                                        "set the tablet to send PNG and try again.")
        return True

    count = "1 page" if len(notebook.pages) == 1 else f"{len(notebook.pages)} pages"
    header = await bot.send_message(chat_id, f"📧 From the reMarkable: {name} ({count})")
    if await transcribe_and_file(header, notebook.pages, caption=notebook.title,
                                 when=notebook.when, origin=ORIGIN, routing_source=ORIGIN):
        _attempts.pop(uid, None)
        return True

    _attempts[uid] = _attempts.get(uid, 0) + 1
    if _attempts[uid] >= MAX_ATTEMPTS:
        _attempts.pop(uid)
        await header.reply_text(f"Giving up after {MAX_ATTEMPTS} tries — the email is still "
                                "in the inbox; send it again from the tablet to retry.")
        return True
    await header.reply_text(f"I'll try again in {POLL_INTERVAL_SECONDS // 60} minutes.")
    return False


async def poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job-queue entry point: handle whatever has arrived since the last poll."""
    if _busy.locked():  # a big notebook can outlast the poll interval
        return
    async with _busy:
        try:
            emails = await asyncio.to_thread(fetch_unseen)
        except Exception:
            logger.exception("Checking the reMarkable inbox failed")
            return
        for uid, raw in emails:
            try:
                done = await handle(context.bot, uid, raw)
            except Exception:
                logger.exception(f"Handling reMarkable email {uid} failed")
                continue
            if done:
                try:
                    await asyncio.to_thread(mark_seen, uid)
                except Exception:
                    logger.exception(f"Marking reMarkable email {uid} read failed")
