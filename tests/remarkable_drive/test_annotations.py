"""Finding and anchoring the marks on an annotated paper exported from the reMarkable.

``fixtures/annotated_*.pdf`` are four pages of a real export (2026-11-14) and the
same pages of the original: a loop round a passage and "CREMLS?" beside a sentence
(p.1), a note and a bracket beside a figure (p.2), a smart highlight with a freehand
highlight over part of it (p.3), a page inserted on the tablet, and a highlight with a
ragged start and end (p.4). The export's p.2 is 31pt wider on the left, where the note
ran off the page.
"""

from pathlib import Path

import fitz
import pytest

from remarkable_drive import annotations as ann
from remarkable_drive import outbound
from remarkable_drive.outbound import COVER_MARKER

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def docs():
    export = fitz.open(FIXTURES / "annotated_export.pdf")
    original = fitz.open(FIXTURES / "annotated_original.pdf")
    yield export, original
    export.close()
    original.close()


@pytest.fixture(scope="module")
def found(docs):
    return ann.read(*docs)


def test_pages_map_by_text_around_the_inserted_page(docs):
    assert ann.map_pages(*docs) == [0, 1, 2, None, 3]


def test_inserted_page_is_placed_after_the_page_before_it(found):
    assert [(p.after_page, p.index) for p in found.inserted] == [(3, 3)]
    assert found.unmatched == []


def test_loop_anchors_to_the_passage_it_goes_round(found):
    loop = found.marks[0]
    assert (loop.kind, loop.page, loop.anchor) == ("pen", 1, "enclosed")
    assert loop.text.startswith("referred")
    assert "the main source of postmarketing" in loop.text
    assert loop.text.endswith("brings together 44 million reports from member")


def test_margin_question_anchors_to_its_own_column(found):
    note = found.marks[1]
    assert (note.page, note.anchor) == (1, "beside")
    assert note.text == "Appendix 1). In this paper, we will refer to the new method as vigiMatch2025."


def test_notes_beside_a_figure_anchor_to_its_caption(found):
    page2 = [m for m in found.marks if m.page == 2]
    # "dunno?" and the bracket below it; the "?"'s dot is part of the note, not a mark.
    assert len(page2) == 2
    assert all(m.anchor == "figure" for m in page2)
    assert all(m.text.startswith("Figure 1. Schematic of how the date vector") for m in page2)


def test_widened_page_is_shifted_back_onto_the_original(found, docs):
    export, _ = docs
    assert export[1].mediabox.x0 < -30  # the export grew 31pt to the left
    note = [m for m in found.marks if m.page == 2][0]
    # In the original's coordinates the note sits off the left edge of the page.
    assert note.rect.x0 < 0
    # Its strokes are kept in the export's coordinates, for cropping.
    assert ann._bbox(note.drawings).x0 > 0


def test_overlapping_highlights_are_one_passage(found):
    page3 = [m for m in found.marks if m.page == 3]
    assert len(page3) == 1
    assert page3[0].kind == "highlight"
    assert page3[0].colour == (0.95, 0.62, 1.0)
    assert page3[0].text.startswith("vigiMatch2025 demonstrates a substantial improvement")


def test_highlight_follows_its_shape_not_its_box(found):
    (highlight,) = [m for m in found.marks if m.page == 4]
    assert highlight.colour == (1.0, 0.76, 0.55)
    assert highlight.text.startswith("The externally indicated feature")
    assert highlight.text.endswith("relatively rare in general.")


# --- A cover page, built the way outbound builds it ---------------------------


def _ink(page: fitz.Page, rect: fitz.Rect, colour=(0, 0, 0)) -> None:
    """A filled stroke outline, the way the tablet draws pen and highlighter."""
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(fill=colour, color=None)
    shape.commit()


def test_cover_page_ink_is_a_general_remark_and_pages_number_from_the_paper():
    original = fitz.open()
    cover = original.new_page()
    cover.insert_text((50, 800), f"{COVER_MARKER} · paper 7", fontsize=7)
    for n in range(2):
        original.new_page().insert_text((72, 100), f"Paper page {n + 1} words here")
    export = fitz.open(stream=original.tobytes(), filetype="pdf")
    _ink(export[0], fitz.Rect(100, 300, 140, 310))
    _ink(export[2], fitz.Rect(400, 92, 440, 102))

    found = ann.read(export, original)
    assert [(m.page, m.anchor) for m in found.marks] == [(None, "cover"), (2, "beside")]
    assert found.marks[1].text == "Paper page 2 words here"


def test_a_single_page_export_matches_its_page():
    original = fitz.open()
    for n in range(3):
        original.new_page().insert_text((72, 100), f"Page {n + 1} of the paper")
    export = fitz.open()
    export.insert_pdf(original, from_page=2, to_page=2)
    _ink(export[0], fitz.Rect(72, 103, 200, 105))  # an underline

    found = ann.read(export, original)
    (mark,) = found.marks
    assert (mark.page, mark.anchor, mark.text) == (3, "underline", "Page 3 of the paper")


