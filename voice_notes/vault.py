"""Filing voice notes into the Obsidian vault.

The bot only writes plain files; ``obsidian-sync.service`` (``ob sync
--continuous``) carries them to every device. The vault location comes from
``OBSIDIAN_VAULT_DIR``. Unset -- dev and tests -- it falls back to a folder under
:func:`util.paths.data_dir`, so nothing but the server ever touches the real vault.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from util.logging_util import setup_logger
from util.paths import data_path

logger = setup_logger(__name__)

NOTES_FOLDER = "Voice Notes"
AUDIO_FOLDER = "audio"


def vault_dir() -> Path:
    configured = os.environ.get("OBSIDIAN_VAULT_DIR")
    return Path(configured).expanduser() if configured else data_path("obsidian")


def notes_dir() -> Path:
    return vault_dir() / NOTES_FOLDER


@dataclass(frozen=True)
class SavedNote:
    note_path: Path
    audio_path: Path


def free_stem(folder: Path, when: datetime) -> str:
    """'2026-10-09 1432', or '2026-10-09 1432 (2)' etc. if that minute is taken in ``folder``."""
    base = when.strftime("%Y-%m-%d %H%M")
    stem, n = base, 1
    while (folder / f"{stem}.md").exists():
        n += 1
        stem = f"{base} ({n})"
    return stem


def write_atomic(path: Path, data: bytes) -> None:
    """Write via a hidden temp file + rename, so sync never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def render_note(*, when: datetime, duration_s: float, model: str,
                audio_name: str, transcript: str) -> str:
    return (
        "---\n"
        f"created: {when.isoformat(timespec='seconds')}\n"
        f"duration: {round(duration_s)}\n"
        "source: telegram\n"
        f"model: {model}\n"
        "tags:\n"
        "  - voice-note\n"
        "---\n"
        "\n"
        f"![[{audio_name}]]\n"
        "\n"
        f"{transcript}\n"
    )


def save_note(*, when: datetime, audio: bytes, audio_ext: str, duration_s: float,
              model: str, transcript: str) -> SavedNote:
    """Write the audio and its transcript note; audio first, so the embed never dangles."""
    stem = free_stem(notes_dir(), when)
    audio_path = notes_dir() / AUDIO_FOLDER / f"{stem}.{audio_ext}"
    note_path = notes_dir() / f"{stem}.md"

    write_atomic(audio_path, audio)
    write_atomic(note_path, render_note(
        when=when, duration_s=duration_s, model=model,
        audio_name=audio_path.name, transcript=transcript,
    ).encode("utf-8"))

    logger.info(f"Saved voice note {note_path.name} ({duration_s:.0f}s)")
    return SavedNote(note_path=note_path, audio_path=audio_path)
