"""Tests for the handwritten notes handler, with Telegram and the model faked."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telegram.error import TimedOut

from handwritten_notes import handwritten_bot as bot
from voice_notes import voice_notes_bot

ME = 42
FOLDER = "Handwritten Notes"


class FakeMessage:
    def __init__(self, message_id=1, photo=None, document=None, media_group_id=None, caption=None):
        self.message_id = message_id
        self.photo = photo or []
        self.document = document
        self.media_group_id = media_group_id
        self.caption = caption
        self.date = datetime(2026, 10, 9, 12, 32, tzinfo=timezone.utc)
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeBot:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    async def get_file(self, file_id, **kwargs):
        self.calls.append(file_id)
        if len(self.calls) <= self.failures:
            raise TimedOut()
        return SimpleNamespace(download_as_bytearray=_bytes_for(file_id))


def _bytes_for(file_id):
    async def download(**kwargs):
        return bytearray(f"img-{file_id}".encode())
    return download


class FakeJobQueue:
    def __init__(self):
        self.jobs = []

    def run_once(self, callback, when, data=None):
        self.jobs.append((callback, when, data))


def _context(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or FakeBot(), bot_data={}, job_queue=FakeJobQueue())


def _photo(file_id="big", **kwargs):
    # Telegram lists photo sizes smallest first.
    return FakeMessage(photo=[SimpleNamespace(file_id="thumb"), SimpleNamespace(file_id=file_id)],
                       **kwargs)


def _update(message, user_id=ME):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


@pytest.fixture(autouse=True)
def fakes(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_notes_bot, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(bot, "get_telegram_user_id", lambda: ME)
    seen = []

    def fake_transcribe(pages, caption=None):
        seen.append((pages, caption))
        return "- [ ] Remember the milk"
    monkeypatch.setattr(bot.transcribe, "transcribe", fake_transcribe)
    return SimpleNamespace(vault=tmp_path / FOLDER, seen=seen)


@pytest.mark.asyncio
async def test_single_photo_uses_largest_size_and_files_the_note(fakes):
    message = _photo()
    await bot.handle_image(_update(message), _context())

    assert message.replies == [
        "Transcribing…",
        "- [ ] Remember the milk",
        f"📝 Saved to {FOLDER}/2026-10-09 1432.md",
    ]
    assert fakes.seen == [([(b"img-big", "image/jpeg")], None)]
    assert (fakes.vault / "images" / "2026-10-09 1432 p1.jpg").read_bytes() == b"img-big"
    assert "- [ ] Remember the milk" in (fakes.vault / "2026-10-09 1432.md").read_text()


@pytest.mark.asyncio
async def test_image_sent_as_file_keeps_its_type(fakes):
    doc = SimpleNamespace(file_id="scan", mime_type="image/png")
    await bot.handle_image(_update(FakeMessage(document=doc)), _context())
    assert fakes.seen[0][0] == [(b"img-scan", "image/png")]
    assert (fakes.vault / "images" / "2026-10-09 1432 p1.png").exists()


@pytest.mark.asyncio
async def test_unsupported_image_type_is_rejected(fakes):
    message = FakeMessage(document=SimpleNamespace(file_id="x", mime_type="image/heic"))
    await bot.handle_image(_update(message), _context())
    assert message.replies[0].startswith("I can't read image/heic images")
    assert fakes.seen == []


@pytest.mark.asyncio
async def test_album_becomes_one_note_with_pages_in_order(fakes):
    context = _context()
    # Updates can arrive out of order; the caption sits on one of them.
    for mid in (3, 1, 2):
        message = _photo(file_id=f"p{mid}", message_id=mid, media_group_id="album",
                         caption="Standup" if mid == 1 else None)
        await bot.handle_image(_update(message), context)

    assert fakes.seen == []  # nothing happens until the album has arrived
    [(callback, when, data)] = context.job_queue.jobs
    assert when == bot.ALBUM_WAIT_SECONDS

    await callback(SimpleNamespace(bot=context.bot, bot_data=context.bot_data,
                                   job=SimpleNamespace(data=data)))

    [(pages, caption)] = fakes.seen
    assert [data for data, _ in pages] == [b"img-p1", b"img-p2", b"img-p3"]
    assert caption == "Standup"
    note = (fakes.vault / "2026-10-09 1432.md").read_text()
    assert "pages: 3\n" in note and "# Standup\n" in note
    assert context.bot_data[bot.ALBUMS_KEY] == {}


@pytest.mark.asyncio
async def test_rejects_other_users(fakes):
    message = _photo()
    await bot.handle_image(_update(message, user_id=7), _context())
    assert message.replies == ["Unauthorised."]
    assert not fakes.vault.exists()


@pytest.mark.asyncio
async def test_download_failure_says_so(fakes):
    dead = FakeBot(failures=voice_notes_bot.DOWNLOAD_ATTEMPTS)
    message = _photo()
    await bot.handle_image(_update(message), _context(dead))
    assert message.replies[1].startswith("Couldn't download the photo from Telegram")
    assert fakes.seen == []
    assert not fakes.vault.exists()


@pytest.mark.asyncio
async def test_transcription_failure_saves_nothing(monkeypatch, fakes):
    def broken(pages, caption=None):
        raise RuntimeError("model exploded")
    monkeypatch.setattr(bot.transcribe, "transcribe", broken)

    message = _photo()
    await bot.handle_image(_update(message), _context())
    assert message.replies == ["Transcribing…", "Transcription failed: model exploded"]
    assert not fakes.vault.exists()


@pytest.mark.asyncio
async def test_transcript_still_sent_when_vault_write_fails(monkeypatch, fakes):
    def broken(**kwargs):
        raise OSError("disk on fire")
    monkeypatch.setattr(bot.vault, "save_note", broken)

    message = _photo()
    await bot.handle_image(_update(message), _context())
    assert message.replies[1] == "- [ ] Remember the milk"
    assert message.replies[2] == "⚠️ Couldn't save to Obsidian: disk on fire"
