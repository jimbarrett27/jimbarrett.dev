"""Annotated paper → notes in its Obsidian stub. The vision model is faked throughout."""

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from content_screening import db_engine
from content_screening.orm_models import ArticleORM, Base
from remarkable_drive import reading
from remarkable_drive.watcher import DriveFile, Outcome
from tests.triage.test_obsidian import make_paper
from triage import obsidian

FIXTURES = Path(__file__).parent / "fixtures"


# --- Naming -------------------------------------------------------------------


@pytest.mark.parametrize("name, expected", [
    ("42 - A Great Paper.pdf", 42),
    ("42 - A Great Paper (1).pdf", 42),
    ("7 - x.pdf", 7),
    ("A Great Paper.pdf", None),
    ("2024 report.pdf", None),
])
def test_paper_id(name, expected):
    assert reading.paper_id(name) == expected


# --- Splicing into the stub ---------------------------------------------------


BLOCK = f"{reading.START}\nnew notes\n{reading.END}"


def test_first_export_goes_at_the_top_of_notes_and_drops_the_placeholder():
    stub = obsidian.build_stub_markdown(make_paper())
    stub += "- my own note\n"
    out = reading.splice(stub, BLOCK)
    assert reading.PLACEHOLDER not in out
    notes = out.split("## Notes\n", 1)[1]
    assert notes.index("new notes") < notes.index("- my own note")


def test_reexport_replaces_only_the_block():
    stub = f"# T\n\nabove\n\n## Notes\n\n{reading.START}\nold\n{reading.END}\n\nmine\n"
    out = reading.splice(stub, BLOCK)
    assert "old" not in out
    assert out == f"# T\n\nabove\n\n## Notes\n\n{BLOCK}\n\nmine\n"


def test_stub_without_notes_heading_gets_one():
    assert reading.splice("# T\n", BLOCK) == f"# T\n\n## Notes\n\n{BLOCK}\n"


def test_frontmatter_lines_are_edited_in_place():
    stub = "---\ntitle: T\nauthors:\n- 'A, B'\nstatus: unread\n---\n\nbody\n"
    out = reading._set_frontmatter(stub, "status", "read")
    out = reading._set_frontmatter(out, "triage_id", "9")
    assert out == "---\ntitle: T\ntriage_id: 9\nauthors:\n- 'A, B'\nstatus: read\n---\n\nbody\n"


# --- Finding the stub ---------------------------------------------------------


def _stub(vault: Path, sub: str, name: str, **fields) -> Path:
    path = vault / reading.PAPERS_SUBDIR / sub / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = "\n".join(f"{k}: {v}" for k, v in fields.items())
    path.write_text(f"---\n{fm}\n---\n\n## Notes\n", encoding="utf-8")
    return path


def test_stub_found_by_triage_id_after_being_moved(tmp_path):
    moved = _stub(tmp_path, "somewhere", "a.md", title="A", triage_id=5)
    paper = make_paper(id=5, obsidian_path="Papers/unread/a.md")
    assert reading.find_stub(tmp_path, paper) == moved


def test_old_stub_found_by_url(tmp_path):
    old = _stub(tmp_path, "read", "b.md", title="B", url="'https://arxiv.org/abs/2401.00001'")
    assert reading.find_stub(tmp_path, make_paper(id=5)) == old


def test_write_notes_marks_read_and_moves(tmp_path):
    paper = make_paper(id=5)
    rel = obsidian.write_stub(tmp_path, paper, reading.PAPERS_SUBDIR)
    note = reading.write_notes(tmp_path, make_paper(id=5, obsidian_path=rel), BLOCK)
    assert note.parent == tmp_path / "Papers" / "read"
    assert not (tmp_path / rel).exists()
    text = note.read_text()
    assert "status: read" in text and "triage_id: 5" in text and "new notes" in text


def test_write_notes_creates_a_missing_stub(tmp_path):
    note = reading.write_notes(tmp_path, make_paper(id=5), BLOCK)
    assert note.parent.name == "read"
    assert "new notes" in note.read_text()


# --- Transcription replies ----------------------------------------------------


def test_parse_tolerates_fences_and_missing_items():
    reply = '```json\n[{"n": 2, "kind": "mark", "text": "circled"}]\n```'
    out = reading._parse(reply, 2)
    assert out[0].text == "[not transcribed]"
    assert (out[1].kind, out[1].text) == ("mark", "circled")


# --- End to end on the fixture ------------------------------------------------


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    db_engine.set_engine(engine)
    yield
    db_engine.reset_engine()


