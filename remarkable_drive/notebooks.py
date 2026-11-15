"""reMarkable notebooks exported to ``reMarkable/Notes`` → the handwritten notes pipeline.

The export is a vector PDF: your strokes as real paths, plus the page template (a
dot grid, lines, …) as many identical little shapes. Each page is redrawn with the
ink only and rendered to PNG, so the vision model sees the writing without ~1,500
dots behind it, and pages with nothing written on them are skipped. The pages then
go to :func:`handwritten_notes.handwritten_bot.transcribe_and_file`, exactly like
photos sent in the chat or notebooks emailed from the tablet.
"""

import re
from collections import defaultdict

import fitz

from handwritten_notes.handwritten_bot import PageImage, transcribe_and_file
from remarkable_drive.watcher import DriveFile, Outcome
from util.timezone import STOCKHOLM

ORIGIN = "remarkable"
# Renders a 445×594pt notebook page at about 1100×1500px.
ZOOM = 2.5
# A template is many identical shapes; handwriting never repeats exactly 20 times.
TEMPLATE_MIN_REPEATS = 20

_COPY_SUFFIX = re.compile(r" \(\d+\)$")


def _template_key(drawing: dict) -> tuple:
    rect = drawing["rect"]
    return (drawing["type"], round(rect.width, 1), round(rect.height, 1),
            round(drawing.get("width") or 0, 2), drawing.get("fill"), drawing.get("color"))


def ink_drawings(page: fitz.Page) -> list[dict]:
    """The page's drawings minus its template: groups of identically sized, styled shapes."""
    drawings = page.get_drawings()
    groups = defaultdict(list)
    for index, drawing in enumerate(drawings):
        groups[_template_key(drawing)].append(index)
    template = {i for members in groups.values() if len(members) >= TEMPLATE_MIN_REPEATS
                for i in members}
    return [d for i, d in enumerate(drawings) if i not in template]


def _redraw(drawings: list[dict], width: float, height: float) -> fitz.Document:
    """A one-page document with only ``drawings`` on it."""
    doc = fitz.open()
    shape = doc.new_page(width=width, height=height).new_shape()
    for d in drawings:
        for item in d["items"]:
            op = item[0]
            if op == "l":
                shape.draw_line(item[1], item[2])
            elif op == "c":
                shape.draw_bezier(item[1], item[2], item[3], item[4])
            elif op == "re":
                shape.draw_rect(item[1])
            elif op == "qu":
                shape.draw_quad(item[1])
        shape.finish(
            fill=d.get("fill"),
            color=d.get("color"),
            width=d.get("width") or 0,
            lineCap=max(d.get("lineCap") or (0,)),
            lineJoin=d.get("lineJoin") or 0,
            closePath=d.get("closePath", False),
            even_odd=d.get("even_odd", False),
            fill_opacity=d.get("fill_opacity") or 1,
            stroke_opacity=d.get("stroke_opacity") or 1,
        )
    shape.commit()
    return doc


def render_pages(pdf: bytes) -> list[PageImage]:
    """PNGs of the pages with something written on them, template removed.

    A page with text or images on it (a PDF document, rather than a notebook) is
    rendered as it is: only notebook pages are pure strokes.
    """
    pages = []
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        for page in doc:
            matrix = fitz.Matrix(ZOOM, ZOOM)
            if page.get_text("words") or page.get_images():
                pixmap = page.get_pixmap(matrix=matrix)
            else:
                ink = ink_drawings(page)
                if not ink:
                    continue
                with _redraw(ink, page.rect.width, page.rect.height) as clean:
                    pixmap = clean[0].get_pixmap(matrix=matrix)
            pages.append(PageImage(pixmap.tobytes("png"), "image/png", "png"))
    return pages


def title(file: DriveFile) -> str:
    """The notebook's name on the tablet: the filename without ``.pdf`` or a `` (2)`` suffix."""
    name = file.name[:-4] if file.name.lower().endswith(".pdf") else file.name
    return _COPY_SUFFIX.sub("", name).strip() or "a notebook"


async def handle(bot, chat_id: int, file: DriveFile, data: bytes) -> Outcome:
    name = title(file)
    if file.mime_type != "application/pdf":
        await bot.send_message(chat_id, f"📁 {file.name} in reMarkable/Notes isn't a PDF — "
                                        "moved it to reMarkable/Failed.")
        return Outcome.REJECT

    pages = render_pages(data)
    if not pages:
        await bot.send_message(chat_id, f"📁 {name} from the reMarkable has nothing written on it.")
        return Outcome.DONE

    count = "1 page" if len(pages) == 1 else f"{len(pages)} pages"
    header = await bot.send_message(chat_id, f"📁 From the reMarkable: {name} ({count})")
    done = await transcribe_and_file(header, pages, caption=name,
                                     when=file.modified.astimezone(STOCKHOLM),
                                     origin=ORIGIN, routing_source=ORIGIN)
    return Outcome.DONE if done else Outcome.RETRY
