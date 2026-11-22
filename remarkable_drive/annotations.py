"""Reading an annotated paper exported from the reMarkable: which marks are where, on what.

An export is the uploaded PDF with your ink added. The tablet leaves the original
page content alone and appends each stroke after the page's own drawings, so on a
page that matches the original the ink is exactly the drawings past the original's
count: no image work needed to separate it. The steps (REWORK_PLAN §2.4):

1. **Map pages** by the invisible page stamp outbound writes on each page (or, on
   older uploads, by text layer: each export page whose words equal the next
   unmatched original page's is that page). A page with no words or stamp that
   matches nothing is a page you inserted. The cover page (:data:`remarkable_drive.outbound.COVER_MARKER`) is
   recognised so its ink becomes general remarks.
2. **Separate the ink**: drawings beyond the original page's count.
3. **Classify** by colour: black and grey are pen, anything else is the highlighter.
4. **Group** pen strokes by proximity, so one margin note or one circle is one mark.
5. **Anchor** each mark to the printed words: highlighted, circled, underlined, written
   beside, or next to a figure (its caption).

Writing past the page edge widens the page and can move its origin, so every export
page's coordinates are shifted back onto the original's using the first word's
position before anything is compared.

Transcribing pen marks and writing the note live in :mod:`remarkable_drive.reading`.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import fitz
from PIL import Image, ImageDraw

from remarkable_drive.outbound import COVER_MARKER, PAGE_STAMP

# Pen strokes closer than this (pt) belong to the same mark.
GROUP_GAP = 7.0
# A highlight covers a word when this much of the word's box is under it.
HIGHLIGHT_COVER = 0.5
# Pen colours are black or grey; anything with more spread between channels is a highlighter.
GREY_TOLERANCE = 0.08
# Underline: a flat mark, at most this tall (pt) and this many times wider than tall.
UNDERLINE_MAX_HEIGHT = 7.0
UNDERLINE_ASPECT = 4.0
# How far above an underline (pt) the underlined words' baseline may be.
UNDERLINE_REACH = 9.0
# Raster used to test what ink covers: pixels per pt.
RASTER_SCALE = 2.0
# A loop: at least this many words inside the ink's hull, at most this share touched by it.
LOOP_MIN_WORDS = 3
LOOP_MAX_TOUCHED = 0.6
# A speck (a dot, the point of a "?") at most this big (pt) joins a mark up to this far away.
SPECK_SIZE = 10.0
SPECK_REACH = 20.0
# Handwritten words on one line (overlapping by this share of the shorter one's
# height) at most this far apart (pt), or lines stacked at most this far apart, are
# one note.
WORD_GAP = 30.0
LINE_GAP = 15.0
LINE_OVERLAP = 0.4
# A horizontal gap wider than this (pt) between words on a baseline is a gutter.
COLUMN_GAP = 12.0
# Images shorter than this (pt) are inline glyphs or logos, not figures.
MIN_FIGURE_HEIGHT = 40.0
# Text lines quoted for a note written beside the text.
BESIDE_MAX_LINES = 4
# How far (pt) a note may sit from a figure and still be about it.
FIGURE_REACH = 60.0

# Line-end hyphens: ASCII, and the Unicode hyphen browsers print when they hyphenate.
_HYPHENS = ("-", "\u2010")

_CAPTION = re.compile(r"^\s*(fig\.?|figure|table)\s*\d+", re.IGNORECASE)


# --- Data ---------------------------------------------------------------------


@dataclass
class Mark:
    """One annotation: a highlight, or a group of pen strokes."""
    kind: str                      # "highlight" | "pen"
    page: Optional[int]            # paper page number (1-based); None on the cover
    rect: fitz.Rect                # in the original page's coordinates
    drawings: list[dict]           # pen strokes in the export page's coordinates (for rendering)
    colour: Optional[tuple] = None
    anchor: str = "none"           # highlight | enclosed | underline | beside | figure | cover | none
    text: str = ""                 # the printed words it's anchored to
    drawings_original: list[dict] = field(default_factory=list, repr=False)  # moved onto the original
    export_index: Optional[int] = None  # the export page it's on (for rendering pen marks)


@dataclass
class InsertedPage:
    after_page: Optional[int]      # the paper page it follows; None if before the first
    index: int                     # page index in the export


@dataclass
class Annotations:
    marks: list[Mark] = field(default_factory=list)
    inserted: list[InsertedPage] = field(default_factory=list)
    unmatched: list[int] = field(default_factory=list)  # export pages that are neither

    @property
    def empty(self) -> bool:
        return not self.marks and not self.inserted


# --- 1. Mapping pages ---------------------------------------------------------


def _words(page: fitz.Page) -> list[tuple]:
    """The page's printed words, without the upload's invisible page stamp."""
    return [w for w in page.get_text("words") if not w[4].startswith(PAGE_STAMP)]


def _stamp(page: fitz.Page) -> Optional[str]:
    """The page stamp outbound writes on every uploaded page; None on older uploads."""
    for w in page.get_text("words"):
        if w[4].startswith(PAGE_STAMP):
            return w[4]
    return None


def _key(words: list[tuple]) -> tuple[str, ...]:
    return tuple(w[4] for w in words)


def is_cover(page: fitz.Page) -> bool:
    return COVER_MARKER in page.get_text()


def map_pages(export: fitz.Document, original: fitz.Document) -> list[Optional[int]]:
    """For each export page, the original page index it shows, or None (inserted/unknown).

    Pages are matched by their page stamp, or on uploads from before stamps, by their
    words. Matching is in order: an export page matches the first original page at or
    after the last match with the same key. Pages you insert don't break the order,
    and a single-page "current page" export matches wherever that page is.
    """
    def key(page: fitz.Page):
        return _stamp(page) or _key(_words(page))

    keys = [key(p) for p in original]
    mapping: list[Optional[int]] = []
    cursor = 0
    for page in export:
        key_ = key(page)
        match = None
        if key_:
            for j in list(range(cursor, len(keys))) + list(range(0, cursor)):
                if keys[j] == key_:
                    match = j
                    break
        mapping.append(match)
        if match is not None:
            cursor = match + 1
    return mapping


# --- 2./3. Ink ----------------------------------------------------------------


def _offset(export_page: fitz.Page, original_page: fitz.Page) -> fitz.Point:
    """What to add to export coordinates to get the original's (non-zero if the page grew)."""
    ew, ow = _words(export_page), _words(original_page)
    if not ew or not ow:
        return fitz.Point(0, 0)
    return fitz.Point(ow[0][0] - ew[0][0], ow[0][1] - ew[0][1])


