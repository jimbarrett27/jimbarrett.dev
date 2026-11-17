"""A paper PDF re-laid column by column onto tablet-sized pages.

The fallback for papers without arXiv HTML (:mod:`remarkable_drive.reflow`). Each
source page is cut into pieces in reading order: full-width bands (title block, wide
figures and tables) and, between them, the left column then the right. Pieces are
scaled to the output page's width (one scale per source page, so the text size is
consistent) and stacked; a piece taller than the room left is split at a gap
between lines. Each source page starts a fresh output page.

Text outside a piece is redacted from its copy, so the output's text layer holds
exactly what's visible and the annotation pipeline can still anchor to words.
Running heads and page numbers are left out. Single-column papers come out as
their one column, margins trimmed.
"""

import re
from collections import Counter
from dataclasses import dataclass

import fitz

from remarkable_drive.reflow import MARGIN_MM, PAGE_MM

MM = 72 / 25.4
OUT_W, OUT_H = PAGE_MM[0] * MM, PAGE_MM[1] * MM
TOP, RIGHT, BOTTOM, LEFT = (m * MM for m in MARGIN_MM)
PAD = 3.0       # pt round each piece, source units
GAP = 6.0       # pt between stacked pieces, output units
BAND = 0.11     # top/bottom share of a page where running heads and folios live

_DIGITS = re.compile(r"\d+")


@dataclass
class _El:
    rect: fitz.Rect
    kind: str  # "text" | "fig"


def _norm(text: str) -> str:
    return _DIGITS.sub("#", text.strip().lower())


def _line_text(line: dict) -> str:
    return "".join(s["text"] for s in line["spans"])


def _at_edge(page: fitz.Page, rect: fitz.Rect) -> bool:
    h = page.rect.height
    return rect.y1 < h * BAND or rect.y0 > h * (1 - BAND)


def _furniture(doc: fitz.Document) -> set[str]:
    """Text repeated near the top/bottom edge of several pages: running heads, folios."""
    seen = Counter()
    for page in doc:
        seen.update({_norm(_line_text(line))
                     for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", [])
                     if _at_edge(page, fitz.Rect(line["bbox"]))})
    return {k for k, n in seen.items() if n >= 3 or k in {"#", ""}}


def _elements(page: fitz.Page, furniture: set[str]) -> list[_El]:
    els = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] == 1:
            els.append(_El(fitz.Rect(block["bbox"]), "fig"))
            continue
        for line in block["lines"]:
            if not _line_text(line).strip():
                continue
            if abs(line["dir"][0]) < 0.5:   # vertical text: the arXiv margin stamp
                continue
            rect = fitz.Rect(line["bbox"])
            if _at_edge(page, rect) and _norm(_line_text(line)) in furniture:
                continue
            els.append(_El(rect, "text"))
    for rect in page.cluster_drawings():
        if rect.width > 2 or rect.height > 2:
            els.append(_El(fitz.Rect(rect), "fig"))
    return [e for e in els if e.rect.intersects(page.rect) and not e.rect.is_empty]


def _gutter(els: list[_El]) -> float | None:
    """x of a vertical gutter near mid-page that most text lines don't cross."""
    text = [e.rect for e in els if e.kind == "text"]
    if len(text) < 10:
        return None
    x0 = min(r.x0 for r in text)
    width = max(r.x1 for r in text) - x0
    best = None
    for i in range(41):
        x = x0 + width * (0.4 + 0.2 * i / 40)
        left = sum(1 for r in text if r.x1 <= x)
        right = sum(1 for r in text if r.x0 >= x)
        if min(left, right) < 0.2 * len(text):
            continue
        crossing = sum(1 for r in text if r.x0 < x < r.x1)
        if best is None or crossing < best[0]:
            best = (crossing, x)
    if best and best[0] <= 0.15 * len(text):
        return best[1]
    return None


