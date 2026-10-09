"""Tests for voice_notes.vault -- where notes land and what they look like."""

from datetime import datetime

import pytest

from util.timezone import STOCKHOLM
from voice_notes import vault

WHEN = datetime(2026, 10, 9, 14, 32, 7, tzinfo=STOCKHOLM)


@pytest.fixture(autouse=True)
def tmp_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(tmp_path))
    return tmp_path


def _save(transcript="Buy more coffee.", when=WHEN):
    return vault.save_note(when=when, audio=b"OggS-fake", audio_ext="ogg",
                           duration_s=12.4, model="whisper-large-v3-turbo",
                           transcript=transcript)


def test_writes_note_and_audio_into_the_vault(tmp_vault):
    saved = _save()
    assert saved.note_path == tmp_vault / "Voice Notes" / "2026-10-09 1432.md"
    assert saved.audio_path == tmp_vault / "Voice Notes" / "audio" / "2026-10-09 1432.ogg"
    assert saved.audio_path.read_bytes() == b"OggS-fake"


def test_note_has_frontmatter_embed_and_transcript():
    text = _save().note_path.read_text()
    assert text.startswith("---\ncreated: 2026-10-09T14:32:07+02:00\nduration: 12\n")
    assert "source: telegram\n" in text
    assert "model: whisper-large-v3-turbo\n" in text
    assert "  - voice-note\n" in text
    assert "![[2026-10-09 1432.ogg]]" in text
    assert text.endswith("Buy more coffee.\n")


def test_same_minute_does_not_overwrite():
    first = _save("one")
    second = _save("two")
    third = _save("three")
    assert second.note_path.name == "2026-10-09 1432 (2).md"
    assert third.note_path.name == "2026-10-09 1432 (3).md"
    assert "![[2026-10-09 1432 (2).ogg]]" in second.note_path.read_text()
    assert first.note_path.read_text().endswith("one\n")


def test_leaves_no_temp_files(tmp_vault):
    _save()
    leftovers = [p for p in tmp_vault.rglob("*") if p.name.startswith(".")]
    assert leftovers == []


def test_unset_env_falls_back_to_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("OBSIDIAN_VAULT_DIR")
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path / "data"))
    assert vault.vault_dir() == tmp_path / "data" / "obsidian"