def ink(export_page: fitz.Page, original_page: Optional[fitz.Page]) -> list[dict]:
    """The drawings on ``export_page`` that aren't on ``original_page``."""
    drawings = export_page.get_drawings()
    if original_page is None:
        return drawings
    return drawings[len(original_page.get_drawings()):]


def is_pen(drawing: dict) -> bool:
    colour = drawing.get("fill") or drawing.get("color") or (0, 0, 0)
    return max(colour) - min(colour) <= GREY_TOLERANCE


def _colour(drawing: dict) -> Optional[tuple]:
    colour = drawing.get("fill") or drawing.get("color")
    return tuple(round(c, 2) for c in colour) if colour else None


# --- Geometry helpers ---------------------------------------------------------


def _points(drawing: dict) -> list[fitz.Point]:
    """The drawing's outline as a polygon (béziers sampled)."""
    points: list[fitz.Point] = []
    for item in drawing["items"]:
        op = item[0]
        if op == "l":
            points += [item[1], item[2]]
        elif op == "c":
            p0, p1, p2, p3 = item[1:5]
            for i in range(9):
                t = i / 8
                u = 1 - t
                points.append(p0 * (u ** 3) + p1 * (3 * u * u * t) + p2 * (3 * u * t * t)
                              + p3 * (t ** 3))
        elif op == "re":
            r = item[1]
            points += [r.tl, r.tr, r.br, r.bl, r.tl]
        elif op == "qu":
            q = item[1]
            points += [q.ul, q.ur, q.lr, q.ll, q.ul]
    return points


def _moved(drawing: dict, offset: fitz.Point) -> dict:
    """``drawing`` translated by ``offset``."""
    m = fitz.Matrix(1, 0, 0, 1, offset.x, offset.y)

    def tx(v):
        if isinstance(v, fitz.Point):
            return v * m
        if isinstance(v, fitz.Rect):
            return v * m
        if isinstance(v, fitz.Quad):
            return v * m
        return v

    moved = dict(drawing)
    moved["items"] = [tuple(tx(v) for v in item) for item in drawing["items"]]
    moved["rect"] = drawing["rect"] * m
    return moved


def _subpaths(drawing: dict) -> list[list[fitz.Point]]:
    """The drawing's outline split where the path jumps.

    One drawing can hold several shapes: a highlight over three lines of text is one
    drawing with a rectangle per line. Joining them into one polygon fills the wrong
    area, so each is filled on its own.
    """
    paths: list[list[fitz.Point]] = []
    current: list[fitz.Point] = []
    for item in drawing["items"]:
        points = _points({"items": [item]})
        if not points:
            continue
        if current and abs(current[-1] - points[0]) > 0.5:
            paths.append(current)
            current = []
        current += points if not current else points[1:]
    if current:
        paths.append(current)
    return paths


