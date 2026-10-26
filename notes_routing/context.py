"""Background on the writer, read from a note in the vault, to help read their notes.

Names and jargon are where transcription goes wrong without anyone noticing: a
handwritten "Jim" reads confidently as "Sim", and nothing gets flagged as unsure.
``_Notes Context.md`` at the vault root says who the writer is, what they write
about, and, under a ``## Vocabulary`` heading, a bulleted list of names and terms.
It is written in Obsidian like any other note, so none of it lives in this repo.

The whole note goes into the transcription, figure and routing prompts; the
vocabulary list also goes to Whisper. A missing note just means no context, which
is what dev and tests get.
"""

import re

from voice_notes.vault import vault_dir

CONTEXT_NOTE = "_Notes Context.md"
VOCABULARY_HEADING = "vocabulary"
# Enough for a paragraph and a few dozen terms. It rides along on every call, so
# keep it a fraction of the ~1.5k tokens each page image already costs.
MAX_CONTEXT_CHARS = 1500
MAX_VOCABULARY_TERMS = 50

FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
HEADING = re.compile(r"^#+\s+(.*?)\s*$")
BULLET = re.compile(r"^\s*[-*+]\s+(.*?)\s*$")


def _read() -> str:
    path = vault_dir() / CONTEXT_NOTE
    if not path.is_file():
        return ""
    return FRONTMATTER.sub("", path.read_text(encoding="utf-8")).strip()


def about() -> str:
    """The note's text, capped, for an LLM prompt; '' if there is no note."""
    return _read()[:MAX_CONTEXT_CHARS]


def vocabulary() -> list[str]:
    """The bullets under the note's ``## Vocabulary`` heading, in order."""
    terms, inside = [], False
    for line in _read().splitlines():
        if heading := HEADING.match(line):
            inside = heading.group(1).lower() == VOCABULARY_HEADING
        elif inside and (bullet := BULLET.match(line)) and bullet.group(1):
            terms.append(bullet.group(1))
    return terms[:MAX_VOCABULARY_TERMS]
