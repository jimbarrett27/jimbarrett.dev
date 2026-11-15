"""Tests for sending kept papers to the reMarkable: PDF lookup, cover page, upload."""

from types import SimpleNamespace

import fitz
import pytest
import requests

from remarkable_drive import outbound
from tests.triage.test_obsidian import make_paper


def _pdf(pages=2) -> bytes:
    doc = fitz.open()
    for n in range(pages):
        doc.new_page().insert_text((72, 72), f"Original page {n + 1}")
    return doc.tobytes()


# --- find_pdf_url -------------------------------------------------------------


def test_arxiv_paper_uses_arxiv_pdf():
    paper = make_paper(source_type="arxiv", external_id="2401.00001v2")
    assert outbound.find_pdf_url(paper) == "https://arxiv.org/pdf/2401.00001v2"


def test_arxiv_doi_uses_arxiv_pdf():
    paper = make_paper(source_type="openalex", external_id="W1", doi="10.48550/arxiv.2401.00001")
    assert outbound.find_pdf_url(paper) == "https://arxiv.org/pdf/2401.00001"


@pytest.fixture
def openalex(monkeypatch):
    from content_screening import openalex as oa
    calls = []

    def install(work=None, error=None):
        def fake_get(path, params, mailto):
            calls.append(path)
            if error:
                raise error
            return work
        monkeypatch.setattr(oa, "_get", fake_get)
        return calls
    return install


def test_openalex_best_location(openalex):
    calls = openalex({"best_oa_location": {"pdf_url": "https://x/best.pdf"},
                      "locations": [{"pdf_url": "https://x/other.pdf"}]})
    paper = make_paper(source_type="openalex", external_id="W9", doi="10.1/abc",
                       metadata_={"openalex_id": "W9"})
    assert outbound.find_pdf_url(paper) == "https://x/best.pdf"
    assert calls == ["works/W9"]


def test_openalex_falls_back_to_any_location_and_doi(openalex):
    calls = openalex({"best_oa_location": None,
                      "locations": [{"pdf_url": None}, {"pdf_url": "https://x/repo.pdf"}]})
    paper = make_paper(source_type="rss", external_id="r1", doi="10.1/abc", metadata_={})
    assert outbound.find_pdf_url(paper) == "https://x/repo.pdf"
    assert calls == ["works/doi:10.1/abc"]


def test_openalex_no_pdf(openalex):
    openalex({"best_oa_location": {"pdf_url": None}, "locations": []})
    paper = make_paper(source_type="rss", external_id="r1", doi="10.1/abc", metadata_={})
    assert outbound.find_pdf_url(paper) is None


def test_openalex_unknown_work_is_no_pdf(openalex):
    openalex(error=requests.HTTPError(response=SimpleNamespace(status_code=404)))
    paper = make_paper(source_type="rss", external_id="r1", doi="10.1/abc", metadata_={})
    assert outbound.find_pdf_url(paper) is None


def test_no_identifiers_is_no_pdf():
    paper = make_paper(source_type="rss", external_id="r1", doi=None, metadata_={})
    assert outbound.find_pdf_url(paper) is None


# --- fetch_pdf ----------------------------------------------------------------


@pytest.mark.parametrize("status, content, expected", [
    (200, b"%PDF-1.7 ...", b"%PDF-1.7 ..."),
    (200, b"<html>Sign in to read</html>", None),
    (403, b"Forbidden", None),
])
def test_fetch_pdf(monkeypatch, status, content, expected):
    response = SimpleNamespace(status_code=status, content=content, raise_for_status=lambda: None)
    monkeypatch.setattr(outbound.requests, "get", lambda *a, **k: response)
    assert outbound.fetch_pdf("https://x/p.pdf") == expected


def test_fetch_pdf_server_error_raises(monkeypatch):
    def raise_for_status():
        raise requests.HTTPError("503")
    response = SimpleNamespace(status_code=503, content=b"", raise_for_status=raise_for_status)
    monkeypatch.setattr(outbound.requests, "get", lambda *a, **k: response)
    with pytest.raises(requests.HTTPError):
        outbound.fetch_pdf("https://x/p.pdf")


# --- cover page ---------------------------------------------------------------


def test_cover_page_contents():
    paper = make_paper(id=77, metadata_={"venue": "JMIR AI", "publication_date": "2026-01-14"},
                       surfaced_by=["topic"])
    paper.rubric_answers = [{"statement": "About fraud", "answer": 2, "justification": "AML."}]
    with fitz.open(stream=outbound.build_cover(paper), filetype="pdf") as doc:
        assert doc.page_count == 1
        assert doc[0].rect == outbound.A4
        text = " ".join(doc[0].get_text().split())
    for expected in (paper.title, "Score 0.60", paper.llm_reasoning, "JMIR AI · 2026-01-14",
                     "About fraud", "strongly agree", "AML.", f"{outbound.COVER_MARKER} · paper 77"):
        assert expected in text


def test_cover_ignores_malformed_rubric():
    paper = make_paper()
    paper.rubric_answers = {"not": "a list"}
    with fitz.open(stream=outbound.build_cover(paper), filetype="pdf") as doc:
        assert "Rubric" not in doc[0].get_text()


def test_with_cover_prepends_one_page():
    with fitz.open(stream=outbound.with_cover(make_paper(), _pdf(3)), filetype="pdf") as doc:
        assert doc.page_count == 4
        assert outbound.COVER_MARKER in doc[0].get_text()
        assert "Original page 1" in doc[1].get_text()


@pytest.mark.parametrize("title, expected", [
    ("Short", "5 - Short.pdf"),
    ('A/B: "testing"?', "5 - A B testing.pdf"),
    ("word " * 30, "5 - " + " ".join(["word"] * 12) + ".pdf"),
])
def test_drive_filename(title, expected):
    assert outbound.drive_filename(make_paper(id=5, title=title)) == expected


# --- send_to_tablet -----------------------------------------------------------


@pytest.fixture
def tablet(monkeypatch, tmp_path):
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path))
    folder = {"files": []}
    uploads = []
    monkeypatch.setattr(outbound.drive, "ensure_folder", lambda path: "toread")
    monkeypatch.setattr(outbound.drive, "list_files", lambda folder_id: folder["files"])

    def upload(path, folder_id, name=None):
        uploads.append((path.read_bytes(), folder_id, name))
        return f"drive-{len(uploads)}"
    monkeypatch.setattr(outbound.drive, "upload_file", upload)
    monkeypatch.setattr(outbound, "fetch_pdf", lambda url: _pdf())
    return SimpleNamespace(folder=folder, uploads=uploads, data=tmp_path)


def test_send_uploads_with_cover_and_keeps_a_copy(tablet):
    paper = make_paper(id=12, title="Fraud graphs")
    assert outbound.send_to_tablet(paper) == "drive-1"

    [(data, folder_id, name)] = tablet.uploads
    assert (folder_id, name) == ("toread", "12 - Fraud graphs.pdf")
    assert (tablet.data / "papers" / "12.pdf").read_bytes() == data
    with fitz.open(stream=data, filetype="pdf") as doc:
        assert doc.page_count == 3


def test_send_reuses_an_existing_upload(tablet):
    tablet.folder["files"] = [{"id": "already", "name": "12 - Fraud graphs.pdf"}]
    assert outbound.send_to_tablet(make_paper(id=12, title="Fraud graphs")) == "already"
    assert tablet.uploads == []


def test_send_without_pdf_returns_none(tablet, monkeypatch):
    monkeypatch.setattr(outbound, "fetch_pdf", lambda url: None)
    assert outbound.send_to_tablet(make_paper()) is None
    assert tablet.uploads == []