def _rasterise(drawings: list[dict], rect: fitz.Rect) -> Image.Image:
    """A 1-bit-ish image of ``drawings`` over ``rect`` (black ink on white)."""
    width = max(1, int(rect.width * RASTER_SCALE) + 1)
    height = max(1, int(rect.height * RASTER_SCALE) + 1)
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    for d in drawings:
        line_width = max(1, int((d.get("width") or 0) * RASTER_SCALE))
        for path in _subpaths(d):
            pts = [((p.x - rect.x0) * RASTER_SCALE, (p.y - rect.y0) * RASTER_SCALE) for p in path]
            if len(pts) < 2:
                continue
            if d.get("fill") is not None:
                draw.polygon(pts, fill=0)
            draw.line(pts, fill=0, width=line_width)
    return image


def _covered(word_rect: fitz.Rect, mask: Image.Image, rect: fitz.Rect) -> float:
    """The share of ``word_rect`` that is black in ``mask`` (sampled on a grid)."""
    hits = total = 0
    for i in range(5):
        for j in range(3):
            x = word_rect.x0 + (i + 0.5) * word_rect.width / 5
            y = word_rect.y0 + (j + 0.5) * word_rect.height / 3
            px, py = int((x - rect.x0) * RASTER_SCALE), int((y - rect.y0) * RASTER_SCALE)
            total += 1
            if 0 <= px < mask.width and 0 <= py < mask.height and mask.getpixel((px, py)) < 128:
                hits += 1
    return hits / total


