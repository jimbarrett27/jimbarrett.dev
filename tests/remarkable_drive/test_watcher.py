"""Tests for the Drive watcher's dispatch, moves and retry accounting (Drive faked)."""

from types import SimpleNamespace

import pytest

from remarkable_drive import watcher
from remarkable_drive.watcher import Outcome
from tests.handwritten_notes.test_remarkable import ME, FakeBot

NOTES = f"{watcher.ROOT}/Notes"


class FakeDrive:
    def __init__(self, files):
        self.folders = {NOTES: "notes", watcher.DONE: "done", watcher.FAILED: "failed"}
        self.location = {f["id"]: "notes" for f in files}
        self.files = {f["id"]: f for f in files}

    def ensure_folder(self, path):
        return self.folders[path]

    def list_files(self, folder_id):
        return [self.files[i] for i, where in self.location.items() if where == folder_id]

    def download_bytes(self, file_id):
        return f"content of {file_id}".encode()

    def move_file(self, file_id, folder_id):
        self.location[file_id] = folder_id


def _item(file_id, modified="2026-11-14T16:25:19.943Z"):
    return {"id": file_id, "name": f"{file_id}.pdf", "mimeType": "application/pdf",
            "modifiedTime": modified}


@pytest.fixture
def setup(monkeypatch):
    def install(files, outcomes):
        fake = FakeDrive(files)
        for name in ("ensure_folder", "list_files", "download_bytes", "move_file"):
            monkeypatch.setattr(watcher.drive, name, getattr(fake, name))
        monkeypatch.setattr(watcher, "_folder_ids", {})
        monkeypatch.setattr(watcher, "_attempts", {})
        monkeypatch.setattr(watcher, "get_telegram_user_id", lambda: ME)
        handled = []

        async def handler(bot, chat_id, file, data):
            handled.append((file.id, data))
            outcome = outcomes[file.id]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        monkeypatch.setattr(watcher, "_handlers", lambda: {NOTES: handler})
        bot = FakeBot()
        return SimpleNamespace(drive=fake, handled=handled, bot=bot,
                               context=SimpleNamespace(bot=bot))
    return install


@pytest.mark.asyncio
async def test_outcomes_move_files(setup):
    s = setup([_item("ok"), _item("bad"), _item("again")],
              {"ok": Outcome.DONE, "bad": Outcome.REJECT, "again": Outcome.RETRY})
    await watcher.poll(s.context)

    assert s.drive.location == {"ok": "done", "bad": "failed", "again": "notes"}
    assert ("ok", b"content of ok") in s.handled


@pytest.mark.asyncio
async def test_oldest_first(setup):
    s = setup([_item("new", "2026-11-14T17:00:00Z"), _item("old", "2026-11-14T09:00:00Z")],
              {"new": Outcome.DONE, "old": Outcome.DONE})
    await watcher.poll(s.context)
    assert [file_id for file_id, _ in s.handled] == ["old", "new"]


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts(setup):
    s = setup([_item("flaky")], {"flaky": RuntimeError("boom")})
    for _ in range(watcher.MAX_ATTEMPTS - 1):
        await watcher.poll(s.context)
        assert s.drive.location["flaky"] == "notes"

    await watcher.poll(s.context)
    assert s.drive.location["flaky"] == "failed"
    assert "Giving up on flaky.pdf" in s.bot.sent[-1].text
    assert watcher._attempts == {}


@pytest.mark.asyncio
async def test_listing_failure_is_survived(setup, monkeypatch):
    s = setup([_item("ok")], {"ok": Outcome.DONE})

    def broken(folder_id):
        raise RuntimeError("Drive down")
    monkeypatch.setattr(watcher.drive, "list_files", broken)
    await watcher.poll(s.context)
    assert s.handled == []
