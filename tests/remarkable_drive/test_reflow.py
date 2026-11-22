"""Tests for printing arXiv's HTML at tablet size, and the column re-layout fallback.

The HTML tests drive a real headless Chromium against a small LaTeXML-shaped page;
they're skipped where Chromium for Playwright isn't installed.
"""

from pathlib import Path

import fitz
import pytest
from playwright.sync_api import sync_playwright

from remarkable_drive import columns, reflow

FIXTURES = Path(__file__).parent / "fixtures"


def _chromium() -> bool:
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:  # noqa: BLE001 - any failure means no browser here
        return False


needs_chromium = pytest.mark.skipif(not _chromium(), reason="no Chromium for Playwright")
MM = 72 / 25.4


@pytest.fixture(scope="module")
def rendered():
    pdf = reflow.render((FIXTURES / "latexml.html").as_uri())
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        yield [(page.rect, page.get_text("words")) for page in doc]


@needs_chromium
def test_pages_are_tablet_sized(rendered):
    for rect, _ in rendered:
        assert rect.width == pytest.approx(157 * MM, abs=1)
        assert rect.height == pytest.approx(210 * MM, abs=1)


@needs_chromium
def test_site_chrome_is_hidden_and_text_is_selectable(rendered):
    text = " ".join(w[4] for _, words in rendered for w in words)
    assert "NAVIGATION" not in text
    assert "Opening paragraph" in text and "Closing paragraph." in text


@needs_chromium
def test_nothing_runs_past_the_right_margin(rendered):
    """The SVG-boxed prompt, the listing and the wide table all fit the page."""
    words = [(rect, w) for rect, ws in rendered for w in ws]
    expected = ([f"prompt{i}" for i in range(120)] + [f"tok{i}" for i in range(40)]
                + [f"cell{i:02d}value" for i in range(14)])
    for word in expected:
        # Unpadded table cells extract as one run of text, so match within words.
        [(rect, w)] = [(r, w) for r, w in words
                       if w[4] == word or (word.startswith("cell") and word in w[4])][:1]
        assert w[0] >= 14 * MM - 1 and w[2] <= rect.width - 7 * MM + 1, word


@needs_chromium
def test_a_page_that_isnt_latexml_is_none(tmp_path):
    page = tmp_path / "plain.html"
    page.write_text("<html><body><p>HTML is not available for this paper.</p></body></html>")
    assert reflow.render(page.as_uri()) is None


# --- columns ------------------------------------------------------------------


def _two_column_pdf() -> bytes:
    """Three A4 pages, each with a running head and 20 lines per column."""
    doc = fitz.open()
    for n in range(3):
        page = doc.new_page()
        page.insert_text((72, 40), "Journal of Fixtures", fontsize=8)
        page.insert_text((72, 70), f"Wide title band {n}", fontsize=14)
        for i in range(20):
            page.insert_text((72, 110 + 14 * i), f"left{n}-{i:02d} words here", fontsize=9)
            page.insert_text((320, 110 + 14 * i), f"right{n}-{i:02d} words here", fontsize=9)
    return doc.tobytes()


def test_columns_are_stacked_in_reading_order_on_tablet_pages():
    with fitz.open(stream=columns.relayout(_two_column_pdf()), filetype="pdf") as doc:
        for page in doc:
            assert page.rect.width == pytest.approx(157 * MM, abs=1)
        words = [w[4] for page in doc for w in page.get_text("words", sort=False)]
    tokens = [w for w in words if w[:4] in ("left", "righ", "band") or w.startswith("Wide")]
    order = [w.split("-")[0] for w in words if "-" in w]
    # Each page: all of the left column, then all of the right.
    assert order == ["left0"] * 20 + ["right0"] * 20 + ["left1"] * 20 + ["right1"] * 20 + ["left2"] * 20 + ["right2"] * 20
    assert tokens  # sanity: something was extracted
    assert "Journal" not in words  # the running head is dropped


def test_column_text_is_bigger_than_on_a4():
    with fitz.open(stream=_two_column_pdf(), filetype="pdf") as src, \
            fitz.open(stream=columns.relayout(_two_column_pdf()), filetype="pdf") as out:
        def height(doc, word):
            for page in doc:
                for w in page.get_text("words"):
                    if w[4] == word:
                        return (w[3] - w[1]) / page.rect.width
        # Relative to the page width: a column fills the tablet page.
        assert height(out, "left0-00") > 1.5 * height(src, "left0-00")
