"""Tests for the voice notes bot handler, with Telegram and the model faked."""

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from telegram.error import TimedOut

from voice_notes import voice_notes_bot as bot

ME = 42


class FakeMessage:
    def __init__(self, voice=None, audio=None):
        self.voice = voice
        self.audio = audio
        self.date = datetime(2026, 10, 9, 12, 32, tzinfo=timezone.utc)
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeFile:
    async def download_as_bytearray(self, **kwargs):
        return bytearray(b"OggS-fake")


class FakeBot:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    async def get_file(self, file_id, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise TimedOut()
        return FakeFile()


def _update(user_id=ME, **media):
    message = FakeMessage(**media)
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    return update, message


CONTEXT = SimpleNamespace(bot=FakeBot())
VOICE = SimpleNamespace(file_id="abc")


@pytest.fixture(autouse=True)
def fakes(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(bot, "get_telegram_user_id", lambda: ME)
    monkeypatch.setattr(bot.audio, "decode", lambda b: np.zeros(16_000 * 5, dtype=np.float32))
    monkeypatch.setattr(bot.transcribe, "transcribe", lambda s: "Remember the milk.")
    return tmp_path


@pytest.mark.asyncio
async def test_replies_with_transcript_and_files_the_note(fakes):
    update, message = _update(voice=VOICE)
    await bot.handle_voice(update, CONTEXT)

    assert message.replies == [
        "Transcribing…",
        "Remember the milk.",
        "📝 Saved to Voice Notes/2026-10-09 1432.md",
    ]
    note = fakes / "Voice Notes" / "2026-10-09 1432.md"
    assert note.read_text().endswith("Remember the milk.\n")
    assert (fakes / "Voice Notes" / "audio" / "2026-10-09 1432.ogg").read_bytes() == b"OggS-fake"


@pytest.mark.asyncio
async def test_download_is_retried_with_a_longer_timeout(fakes):
    flaky = FakeBot(failures=2)
    update, message = _update(voice=VOICE)
    await bot.handle_voice(update, SimpleNamespace(bot=flaky))

    assert len(flaky.calls) == 3
    assert all(c["read_timeout"] == bot.DOWNLOAD_TIMEOUT_SECONDS for c in flaky.calls)
    assert message.replies[1] == "Remember the milk."
    assert (fakes / "Voice Notes" / "2026-10-09 1432.md").exists()


@pytest.mark.asyncio
async def test_download_failure_says_so_not_transcription(fakes):
    dead = FakeBot(failures=bot.DOWNLOAD_ATTEMPTS)
    update, message = _update(voice=VOICE)
    await bot.handle_voice(update, SimpleNamespace(bot=dead))

    assert len(dead.calls) == bot.DOWNLOAD_ATTEMPTS
    assert message.replies[1].startswith("Couldn't download the voice note from Telegram")
    assert not (fakes / "Voice Notes").exists()


@pytest.mark.asyncio
async def test_rejects_other_users(fakes):
    update, message = _update(user_id=7, voice=VOICE)
    await bot.handle_voice(update, CONTEXT)
    assert message.replies == ["Unauthorised."]
    assert not (fakes / "Voice Notes").exists()


@pytest.mark.asyncio
async def test_audio_file_keeps_its_extension(fakes):
    update, message = _update(audio=SimpleNamespace(file_id="abc", file_name="memo.M4A"))
    await bot.handle_voice(update, CONTEXT)
    assert (fakes / "Voice Notes" / "audio" / "2026-10-09 1432.m4a").exists()


@pytest.mark.asyncio
async def test_transcript_still_sent_when_vault_write_fails(monkeypatch):
    def broken(**kwargs):
        raise OSError("disk on fire")
    monkeypatch.setattr(bot.vault, "save_note", broken)

    update, message = _update(voice=VOICE)
    await bot.handle_voice(update, CONTEXT)
    assert message.replies[1] == "Remember the milk."
    assert message.replies[2] == "⚠️ Couldn't save to Obsidian: disk on fire"


@pytest.mark.asyncio
async def test_transcription_failure_is_reported(monkeypatch, fakes):
    def broken(samples):
        raise RuntimeError("model exploded")
    monkeypatch.setattr(bot.transcribe, "transcribe", broken)

    update, message = _update(voice=VOICE)
    await bot.handle_voice(update, CONTEXT)
    assert message.replies == ["Transcribing…", "Transcription failed: model exploded"]
    assert not (fakes / "Voice Notes").exists()


@pytest.mark.asyncio
async def test_silence_is_still_filed(monkeypatch, fakes):
    monkeypatch.setattr(bot.transcribe, "transcribe", lambda s: "")
    update, message = _update(voice=VOICE)
    await bot.handle_voice(update, CONTEXT)
    assert message.replies[1] == "(no speech recognised)"
    assert (fakes / "Voice Notes" / "2026-10-09 1432.md").read_text().endswith(bot.NO_SPEECH + "\n")


def test_long_transcripts_are_split_on_spaces():
    text = " ".join(["word"] * 2000)  # ~10k chars
    parts = bot._split_message(text)
    assert all(len(p) <= bot.TELEGRAM_MAX_MESSAGE for p in parts)
    assert " ".join(parts) == text
