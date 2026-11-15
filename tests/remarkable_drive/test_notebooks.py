"""Tests for notebook PDFs exported to Drive: template removal, rendering, filing."""

from datetime import datetime, timezone
from types import SimpleNamespace

import fitz
import pytest

from handwritten_notes import handwritten_bot
from notes_routing import telegram as routing
from remarkable_drive import notebooks
from remarkable_drive.watcher import DriveFile, Outcome
from tests.handwritten_notes.test_remarkable import ME, FakeBot

FOLDER = "Handwritten Notes"
NOTEBOOK = (445, 594)


def _notebook(*pages: str) -> bytes:
    """A notebook PDF; each page is 'dots', 'ink' (dots + a stroke), 'text' or 'blank'."""
    doc = fitz.open()
    for kind in pages:
        page = doc.new_page(width=NOTEBOOK[0], height=NOTEBOOK[1])
        if kind in ("dots", "ink"):
            shape = page.new_shape()
            for x in range(20, 440, 20):
                for y in range(20, 590, 20):
                    shape.draw_circle((x, y), 0.15)
                    shape.finish(fill=(0, 0, 0), color=None)
            shape.commit()
        if kind == "ink":
            shape = page.new_shape()
            shape.draw_bezier((50, 100), (120, 40), (200, 160), (300, 100))
            shape.finish(color=(0, 0, 0), width=1.27)
            shape.draw_line((50, 200), (300, 210))
            shape.finish(color=(0, 0, 0), width=1.27)
            shape.commit()
        if kind == "text":
            page.insert_text((50, 100), "A typed document")
    return doc.tobytes()


def _file(name="Standup.pdf", mime="application/pdf") -> DriveFile:
    return DriveFile(id="f1", name=name, mime_type=mime,
                     modified=datetime(2026, 11, 14, 16, 25, tzinfo=timezone.utc))


def test_ink_drawings_drops_the_template_and_keeps_the_strokes():
    with fitz.open(stream=_notebook("ink"), filetype="pdf") as doc:
        ink = notebooks.ink_drawings(doc[0])
    assert len(ink) == 2
    assert {round(d["width"], 2) for d in ink} == {1.27}


def test_render_pages_skips_blank_and_template_only_pages():
    pages = notebooks.render_pages(_notebook("dots", "ink", "blank", "text"))
    assert len(pages) == 2  # the inked page and the typed page
    assert all(p.mime == "image/png" and p.data.startswith(b"\x89PNG") for p in pages)


def test_rendered_page_has_no_dots_left():
    [page] = notebooks.render_pages(_notebook("ink"))
    pixmap = fitz.Pixmap(page.data)
    # A dot sits at (20, 20)pt; the strokes are far from it.
    x, y = int(20 * notebooks.ZOOM), int(20 * notebooks.ZOOM)
    assert pixmap.pixel(x, y) == (255, 255, 255)


@pytest.mark.parametrize("name, expected", [
    ("Standup.pdf", "Standup"),
    ("Standup (2).pdf", "Standup"),
    ("Q3 (draft).pdf", "Q3 (draft)"),
    (".pdf", "a notebook"),
])
def test_title(name, expected):
    assert notebooks.title(_file(name)) == expected


@pytest.fixture
def filing(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(tmp_path))
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(routing.router, "route", lambda *a: routing.router.Route(title=None))
    seen = []

    def fake_transcribe(pages, caption=None):
        seen.append((pages, caption))
        return "- [ ] Remember the milk"
    monkeypatch.setattr(handwritten_bot.transcribe, "transcribe", fake_transcribe)
    return SimpleNamespace(vault=tmp_path / FOLDER, seen=seen)


@pytest.mark.asyncio
async def test_handle_files_the_notebook(filing):
    bot = FakeBot()
    outcome = await notebooks.handle(bot, ME, _file(), _notebook("ink", "dots"))

    assert outcome is Outcome.DONE
    assert bot.sent[0].text == "📁 From the reMarkable: Standup (1 page)"
    [(pages, caption)] = filing.seen
    assert caption == "Standup" and len(pages) == 1
    assert "Remember the milk" in next(filing.vault.glob("*.md")).read_text()


@pytest.mark.asyncio
async def test_handle_blank_notebook_is_done_without_transcribing(filing):
    bot = FakeBot()
    assert await notebooks.handle(bot, ME, _file(), _notebook("dots")) is Outcome.DONE
    assert "nothing written" in bot.sent[0].text
    assert filing.seen == []


@pytest.mark.asyncio
async def test_handle_rejects_non_pdf(filing):
    bot = FakeBot()
    outcome = await notebooks.handle(bot, ME, _file("photo.png", "image/png"), b"")
    assert outcome is Outcome.REJECT
    assert filing.seen == []


@pytest.mark.asyncio
async def test_handle_asks_for_retry_when_transcription_fails(filing, monkeypatch):
    def broken(pages, caption=None):
        raise RuntimeError("model down")
    monkeypatch.setattr(handwritten_bot.transcribe, "transcribe", broken)
    assert await notebooks.handle(FakeBot(), ME, _file(), _notebook("ink")) is Outcome.RETRY