def _pieces(els: list[_El]) -> list[fitz.Rect]:
    """Source-page rectangles in reading order."""
    if not els:
        return []
    content = fitz.Rect(els[0].rect)
    for e in els:
        content |= e.rect
    gutter = _gutter(els)
    if gutter is None:
        return [content]

    def spans(r: fitz.Rect) -> bool:
        return r.x0 < gutter - 2 and r.x1 > gutter + 2

    bands: list[list[float]] = []
    for r in sorted((e.rect for e in els if spans(e.rect)), key=lambda r: r.y0):
        if bands and r.y0 <= bands[-1][1] + 4:
            bands[-1][1] = max(bands[-1][1], r.y1)
        else:
            bands.append([r.y0, r.y1])

    out = []

    def columns(top: float, bottom: float) -> None:
        inside = [e.rect for e in els
                  if e.rect.y0 >= top - 1 and e.rect.y1 <= bottom + 1 and not spans(e.rect)]
        left = [r for r in inside if r.x1 <= gutter + 2]
        right = [r for r in inside if r.x0 >= gutter - 2]
        if left:
            out.append(fitz.Rect(content.x0, min(r.y0 for r in left), gutter,
                                 max(r.y1 for r in left)))
        if right:
            out.append(fitz.Rect(gutter, min(r.y0 for r in right), content.x1,
                                 max(r.y1 for r in right)))

    y = content.y0
    for top, bottom in bands:
        if top > y:
            columns(y, top)
        out.append(fitz.Rect(content.x0, top, content.x1, bottom))
        y = bottom
    if y < content.y1:
        columns(y, content.y1)
    return [r for r in out if r.height > 4]


def _cuts(els: list[_El], rect: fitz.Rect) -> list[float]:
    """y values inside ``rect`` where a horizontal cut crosses no element."""
    rects = [e.rect for e in els if e.rect.intersects(rect)]
    cuts = []
    for y in sorted({r.y1 for r in rects}):
        c = y + 0.5
        if rect.y0 < c < rect.y1 and not any(r.y0 < c < r.y1 for r in rects):
            cuts.append(c)
    return cuts


def _isolated(src: fitz.Document, pno: int, clip: fitz.Rect) -> fitz.Document:
    """A one-page copy of ``src[pno]`` with all text outside ``clip`` removed."""
    doc = fitz.open()
    doc.insert_pdf(src, from_page=pno, to_page=pno)
    page = doc[0]
    r = page.rect
    for box in (fitz.Rect(r.x0, r.y0, r.x1, clip.y0), fitz.Rect(r.x0, clip.y1, r.x1, r.y1),
                fitz.Rect(r.x0, clip.y0, clip.x0, clip.y1),
                fitz.Rect(clip.x1, clip.y0, r.x1, clip.y1)):
        if not box.is_empty:
            page.add_redact_annot(box)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)
    return doc


def relayout(pdf: bytes) -> bytes:
    """``pdf`` re-laid onto portrait tablet pages, a column wide."""
    inner_w = OUT_W - LEFT - RIGHT
    floor = OUT_H - BOTTOM
    with fitz.open(stream=pdf, filetype="pdf") as src, fitz.open() as out:
        furniture = _furniture(src)
        for pno, page in enumerate(src):
            els = _elements(page, furniture)
            pieces = [r + (-PAD, -PAD, PAD, PAD) for r in _pieces(els)]
            if not pieces:
                continue
            # The narrowest piece (a column) fills the width; wider ones are shrunk.
            col_w = min(r.width for r in pieces)
            cur, y = None, 0.0
            for r in pieces:
                base = min(inner_w / col_w, inner_w / r.width)
                cuts = _cuts(els, r)
                top = r.y0
                while top < r.y1 - 1:
                    scale = base
                    if cur is None or y >= floor - 20:
                        cur, y = out.new_page(width=OUT_W, height=OUT_H), TOP
                    room = (floor - y) / scale
                    bottom = r.y1
                    if bottom - top > room:
                        fits = [c for c in cuts if top + 10 < c <= top + room]
                        if fits:
                            bottom = fits[-1]
                        elif y > TOP:       # no clean cut here: start a fresh page
                            cur = None
                            continue
                        else:               # taller than a page: shrink it
                            scale = min(scale, (floor - TOP) / (bottom - top))
                    clip = fitz.Rect(r.x0, top, r.x1, bottom)
                    w = clip.width * scale
                    x = LEFT + (inner_w - w) / 2
                    target = fitz.Rect(x, y, x + w, y + clip.height * scale)
                    with _isolated(src, pno, clip) as iso:
                        cur.show_pdf_page(target, iso, 0, clip=clip)
                    y = target.y1 + GAP
                    top = bottom
        return out.tobytes(garbage=3, deflate=True)
