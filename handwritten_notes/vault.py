"""Filing transcribed handwritten notes into the Obsidian vault.

Same vault, same write rules as :mod:`voice_notes.vault`: plain files, written via
temp file + rename, which ``obsidian-sync.service`` carries to every device.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from util.logging_util import setup_logger
from voice_notes.vault import free_stem, vault_dir, write_atomic

logger = setup_logger(__name__)

NOTES_FOLDER = "Handwritten Notes"
IMAGES_FOLDER = "images"


def notes_dir() -> Path:
    return vault_dir() / NOTES_FOLDER


@dataclass(frozen=True)
class SavedNote:
    note_path: Path
    image_paths: list[Path]


def render_note(*, when: datetime, model: str, image_names: list[str],
                caption: str | None, transcript: str) -> str:
    heading = f"# {caption}\n\n" if caption else ""
    embeds = "\n".join(f"![[{name}]]" for name in image_names)
    return (
        "---\n"
        f"created: {when.isoformat(timespec='seconds')}\n"
        f"pages: {len(image_names)}\n"
        "source: telegram\n"
        f"model: {model}\n"
        "tags:\n"
        "  - handwritten-note\n"
        "---\n"
        "\n"
        f"{heading}"
        f"{transcript}\n"
        "\n"
        "## Pages\n"
        "\n"
        f"{embeds}\n"
    )


def save_note(*, when: datetime, pages: list[tuple[bytes, str]], model: str,
              caption: str | None, transcript: str) -> SavedNote:
    """Write the page images and the note; images first, so no embed ever dangles.

    ``pages`` are ``(bytes, extension)`` pairs in page order.
    """
    stem = free_stem(notes_dir(), when)
    note_path = notes_dir() / f"{stem}.md"
    image_paths = [notes_dir() / IMAGES_FOLDER / f"{stem} p{i}.{ext}"
                   for i, (_, ext) in enumerate(pages, start=1)]

    for path, (data, _) in zip(image_paths, pages):
        write_atomic(path, data)
    write_atomic(note_path, render_note(
        when=when, model=model, image_names=[p.name for p in image_paths],
        caption=caption, transcript=transcript,
    ).encode("utf-8"))

    logger.info(f"Saved handwritten note {note_path.name} ({len(pages)} page(s))")
    return SavedNote(note_path=note_path, image_paths=image_paths)