def test_nothing_written_finds_nothing():
    original = fitz.open()
    original.new_page().insert_text((72, 100), "Untouched")
    export = fitz.open(stream=original.tobytes(), filetype="pdf")
    assert ann.read(export, original).empty


def test_specks_join_the_nearest_mark():
    strokes = [{"rect": fitz.Rect(0, 0, 30, 20)}, {"rect": fitz.Rect(34, 5, 40, 20)},
               {"rect": fitz.Rect(45, 0, 48, 3)},     # a dot, 5pt from the "?"
               {"rect": fitz.Rect(200, 0, 230, 20)}]  # another note
    groups = ann.group(strokes)
    assert sorted(len(g) for g in groups) == [1, 3]


# --- A reflowed paper ---------------------------------------------------------
#
# ``fixtures/reflowed_*.pdf``: two pages of a paper re-rendered at tablet size and
# annotated on the tablet (2026-11-17). Page 1: a smart highlight over three lines and
# "Much better margin!" written after a heading. Page 2: "Great work Claude! Let me know
# if you read this!" in four handwritten lines below a list.


@pytest.fixture(scope="module")
def reflowed():
    export = fitz.open(FIXTURES / "reflowed_export.pdf")
    original = fitz.open(FIXTURES / "reflowed_original.pdf")
    yield ann.read(export, original)
    export.close()
    original.close()


def test_a_highlight_over_several_lines_covers_each_line(reflowed):
    # The tablet stores it as one drawing with a rectangle per line.
    (highlight,) = [m for m in reflowed.marks if m.kind == "highlight"]
    assert highlight.text == ("continued pre-training on risk-control corpora injects domain "
                              "knowledge, and task rewards jointly evaluate prediction "
                              "correctness and reasoning quality.")


def test_a_handwritten_note_is_one_mark_not_one_per_word(reflowed):
    pens = [(m.page, m.anchor, m.text) for m in reflowed.marks if m.kind == "pen"]
    assert pens == [(1, "beside", "1. Introduction"), (2, "beside", "cost savings.")]


def test_separate_notes_side_by_side_stay_separate():
    word = [{"rect": fitz.Rect(0, 0, 30, 20)}, {"rect": fitz.Rect(50, 0, 80, 20)}]
    far = [{"rect": fitz.Rect(200, 0, 230, 20)}]  # another note, well along the line
    below = [{"rect": fitz.Rect(0, 60, 30, 80)}]  # one further down the margin
    groups = ann.group(word + far + below)
    assert sorted(len(g) for g in groups) == [1, 1, 2]


def test_browser_hyphens_are_healed_across_lines():
    # (x0, y0, x1, y1, text, block, line, word), as get_text("words") gives them.
    words = [(72, 90, 130, 102, "heteroge\u2010", 0, 0, 0),
             (72, 104, 110, 116, "neous", 0, 1, 0), (114, 104, 140, 116, "data", 0, 1, 1)]
    assert ann._in_rows(ann._rows(words)) == "heterogeneous data"
    assert ann._join(words) == "heterogeneous data"


# --- Page stamps --------------------------------------------------------------


def _stamped_upload() -> fitz.Document:
    """Cover, a page of text, and a page that is only a figure, stamped as uploaded."""
    from tests.triage.test_obsidian import make_paper

    src = fitz.open()
    src.new_page().insert_text((72, 100), "Words on the first page", fontsize=11)
    figure = src.new_page()
    figure.draw_rect(fitz.Rect(100, 100, 400, 300), color=(0, 0, 0), width=1)
    return fitz.open(stream=outbound.with_cover(make_paper(id=4), src.tobytes()),
                     filetype="pdf")


def test_a_page_with_no_words_is_matched_by_its_stamp():
    original = _stamped_upload()
    export = fitz.open()
    export.insert_pdf(original)
    blank = export.new_page()                        # one the reader inserted
    blank.draw_line((50, 50), (200, 60), color=(0, 0, 0), width=2)
    export.move_page(3, 2)                           # ...between pages 1 and 2

    assert ann.map_pages(export, original) == [0, 1, None, 2]


def test_ink_on_a_figure_page_is_a_mark_not_an_inserted_page():
    original = _stamped_upload()
    export = fitz.open()
    export.insert_pdf(original)
    export[2].draw_line((120, 320), (300, 330), color=(0, 0, 0), width=2)

    result = ann.read(export, original)
    assert result.inserted == [] and result.unmatched == []
    assert [m.page for m in result.marks] == [2]


def test_the_stamp_is_never_part_of_the_text():
    original = _stamped_upload()
    assert all(not w[4].startswith(outbound.PAGE_STAMP)
               for page in original for w in ann._words(page))