@pytest.fixture
def vault(tmp_path, monkeypatch):
    path = tmp_path / "vault"
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(path))
    return path


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def vision(template, params, images, model_name):
        calls.append((params, len(images)))
        replies = [{"n": 1, "kind": "mark", "text": "circled"},
                   {"n": 2, "kind": "note", "text": "CREMLS?"},
                   {"n": 3, "kind": "note", "text": "dunno?"},
                   {"n": 4, "kind": "mark", "text": "bracket"}]
        return json.dumps(replies[:len(images)])

    monkeypatch.setattr(reading, "get_vision_response", vision)
    monkeypatch.setattr(reading.transcribe, "transcribe", lambda pages, caption=None: "page notes")
    return calls


def _add_paper(**overrides) -> None:
    with db_engine.get_session() as session:
        session.add(make_paper(id=12, title="Duplicate detection", **overrides))


def test_process_writes_the_notes(db, vault, fake_llm):
    _add_paper()
    result = reading.process(12, (FIXTURES / "annotated_export.pdf").read_bytes(),
                             (FIXTURES / "annotated_original.pdf").read_bytes(), date(2026, 11, 15))

    assert (result.highlights, result.notes, result.pages) == (2, 4, 1)
    (params, images), = fake_llm
    assert images == 4
    assert [m["where"] for m in params["marks"]][:2] == ["circled or looped round", "written beside"]

    text = result.note.read_text()
    block = text.split(reading.START)[1].split(reading.END)[0]
    assert block.index("**p.1**") < block.index("**p.2**") < block.index("**p.3**")
    assert '> "referred [2], and they remain' in block
    assert "*(circled)*" in block and "CREMLS?" in block and "dunno?" in block
    assert '<!-- pink -->' in block and '<!-- orange -->' in block
    assert "### Notes pages" in block and "**Page after p.3**" in block and "page notes" in block
    assert "*(circled)* ![[paper-12-p1-1.png|240]]" in block
    # What you wrote is its own paragraph, not a continuation of the quote.
    assert "vigiMatch2025.\n\nCREMLS? ![[" in block
    # Two notes beside one figure quote its caption once.
    assert block.count("> Figure 1. Schematic") == 1
    assert (vault / "Papers" / "images" / "paper-12-p1-1.png").exists()
    assert (vault / "Papers" / "images" / "paper-12-page-1.png").exists()

    with db_engine.get_session() as session:
        assert session.get(ArticleORM, 12).obsidian_path == str(result.note.relative_to(vault))


def test_reprocessing_replaces_the_block(db, vault, fake_llm):
    _add_paper()
    args = ((FIXTURES / "annotated_export.pdf").read_bytes(),
            (FIXTURES / "annotated_original.pdf").read_bytes(), date(2026, 11, 15))
    first = reading.process(12, *args)
    first.note.write_text(first.note.read_text() + "\nmy thoughts\n")
    second = reading.process(12, *args)
    text = second.note.read_text()
    assert text.count(reading.START) == 1 and "my thoughts" in text


# --- The watcher handler ------------------------------------------------------


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append(text)


def _file(name, mime="application/pdf"):
    return DriveFile("f1", name, mime, datetime(2026, 11, 15, tzinfo=timezone.utc))


def test_handle_rejects_an_unnamed_export(db):
    bot = FakeBot()
    outcome = asyncio.run(reading.handle(bot, 1, _file("scan.pdf"), b""))
    assert outcome is Outcome.REJECT
    assert "Can't tell which paper" in bot.sent[0]


def test_handle_rejects_without_an_original(db, monkeypatch):
    _add_paper()
    monkeypatch.setattr(reading, "load_original", lambda article_id: None)
    bot = FakeBot()
    outcome = asyncio.run(reading.handle(bot, 1, _file("12 - Duplicate detection.pdf"), b""))
    assert outcome is Outcome.REJECT
    assert "No original" in bot.sent[0]


def test_handle_reports_what_it_wrote(db, vault, fake_llm, monkeypatch):
    _add_paper()
    monkeypatch.setattr(reading, "load_original",
                        lambda article_id: (FIXTURES / "annotated_original.pdf").read_bytes())
    bot = FakeBot()
    data = (FIXTURES / "annotated_export.pdf").read_bytes()
    outcome = asyncio.run(reading.handle(bot, 1, _file("12 - Duplicate detection (1).pdf"), data))
    assert outcome is Outcome.DONE
    assert bot.sent[0].startswith("📄 Read: Duplicate detection\n2 highlights, 4 notes, 1 page of notes")


def test_load_original_falls_back_to_to_read(monkeypatch, tmp_path):
    monkeypatch.setattr(reading, "local_copy_path", lambda article_id: tmp_path / "missing.pdf")
    monkeypatch.setattr(reading.drive, "ensure_folder", lambda path: "folder")
    monkeypatch.setattr(reading.drive, "list_files", lambda folder: [
        {"id": "a", "name": "3 - Other.pdf", "mimeType": "application/pdf"},
        {"id": "b", "name": "12 - Mine.pdf", "mimeType": "application/pdf"}])
    monkeypatch.setattr(reading.drive, "download_bytes", lambda file_id: file_id.encode())
    assert reading.load_original(12) == b"b"
