"""Annotated papers exported to ``reMarkable/Papers/Annotated`` → notes in the paper's stub.

1. **Which paper.** The export is named after the uploaded file, ``<id> - <title>.pdf``
   (plus `` (1)`` on a name clash), so the leading number is the article ID.
2. **The original** to compare against: the copy kept when it was uploaded
   (:func:`remarkable_drive.outbound.local_copy_path`), or failing that the file still
   in ``reMarkable/Papers/To read`` (how a paywalled PDF you uploaded by hand gets here).
3. **The marks** (:mod:`remarkable_drive.annotations`).
4. **Transcribe** the pen marks in one vision call: each is cropped ink-only and sent
   with the printed text it's anchored to. Pages you inserted go through the notebook
   transcription, one call each.
5. **Write the notes** into the stub's ``## Notes``, between
   ``<!-- remarkable:start -->`` and ``<!-- remarkable:end -->``: a re-export replaces
   that block and nothing else. The stub is marked ``status: read`` and moved to
   ``read/``.

Stubs are found by their ``triage_id`` frontmatter wherever you've moved them, then
by the path recorded on the paper, then by URL (stubs from before ``triage_id``).
A paper with no stub gets one.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import fitz

from content_screening.db_engine import get_session
from content_screening.orm_models import ArticleORM
from gcp_util import drive
from handwritten_notes import transcribe
from llm.llm_util import get_vision_response
from remarkable_drive import annotations as ann
from remarkable_drive.notebooks import _redraw, render_pages
from remarkable_drive.outbound import TO_READ, local_copy_path
from remarkable_drive.watcher import DriveFile, Outcome
from triage import obsidian
from util.logging_util import setup_logger
from voice_notes.vault import vault_dir, write_atomic

logger = setup_logger(__name__)

# Chosen over Sonnet 5.5 on the 2026-11-14 export: read "dot product?" where Sonnet read
# "lot product?", in ~9s, at a fraction of the price. Inserted pages still go through
# the notebook transcription's model (transcribe.MODEL).
MODEL = "xiaomi/mimo-v2.6-pro"
PROMPT = Path(__file__).parent / "prompts" / "annotations.jinja2"
# Must match TRIAGE_OBSIDIAN_INBOX_SUBDIR in triage.env: the bot doesn't read that file.
PAPERS_SUBDIR = "Papers"
READ_SUBDIR = "read"
IMAGES_SUBDIR = "images"
START = "<!-- remarkable:start -->"
END = "<!-- remarkable:end -->"
PLACEHOLDER = "<!-- (empty — to be filled when read) -->"
# Crops: rendered at this zoom with this much room (pt) round the ink.
CROP_ZOOM = 3.0
CROP_PAD = 6.0
# Marks per vision call.
BATCH = 15
# Printed text quoted for a note written beside it or next to a figure.
QUOTE_CHARS = 220

_ID = re.compile(r"^\s*(\d+)\s+-\s")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_COLOURS = {  # the tablet's highlighter palette, as far as seen
    (0.95, 0.62, 1.0): "pink",
    (1.0, 0.76, 0.55): "orange",
}
_WHERE = {
    "enclosed": "circled or looped round",
    "underline": "under",
    "beside": "written beside",
    "figure": "written next to the figure captioned",
    "cover": "written on the paper's cover sheet (general remarks)",
    "none": "written in an empty part of the page",
}


# --- Which paper, and its original --------------------------------------------


def paper_id(name: str) -> Optional[int]:
    """The article ID at the front of an export's filename."""
    match = _ID.match(name)
    return int(match.group(1)) if match else None


def load_original(article_id: int) -> Optional[bytes]:
    """The PDF that went to the tablet: the local copy, else the one still in To read."""
    local = local_copy_path(article_id)
    if local.exists():
        return local.read_bytes()
    folder = drive.ensure_folder(TO_READ)
    for item in drive.list_files(folder):
        if paper_id(item["name"]) == article_id and item["mimeType"] == "application/pdf":
            return drive.download_bytes(item["id"])
    return None


# --- Transcription ------------------------------------------------------------


@dataclass
class Transcribed:
    kind: str   # "note" | "mark"
    text: str