def _hull(points: list[fitz.Point]) -> list[tuple[float, float]]:
    """Convex hull (monotone chain)."""
    pts = sorted({(round(p.x, 1), round(p.y, 1)) for p in points})
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _inside(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _centre(word: tuple) -> tuple[float, float]:
    return ((word[0] + word[2]) / 2, (word[1] + word[3]) / 2)


def _join(words: list[tuple]) -> str:
    """Words in reading order, lines joined with spaces and end-of-line hyphens healed."""
    words = sorted(words, key=lambda w: (w[5], w[6], w[7]))  # block, line, word
    text = ""
    last_line = None
    for w in words:
        line = (w[5], w[6])
        if text:
            if line != last_line and text.endswith(_HYPHENS):
                text = text[:-1]
            else:
                text += " "
        text += w[4]
        last_line = line
    return text


# --- 4. Grouping --------------------------------------------------------------


def _bbox(drawings: list[dict]) -> fitz.Rect:
    rect = fitz.Rect(drawings[0]["rect"])
    for d in drawings[1:]:
        rect |= d["rect"]
    return rect


def _distance(a: fitz.Rect, b: fitz.Rect) -> float:
    dx = max(0.0, b.x0 - a.x1, a.x0 - b.x1)
    dy = max(0.0, b.y0 - a.y1, a.y0 - b.y1)
    return max(dx, dy)


def group(drawings: list[dict], gap: float = GROUP_GAP) -> list[list[dict]]:
    """Pen strokes as marks: strokes within ``gap`` of each other, transitively.

    A speck (the dot of an ``i`` or a ``?``) joins the nearest mark within
    :data:`SPECK_REACH`, since handwriting puts those further away than its strokes.
    """
    parent = list(range(len(drawings)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(drawings)):
        for j in range(i + 1, len(drawings)):
            if _distance(drawings[i]["rect"], drawings[j]["rect"]) <= gap:
                parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i, d in enumerate(drawings):
        groups.setdefault(find(i), []).append(d)
    marks = list(groups.values())

    specks = [g for g in marks if max(_bbox(g).width, _bbox(g).height) <= SPECK_SIZE]
    for speck in specks:
        others = [g for g in marks if g is not speck]
        if not others:
            break
        nearest = min(others, key=lambda g: _distance(_bbox(g), _bbox(speck)))
        if _distance(_bbox(nearest), _bbox(speck)) <= SPECK_REACH:
            nearest.extend(speck)
            marks.remove(speck)
    marks = _join_handwriting(marks)
    return sorted(marks, key=lambda g: (_bbox(g).y0, _bbox(g).x0))


def _same_note(a: fitz.Rect, b: fitz.Rect) -> bool:
    """Whether two pieces of handwriting are words or lines of one note."""
    dx = max(0.0, b.x0 - a.x1, a.x0 - b.x1)
    dy = max(0.0, b.y0 - a.y1, a.y0 - b.y1)
    side_by_side = min(a.y1, b.y1) - max(a.y0, b.y0) > LINE_OVERLAP * min(a.height, b.height)
    stacked = min(a.x1, b.x1) - max(a.x0, b.x0) > 0
    return (side_by_side and dx <= WORD_GAP) or (stacked and dy <= LINE_GAP)


def _join_handwriting(marks: list[list[dict]]) -> list[list[dict]]:
    """Merge the words of a note, and its lines, into one mark.

    Strokes within :data:`GROUP_GAP` make a word, but the gaps between handwritten
    words and lines are wider than that, and each mark is transcribed and written up
    on its own.
    """
    marks = [list(m) for m in marks]
    merged = True
    while merged:
        merged = False
        for i in range(len(marks)):
            for j in range(i + 1, len(marks)):
                if _same_note(_bbox(marks[i]), _bbox(marks[j])):
                    marks[i] += marks.pop(j)
                    merged = True
                    break
            if merged:
                break
    return marks


# --- 5. Anchoring -------------------------------------------------------------


def _rows(words: list[tuple]) -> list[tuple[fitz.Rect, list[tuple]]]:
    """Visual lines: words of one text block on one baseline.

    Keyed by block so the two columns of a page stay apart even where the gutter is
    narrow, while a table row (one block, a "line" per cell) comes out whole.
    """
    rows: dict[tuple, list[tuple]] = {}
    for w in words:
        rows.setdefault((w[5], round(w[3] / 2.5)), []).append(w)
    out = []
    for ws in rows.values():
        rect = fitz.Rect(ws[0][:4])
        for w in ws[1:]:
            rect |= fitz.Rect(w[:4])
        out.append((rect, ws))
    return out


def _in_rows(rows: list[tuple[fitz.Rect, list[tuple]]]) -> str:
    """The rows' text top to bottom, left to right, with end-of-line hyphens healed."""
    text = ""
    for _, ws in sorted(rows, key=lambda item: item[0].y0):
        line = " ".join(w[4] for w in sorted(ws, key=lambda w: w[0]))
        if text.endswith(_HYPHENS):
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    return text


def _caption_near(figure: fitz.Rect, words: list[tuple]) -> str:
    """The figure's caption: the closest text block starting "Figure N" or "Table N"."""
    blocks: dict[int, list[tuple]] = {}
    for w in words:
        blocks.setdefault(w[5], []).append(w)
    best, best_distance = "", None
    for ws in blocks.values():
        text = _join(ws)
        if not _CAPTION.match(text):
            continue
        rect = fitz.Rect(ws[0][:4])
        for w in ws[1:]:
            rect |= fitz.Rect(w[:4])
        distance = _distance(rect, figure)
        if best_distance is None or distance < best_distance:
            best, best_distance = text, distance
    return best


def _figures(page: fitz.Page) -> list[fitz.Rect]:
    return [fitz.Rect(info["bbox"]) for info in page.get_image_info()
            if fitz.Rect(info["bbox"]).height > MIN_FIGURE_HEIGHT]


def _nearest_figure(rect: fitz.Rect, figures: list[fitz.Rect]) -> Optional[fitz.Rect]:
    near = [f for f in figures if _distance(f, rect) <= FIGURE_REACH]
    return min(near, key=lambda f: _distance(f, rect)) if near else None


def highlighted(highlights: list[dict], words: list[tuple]) -> list[tuple[tuple, list[tuple]]]:
    """Highlighted passages as (colour, words), one per unbroken run in reading order.

    Overlapping strokes (a freehand line over a smart highlight) count once, and a
    passage highlighted line by line comes out whole.
    """
    by_colour: dict[tuple, set[int]] = {}
    for d in highlights:
        mask = _rasterise([d], d["rect"])
        hit = by_colour.setdefault(_colour(d), set())
        for i, w in enumerate(words):
            rect = fitz.Rect(w[:4])
            if rect.intersects(d["rect"]) and _covered(rect, mask, d["rect"]) >= HIGHLIGHT_COVER:
                hit.add(i)
    passages = []
    for colour, indices in by_colour.items():
        run: list[int] = []
        for i in sorted(indices):
            if run and i != run[-1] + 1:
                passages.append((colour, [words[j] for j in run]))
                run = []
            run.append(i)
        if run:
            passages.append((colour, [words[j] for j in run]))
    return passages


def anchor_pen(mark: "Mark", words: list[tuple], figures: list[fitz.Rect]) -> None:
    """Decide what printed text a pen mark is about, from where it sits."""
    rect = mark.rect

    # Underline: a flat stroke with words sitting on it.
    if rect.height <= UNDERLINE_MAX_HEIGHT and rect.width >= UNDERLINE_ASPECT * rect.height:
        above = [w for w in words
                 if -3 <= rect.y0 - w[3] <= UNDERLINE_REACH
                 and min(w[2], rect.x1) - max(w[0], rect.x0) > 0.5 * (w[2] - w[0])]
        if above:
            mark.anchor, mark.text = "underline", _join(above)
            return

    # A loop round a passage: words inside its hull that the ink mostly leaves alone.
    # (Handwriting over the text touches what it covers; a loop goes round it.)
    hull = _hull([p for d in mark.drawings_original for p in _points(d)])
    if len(hull) >= 3:
        inside = [w for w in words if _inside(_centre(w), hull)]
        if len(inside) >= LOOP_MIN_WORDS:
            mask = _rasterise(mark.drawings_original, rect)
            touched = sum(1 for w in inside if _covered(fitz.Rect(w[:4]), mask, rect) > 0)
            if touched <= LOOP_MAX_TOUCHED * len(inside):
                mark.anchor, mark.text = "enclosed", _join(inside)
                return

    # Beside text: the visual lines level with the note, in the column it's closest to.
    rows = _rows(words)
    level = [(r, ws) for r, ws in rows if r.y1 > rect.y0 and r.y0 < rect.y1]
    if level:
        def score(r):  # nearest first; between overlapping columns, the one it overlaps most
            return (_distance(r, rect) if not r.intersects(rect) else 0.0,
                    -max(0.0, min(r.x1, rect.x1) - max(r.x0, rect.x0)))
        best = min(level, key=lambda item: score(item[0]))[0]
        figure = _nearest_figure(rect, figures)
        if figure is not None and _distance(best, rect) > FIGURE_REACH:
            mark.anchor, mark.text = "figure", _caption_near(figure, words)
            return
        column = [(r, ws) for r, ws in level if min(r.x1, best.x1) - max(r.x0, best.x0) > 0]
        centre = (rect.y0 + rect.y1) / 2
        column.sort(key=lambda item: abs((item[0].y0 + item[0].y1) / 2 - centre))
        mark.anchor, mark.text = "beside", _in_rows(column[:BESIDE_MAX_LINES])
        return

    figure = _nearest_figure(rect, figures)
    if figure is not None:
        mark.anchor, mark.text = "figure", _caption_near(figure, words)
        return

    # Nothing level with it: the closest line.
    if rows:
        nearest = min(rows, key=lambda item: _distance(item[0], rect))
        mark.anchor, mark.text = "beside", _in_rows([nearest])


# --- Putting it together ------------------------------------------------------


def read(export: fitz.Document, original: fitz.Document) -> Annotations:
    """Every mark in ``export``, anchored to ``original``'s text."""
    mapping = map_pages(export, original)
    has_cover = len(original) > 0 and is_cover(original[0])
    result = Annotations()
    last_page: Optional[int] = None

    for index, (page, match) in enumerate(zip(export, mapping)):
        if match is None:
            if _words(page):
                result.unmatched.append(index)
            elif ink(page, None):
                result.inserted.append(InsertedPage(last_page, index))
            continue

        original_page = original[match]
        cover = has_cover and match == 0
        paper_page = None if cover else match + (0 if has_cover else 1)
        if not cover:
            last_page = paper_page

        strokes = ink(page, original_page)
        if not strokes:
            continue
        offset = _offset(page, original_page)
        words = _words(original_page)
        moved = [_moved(d, offset) for d in strokes]
        marks: list[Mark] = []

        for colour, passage in highlighted([d for d in moved if not is_pen(d)], words):
            rect = fitz.Rect(passage[0][:4])
            for w in passage[1:]:
                rect |= fitz.Rect(w[:4])
            marks.append(Mark("highlight", paper_page, rect, [], colour=colour,
                              anchor="highlight", text=_join(passage)))

        figures = _figures(original_page)
        for strokes_in_mark in group([d for d in moved if is_pen(d)]):
            back = fitz.Point(-offset.x, -offset.y)
            mark = Mark("pen", paper_page, _bbox(strokes_in_mark),
                        [_moved(d, back) for d in strokes_in_mark],
                        drawings_original=strokes_in_mark, export_index=index)
            if cover:
                mark.anchor = "cover"
            else:
                anchor_pen(mark, words, figures)
            marks.append(mark)

        result.marks += sorted(marks, key=lambda m: (m.rect.y0, m.rect.x0))

    return result
