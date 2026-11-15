"""Polls the reMarkable's export folders in Drive and dispatches each file by folder.

    reMarkable/
      Notes/              → remarkable_drive.notebooks (handwritten notes pipeline)
      Papers/Annotated/   → remarkable_drive.reading (annotations → the paper's stub)
      Done/               ← processed files are moved here
      Failed/             ← files given up on, or that can't be handled; move one back to retry

A file stays where it is until its handler has finished with it, so a crash or a
restart just means it's picked up again on the next poll. Retries are counted in
memory: after :data:`MAX_ATTEMPTS` failures the file moves to ``Failed/`` and you're
told. A restart resets the count, which only buys a failing file a few more tries.

Only your account can write to this Drive, so unlike the email ingest there's no
sender to verify.
"""

import asyncio
import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from telegram.ext import ContextTypes

from gcp_util import drive
from gcp_util.secrets import get_telegram_user_id
from util.logging_util import setup_logger

logger = setup_logger(__name__)

ROOT = "reMarkable"
DONE = f"{ROOT}/Done"
FAILED = f"{ROOT}/Failed"
POLL_INTERVAL_SECONDS = 120
MAX_ATTEMPTS = 3


class Outcome(enum.Enum):
    DONE = "done"        # handled → Done/
    RETRY = "retry"      # failed in a way worth retrying → stays put
    REJECT = "reject"    # can never be handled → Failed/ (the handler has said why)


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified: datetime

    @classmethod
    def from_api(cls, item: dict) -> "DriveFile":
        return cls(
            id=item["id"],
            name=item["name"],
            mime_type=item["mimeType"],
            modified=datetime.fromisoformat(item["modifiedTime"].replace("Z", "+00:00")),
        )


# handler(bot, chat_id, file, content) → Outcome
Handler = Callable[[object, int, DriveFile, bytes], Awaitable[Outcome]]


def _handlers() -> dict[str, Handler]:
    # Imported here: the handlers import this module for DriveFile/Outcome.
    from remarkable_drive import notebooks, reading
    return {f"{ROOT}/Notes": notebooks.handle,
            f"{ROOT}/Papers/Annotated": reading.handle}


_folder_ids: dict[str, str] = {}
_attempts: dict[str, int] = {}
_busy = asyncio.Lock()


def folder_id(path: str) -> str:
    if path not in _folder_ids:
        _folder_ids[path] = drive.ensure_folder(path)
    return _folder_ids[path]


def _list(path: str) -> list[DriveFile]:
    return [DriveFile.from_api(item) for item in drive.list_files(folder_id(path))
            if item["mimeType"] != drive.FOLDER_MIME]


async def _move(file: DriveFile, path: str) -> None:
    try:
        await asyncio.to_thread(drive.move_file, file.id, folder_id(path))
    except Exception:
        logger.exception(f"Moving {file.name} to {path} failed")


async def process(bot, chat_id: int, file: DriveFile, handler: Handler) -> None:
    """Run one file through its handler and move it according to the outcome."""
    try:
        data = await asyncio.to_thread(drive.download_bytes, file.id)
        outcome = await handler(bot, chat_id, file, data)
    except Exception:
        logger.exception(f"Handling {file.name} from Drive failed")
        outcome = Outcome.RETRY

    if outcome is Outcome.DONE:
        _attempts.pop(file.id, None)
        await _move(file, DONE)
    elif outcome is Outcome.REJECT:
        _attempts.pop(file.id, None)
        await _move(file, FAILED)
    else:
        _attempts[file.id] = _attempts.get(file.id, 0) + 1
        if _attempts[file.id] >= MAX_ATTEMPTS:
            _attempts.pop(file.id)
            await _move(file, FAILED)
            await bot.send_message(
                chat_id, f"📁 Giving up on {file.name} after {MAX_ATTEMPTS} tries — moved it to "
                         f"{FAILED}. Move it back to retry.")


async def poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job-queue entry point: handle whatever has been exported since the last poll."""
    if _busy.locked():  # a long notebook can outlast the poll interval
        return
    async with _busy:
        chat_id = get_telegram_user_id()
        for path, handler in _handlers().items():
            try:
                files = await asyncio.to_thread(_list, path)
            except Exception:
                logger.exception(f"Listing {path} in Drive failed")
                _folder_ids.pop(path, None)  # in case the folder was deleted and recreated
                continue
            for file in sorted(files, key=lambda f: f.modified):
                await process(context.bot, chat_id, file, handler)