def crop(export: fitz.Document, mark: ann.Mark) -> bytes:
    """PNG of a pen mark's ink alone."""
    page = export[mark.export_index]
    rect = ann._bbox(mark.drawings) + (-CROP_PAD, -CROP_PAD, CROP_PAD, CROP_PAD)
    with _redraw(mark.drawings, page.rect.width, page.rect.height) as clean:
        clip = rect & clean[0].rect if rect.intersects(clean[0].rect) else rect
        return clean[0].get_pixmap(matrix=fitz.Matrix(CROP_ZOOM, CROP_ZOOM), clip=clip).tobytes("png")


def _quote(text: str, limit: int = QUOTE_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"


def _parse(reply: str, count: int) -> list[Transcribed]:
    text = reply.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    items = json.loads(text)
    by_n = {int(item["n"]): item for item in items if isinstance(item, dict) and "n" in item}
    out = []
    for n in range(1, count + 1):
        item = by_n.get(n)
        if item is None:
            out.append(Transcribed("note", "[not transcribed]"))
        else:
            out.append(Transcribed("mark" if item.get("kind") == "mark" else "note",
                                   str(item.get("text") or "").strip()))
    return out


def transcribe_marks(crops: list[bytes], marks: list[ann.Mark]) -> list[Transcribed]:
    """Each pen mark's writing (or a label for a pure mark), in batches of :data:`BATCH`."""
    out: list[Transcribed] = []
    for start in range(0, len(marks), BATCH):
        chunk = marks[start:start + BATCH]
        params = {"marks": [{"where": _WHERE.get(m.anchor, _WHERE["none"]),
                             "text": _quote(m.text, 400)} for m in chunk]}
        reply = get_vision_response(str(PROMPT), params,
                                    [(c, "image/png") for c in crops[start:start + BATCH]],
                                    model_name=MODEL)
        out += _parse(reply, len(chunk))
    return out


def transcribe_page(export: fitz.Document, index: int) -> tuple[str, Optional[bytes]]:
    """An inserted page through the notebook transcription: (markdown, png)."""
    single = fitz.open()
    single.insert_pdf(export, from_page=index, to_page=index)
    pages = render_pages(single.tobytes())
    if not pages:
        return "", None
    return transcribe.transcribe([(pages[0].data, pages[0].mime)]), pages[0].data


# --- The note -----------------------------------------------------------------


@dataclass
class Notes:
    """Everything that goes between the markers."""
    marks: list[ann.Mark]
    transcribed: dict[int, Transcribed]   # id(mark) → its transcription (pen marks only)
    images: dict[int, str]                # id(mark) → embedded crop's filename
    pages: list[tuple[ann.InsertedPage, str, Optional[str]]]  # page, transcript, image name


def _colour_name(colour: Optional[tuple]) -> str:
    if colour is None:
        return "highlight"
    return _COLOURS.get(tuple(round(c, 2) for c in colour), "rgb" + str(colour))


def _mark_lines(mark: ann.Mark, notes: Notes, quoted: bool = True) -> list[str]:
    """A mark as Markdown paragraphs: the printed text quoted, then what you wrote.

    Paragraphs, not lines: a line straight after a ``>`` quote would join the quote.
    ``quoted=False`` leaves the quote out (a second note on the same figure).
    """
    if mark.kind == "highlight":
        return [f'> "{" ".join(mark.text.split())}" <!-- {_colour_name(mark.colour)} -->']

    parts = []
    if quoted and mark.anchor in ("enclosed", "underline"):
        parts.append(f'> "{" ".join(mark.text.split())}"')
    elif quoted and mark.anchor in ("beside", "figure") and mark.text:
        parts.append(f"> {_quote(mark.text)}")
    written = notes.transcribed.get(id(mark))
    line = ""
    if written is not None:
        if written.kind == "mark":
            line = f"*({written.text or 'marked'})*"
        elif written.text:
            line = written.text
    image = notes.images.get(id(mark))
    if image:
        line = f"{line} ![[{image}|240]]".strip()
    if line:
        parts.append(line)
    return parts


def _section(marks: list[ann.Mark], notes: Notes) -> list[str]:
    out, last = [], None
    for mark in marks:
        same = mark.kind == "pen" and mark.anchor == "figure" and last == (mark.anchor, mark.text)
        for paragraph in _mark_lines(mark, notes, quoted=not same):
            out += [paragraph, ""]
        last = (mark.anchor, mark.text)
    return out


def render_block(notes: Notes, when: date) -> str:
    """The generated notes, markers included."""
    parts = [START,
             f"<!-- From the reMarkable export on {when.isoformat()}. Edits between these "
             "markers are overwritten when the paper is exported again. -->", ""]

    cover = [m for m in notes.marks if m.page is None]
    if cover:
        parts += ["**General**", ""] + _section(cover, notes)

    pages = sorted({m.page for m in notes.marks if m.page is not None})
    for page in pages:
        parts += [f"**p.{page}**", ""] + _section([m for m in notes.marks if m.page == page], notes)

    if notes.pages:
        parts += ["### Notes pages", ""]
        for inserted, text, image in notes.pages:
            where = f"after p.{inserted.after_page}" if inserted.after_page else "before p.1"
            parts += [f"**Page {where}**", "", text or "_(no text recognised)_", ""]
            if image:
                parts += [f"![[{image}|300]]", ""]

    if not notes.marks and not notes.pages:
        parts += ["_No annotations._", ""]
    parts.append(END)
    return "\n".join(parts)


def splice(stub: str, block: str) -> str:
    """``stub`` with ``block`` in place of any earlier one, else at the top of ``## Notes``."""
    if START in stub and END in stub:
        before, rest = stub.split(START, 1)
        after = rest.split(END, 1)[1]
        return before + block + after
    stub = stub.replace(PLACEHOLDER + "\n", "", 1).replace(PLACEHOLDER, "", 1)
    match = re.search(r"^## Notes[ \t]*\n", stub, re.MULTILINE)
    if match is None:
        return stub.rstrip("\n") + "\n\n## Notes\n\n" + block + "\n"
    head, tail = stub[:match.end()], stub[match.end():].lstrip("\n")
    return head + "\n" + block + "\n" + ("\n" + tail if tail else "")


def _set_frontmatter(stub: str, key: str, value: str, after: str = "title") -> str:
    """Set one top-level frontmatter field by editing its line, so the rest keeps its formatting."""
    match = _FRONTMATTER.match(stub)
    if match is None:
        return f"---\n{key}: {value}\n---\n\n" + stub
    lines = match.group(1).split("\n")
    for i, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[i] = f"{key}: {value}"
            break
    else:
        at = next((i + 1 for i, line in enumerate(lines) if line.startswith(f"{after}:")), 0)
        # A multi-line value (folded title) continues on indented lines.
        while at and at < len(lines) and lines[at].startswith((" ", "\t")):
            at += 1
        lines.insert(at, f"{key}: {value}")
    return "---\n" + "\n".join(lines) + "\n---\n" + stub[match.end():]


def _frontmatter_value(text: str, key: str) -> Optional[str]:
    match = _FRONTMATTER.match(text)
    if match is None:
        return None
    for line in match.group(1).split("\n"):
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return None


def find_stub(vault: Path, paper: ArticleORM) -> Optional[Path]:
    """The paper's stub: by ``triage_id``, then the recorded path, then URL."""
    papers = vault / PAPERS_SUBDIR
    stubs = sorted(papers.rglob("*.md")) if papers.exists() else []
    texts = {}
    for path in stubs:
        try:
            texts[path] = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _frontmatter_value(texts[path], "triage_id") == str(paper.id):
            return path
    if paper.obsidian_path and (vault / paper.obsidian_path).exists():
        return vault / paper.obsidian_path
    if paper.url:
        for path, text in texts.items():
            if _frontmatter_value(text, "url") == paper.url:
                return path
    return None


def write_notes(vault: Path, paper: ArticleORM, block: str) -> Path:
    """Put ``block`` into the paper's stub, mark it read and move it to ``read/``; its new path."""
    stub = find_stub(vault, paper)
    if stub is None:
        stub = vault / obsidian.write_stub(vault, paper, PAPERS_SUBDIR)
    text = splice(stub.read_text(encoding="utf-8"), block)
    text = _set_frontmatter(text, "triage_id", str(paper.id))
    text = _set_frontmatter(text, "status", "read")
    write_atomic(stub, text.encode("utf-8"))

    read_dir = vault / PAPERS_SUBDIR / READ_SUBDIR
    if stub.parent != read_dir:
        read_dir.mkdir(parents=True, exist_ok=True)
        target = read_dir / stub.name
        if not target.exists():
            stub.rename(target)
            stub = target
    return stub


# --- The handler --------------------------------------------------------------


@dataclass
class Result:
    note: Path
    highlights: int
    notes: int
    pages: int
    unmatched: int


def process(article_id: int, data: bytes, original: bytes, when: date) -> Result:
    """Read the export, transcribe, and write the notes into the stub. Blocking."""
    vault = vault_dir()
    with fitz.open(stream=data, filetype="pdf") as export, \
            fitz.open(stream=original, filetype="pdf") as orig:
        found = ann.read(export, orig)
        pens = [m for m in found.marks if m.kind == "pen"]
        crops = [crop(export, m) for m in pens]
        written = transcribe_marks(crops, pens) if pens else []
        pages = [(p, *transcribe_page(export, p.index)) for p in found.inserted]

    images_dir = vault / PAPERS_SUBDIR / IMAGES_SUBDIR
    images_dir.mkdir(parents=True, exist_ok=True)
    image_names: dict[int, str] = {}
    counters: dict[object, int] = {}
    for mark, png in zip(pens, crops):
        where = f"p{mark.page}" if mark.page is not None else "cover"
        counters[where] = counters.get(where, 0) + 1
        name = f"paper-{article_id}-{where}-{counters[where]}.png"
        write_atomic(images_dir / name, png)
        image_names[id(mark)] = name
    page_entries = []
    for n, (inserted, text, png) in enumerate(pages, 1):
        name = None
        if png:
            name = f"paper-{article_id}-page-{n}.png"
            write_atomic(images_dir / name, png)
        page_entries.append((inserted, text, name))

    notes = Notes(found.marks, {id(m): t for m, t in zip(pens, written)}, image_names, page_entries)
    block = render_block(notes, when)

    with get_session() as session:
        paper = session.get(ArticleORM, article_id)
        note = write_notes(vault, paper, block)
        paper.obsidian_path = str(note.relative_to(vault))

    return Result(note=note,
                  highlights=sum(1 for m in found.marks if m.kind == "highlight"),
                  notes=len(pens), pages=len(found.inserted), unmatched=len(found.unmatched))


def _exists(article_id: int) -> Optional[str]:
    with get_session() as session:
        paper = session.get(ArticleORM, article_id)
        return paper.title if paper else None


async def handle(bot, chat_id: int, file: DriveFile, data: bytes) -> Outcome:
    if file.mime_type != "application/pdf":
        await bot.send_message(chat_id, f"📄 {file.name} in Papers/Annotated isn't a PDF — "
                                        "moved it to reMarkable/Failed.")
        return Outcome.REJECT

    article_id = paper_id(file.name)
    title = await asyncio.to_thread(_exists, article_id) if article_id is not None else None
    if title is None:
        await bot.send_message(
            chat_id, f"📄 Can't tell which paper {file.name} is: it should be named "
                     "`<id> - <title>.pdf`, as uploaded. Moved it to reMarkable/Failed; "
                     "rename it and move it back to Papers/Annotated to retry.")
        return Outcome.REJECT

    original = await asyncio.to_thread(load_original, article_id)
    if original is None:
        await bot.send_message(
            chat_id, f"📄 No original to compare {file.name} against (no local copy, nothing "
                     "in Papers/To read). Moved it to reMarkable/Failed.")
        return Outcome.REJECT

    result = await asyncio.to_thread(process, article_id, data, original,
                                     file.modified.date())
    summary = ", ".join(part for part in (
        _count(result.highlights, "highlight"), _count(result.notes, "note"),
        _count(result.pages, "page of notes", "pages of notes")) if part) or "no annotations"
    vault = vault_dir()
    message = f"📄 Read: {title}\n{summary} → {result.note.relative_to(vault)}"
    if result.unmatched:
        message += (f"\n⚠️ {_count(result.unmatched, 'page')} didn't match the original "
                    "and were skipped.")
    await bot.send_message(chat_id, message)
    return Outcome.DONE


def _count(n: int, one: str, many: Optional[str] = None) -> str:
    if not n:
        return ""
    return f"1 {one}" if n == 1 else f"{n} {many or one + 's'}"
