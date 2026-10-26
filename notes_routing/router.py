"""Ask an LLM where a note belongs. Anything it says is checked against the real vault."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from llm.llm_util import get_llm_response
from notes_routing import context, vault_map

PROMPT = Path(__file__).parent / "prompts" / "route.jinja2"
CONFIDENCE_THRESHOLD = 0.75
MAX_TRANSCRIPT_CHARS = 6000
MAX_CANDIDATES = 3


@dataclass(frozen=True)
class Route:
    title: str | None
    folder: str | None = None
    confidence: float = 0.0
    candidates: list[str] = field(default_factory=list)
    new_folder: str | None = None
    reason: str = ""

    @property
    def confident(self) -> bool:
        return self.folder is not None and self.confidence >= CONFIDENCE_THRESHOLD


def safe_title(text: str | None) -> str | None:
    """A title that's also a valid, link-friendly file name on every device Obsidian syncs to."""
    if not text:
        return None
    cleaned = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", text)
    cleaned = " ".join(cleaned.split()).strip(" .")
    return cleaned[:80].rstrip(" .") or None


def safe_folder(text: str | None) -> str | None:
    """A relative folder path the vault can hold, or None for anything that escapes it."""
    if not text:
        return None
    parts = [safe_title(part) for part in str(text).split("/")]
    if not parts or any(p is None or p.startswith((".", "_")) for p in parts):
        return None
    return "/".join(parts)


def _json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError(f"No JSON object in router response: {text[:200]!r}")
    return json.loads(match.group(0))


def parse(text: str, known: set[str]) -> Route:
    data = _json_object(text)
    folder = data.get("folder") if data.get("folder") in known else None
    candidates = [c for c in data.get("candidates") or [] if c in known and c != folder]
    try:
        confidence = min(max(float(data.get("confidence") or 0), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.0
    new_folder = safe_folder(data.get("new_folder"))
    return Route(
        title=safe_title(data.get("title")),
        folder=folder,
        confidence=confidence if folder else 0.0,
        candidates=candidates[:MAX_CANDIDATES],
        new_folder=None if new_folder in known else new_folder,
        reason=str(data.get("reason") or ""),
    )


def route(transcript: str, hint: str | None, source: str) -> Route:
    folders = vault_map.folders()
    text = get_llm_response(str(PROMPT), {
        "source": source,
        "folders": folders,
        "hint": hint or "",
        "context": context.about(),
        "transcript": transcript[:MAX_TRANSCRIPT_CHARS],
    })
    return parse(text, {f.path for f in folders})
