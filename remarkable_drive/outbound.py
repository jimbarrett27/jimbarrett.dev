"""Kept papers → a PDF with a screening cover page → ``reMarkable/Papers/To read``.

Called from the triage backend's routing (:mod:`triage.routing`) when a paper is
kept. The steps:

1. **Make a tablet-sized PDF** (:func:`tablet_pdf`). A4 papers are too small to
   read on the tablet, so:

   a. arXiv papers are printed from arXiv's HTML (:mod:`remarkable_drive.reflow`);
   b. failing that, the open-access PDF is found and re-laid column by column
      (:mod:`remarkable_drive.columns`);
   c. if that re-layout fails, the PDF goes as it is.

   arXiv papers have a PDF by construction; anything else is looked up on OpenAlex
   (``best_oa_location``, then any location with a ``pdf_url``). Publishers often
   answer a PDF link with an HTML page, so only a response that is actually a PDF
   counts.
2. **Prepend a cover page** the size of the paper's pages, summarising why the
   paper is there: legible as the tablet's thumbnail at the top, the screening
   detail below. Its text carries :data:`COVER_MARKER` so the annotation pipeline
   can recognise it. Every page then gets an invisible stamp (:data:`PAGE_STAMP`),
   so the annotation pipeline can match export pages back even when a page has no
   words of its own (a full-page figure).
3. **Upload** as ``<id> - <short title>.pdf``. The leading ID is how an annotated
   export is matched back to its paper. A copy of exactly what was uploaded is kept
   under ``papers/`` in the data dir, for comparing annotated exports against.

The uploaded file is "the original" from then on: annotated exports are compared
against it, not against the publisher's PDF.

No open-access PDF is not an error: :func:`send_to_tablet` returns ``None`` and the
paper is recorded as ``pdf_unavailable``. Network trouble *is* an error, raised so
the routing retry loop tries again.
"""

import html
import re
from pathlib import Path
from typing import Optional

import fitz
import requests

from content_screening.orm_models import ArticleORM
from gcp_util import drive
from remarkable_drive import columns, reflow
from util.logging_util import setup_logger
from util.paths import data_path

logger = setup_logger(__name__)

TO_READ = "reMarkable/Papers/To read"
COVER_MARKER = "triage-cover"
PAGE_STAMP = "triage-page"
USER_AGENT = "jimbarrett.dev-triage/1.0"
MAX_PDF_BYTES = 60 * 1024 * 1024
TITLE_CHARS = 60
A4 = fitz.paper_rect("a4")

_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')



# --- Finding the PDF ----------------------------------------------------------


def _openalex_pdf_url(paper: ArticleORM) -> Optional[str]:
    # Imported here: content_screening.openalex pulls in the whole discovery stack.
    from content_screening.openalex import DEFAULT_MAILTO, _get

    metadata = paper.metadata_ or {}
    if metadata.get("openalex_id"):
        key = metadata["openalex_id"]
    elif paper.doi:
        key = f"doi:{paper.doi}"
    else:
        return None
    try:
        work = _get(f"works/{key}", {"select": "best_oa_location,locations"},
                    DEFAULT_MAILTO)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise
    candidates = [work.get("best_oa_location")] + list(work.get("locations") or [])
    for location in candidates:
        if location and location.get("pdf_url"):
            return location["pdf_url"]
    return None


def arxiv_id(paper: ArticleORM) -> Optional[str]:
    """``paper``'s arXiv ID, from its source or an arXiv DOI; None if it has none."""
    if paper.source_type == "arxiv":
        return paper.external_id
    match = _ARXIV_DOI.match(paper.doi or "")
    return match.group(1) if match else None


def find_pdf_url(paper: ArticleORM) -> Optional[str]:
    """Where to download an open-access PDF of ``paper``, or None if there isn't one."""
    arxiv = arxiv_id(paper)
    if arxiv:
        return f"https://arxiv.org/pdf/{arxiv}"
    return _openalex_pdf_url(paper)


def fetch_pdf(url: str) -> Optional[bytes]:
    """The PDF at ``url``; None if it isn't one (an HTML landing page, a 4xx).

    Timeouts, connection errors and 5xx responses raise: they are worth a retry.
    """
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60,
                            allow_redirects=True)
    if 400 <= response.status_code < 500:
        logger.info("PDF link %s answered %s", url, response.status_code)
        return None
    response.raise_for_status()
    content = response.content
    if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF"):
        logger.info("PDF link %s didn't return a usable PDF", url)
        return None
    return content


# --- Making it tablet-sized --------------------------------------------------


def _from_html(paper: ArticleORM) -> Optional[bytes]:
    arxiv = arxiv_id(paper)
    if not arxiv:
        return None
    try:
        return reflow.render(reflow.arxiv_html_url(arxiv))
    except Exception as exc:  # noqa: BLE001 - the PDF route is still there
        logger.warning("rendering arXiv HTML for paper %s failed: %s", paper.id, exc)
        return None


def _relaid(paper: ArticleORM, pdf: bytes) -> bytes:
    try:
        return columns.relayout(pdf)
    except Exception as exc:  # noqa: BLE001 - the PDF as it is still reads, just small
        logger.warning("re-laying paper %s's PDF failed: %s", paper.id, exc)
        return pdf


def tablet_pdf(paper: ArticleORM) -> Optional[bytes]:
    """``paper`` as a PDF for the tablet; None if there's no open-access copy.

    arXiv HTML if there is some, else the open-access PDF re-laid in columns, else
    that PDF unchanged. A failure to render or re-lay falls through to the next
    option; only fetching the PDF raises.
    """
    pdf = _from_html(paper)
    if pdf is not None:
        logger.info("paper %s: printed from arXiv HTML", paper.id)
        return pdf
    url = find_pdf_url(paper)
    pdf = fetch_pdf(url) if url else None
    if pdf is None:
        return None
    logger.info("paper %s: re-laying the PDF in columns", paper.id)
    return _relaid(paper, pdf)


# --- Cover page ---------------------------------------------------------------


def _e(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _authors(authors: list[str] | None) -> str:
    authors = list(authors or [])
    if len(authors) > 4:
        return ", ".join(authors[:3]) + " et al."
    return ", ".join(authors)


_ANSWER_LABELS = {
    "strongly_agree": "strongly agree", "agree": "agree", "neutral": "neutral",
    "disagree": "disagree", "strongly_disagree": "strongly disagree",
    "cant_tell": "can't tell",
}


def _rubric_statements(profile_name: Optional[str]) -> dict:
    """Statement id -> text from the paper's profile; empty if it can't be loaded."""
    from content_screening.profile import ProfileError, load_profile

    if not profile_name:
        return {}
    try:
        return {s.id: s.statement for s in load_profile(profile_name).rubric}
    except ProfileError:
        return {}


def _rubric_rows(paper: ArticleORM) -> str:
    """The rubric answers (REWORK_PLAN 1.3), one row per statement.

    ``rubric_answers`` is ``{statement_id: {answer, justification}}`` as stored
    by the screener; statement text comes from the paper's profile, falling back
    to the id. Anything malformed is skipped.
    """
    answers = getattr(paper, "rubric_answers", None)
    if not isinstance(answers, dict):
        return ""
    statements = _rubric_statements(getattr(paper, "profile", None))
    rows = []
    for statement_id, answer in answers.items():
        if not isinstance(answer, dict) or "answer" not in answer:
            continue
        rows.append(
            f"<tr><td class='stmt'>{_e(statements.get(statement_id, statement_id))}</td>"
            f"<td class='ans'>{_e(_ANSWER_LABELS.get(answer['answer'], answer['answer']))}</td>"
            f"<td>{_e(answer.get('justification'))}</td></tr>"
        )
    if not rows:
        return ""
    return "<h3>Rubric</h3><table>" + "".join(rows) + "</table>"


_COVER_CSS = """
* { font-family: sans-serif; }
.kicker { font-size: 11pt; color: #666; margin: 0; }
.title { font-size: 26pt; font-weight: bold; line-height: 1.15; margin: 6pt 0 10pt 0; }
.score { font-size: 20pt; margin: 0 0 8pt 0; }
.verdict { font-size: 17pt; line-height: 1.3; margin: 0; }
h3 { font-size: 11pt; margin: 8pt 0 3pt 0; }
p, td { font-size: 9.5pt; line-height: 1.3; }
.meta { color: #333; margin: 0 0 2pt 0; }
table { border-collapse: collapse; width: 100%; }
td { border-bottom: 0.5pt solid #bbb; padding: 2pt 4pt; vertical-align: top; }
td.stmt { width: 120pt; }
td.ans { width: 60pt; font-weight: bold; }
"""


def build_cover(paper: ArticleORM, size: fitz.Rect = A4) -> bytes:
    """A one-page PDF summarising why ``paper`` is on the reading list, ``size`` big."""
    metadata = paper.metadata_ or {}
    score = (f"Score {paper.llm_interest_score:.2f}"
             if paper.llm_interest_score is not None else "Score: n/a")
    top = (
        f"<p class='kicker'>Why this is on your reading list</p>"
        f"<p class='title'>{_e(paper.title)}</p>"
        f"<p class='score'>{_e(score)}</p>"
        f"<p class='verdict'>{_e(paper.llm_reasoning or 'No screening summary recorded.')}</p>"
    )

    venue_date = " · ".join(
        v for v in (metadata.get("venue"), metadata.get("publication_date")) if v)
    details = [f"<p class='meta'><b>Authors:</b> {_e(_authors(paper.authors))}</p>"]
    if venue_date:
        details.append(f"<p class='meta'><b>Published:</b> {_e(venue_date)}</p>")
    if paper.surfaced_by:
        details.append(f"<p class='meta'><b>Surfaced by:</b> {_e(', '.join(paper.surfaced_by))}</p>")
    if paper.llm_tags:
        details.append(f"<p class='meta'><b>Tags:</b> {_e(', '.join(paper.llm_tags))}</p>")
    details.append(_rubric_rows(paper))
    if paper.abstract:
        details.append(f"<h3>Abstract</h3><p>{_e(paper.abstract)}</p>")

    doc = fitz.open()
    width, height = size.width, size.height
    page = doc.new_page(width=width, height=height)
    margin = 48 * width / A4.width
    left = max(margin, reflow.MARGIN_MM[3] * 72 / 25.4)   # clear of the tablet's menu
    right = width - margin
    split = height * 0.45
    # The top half is the thumbnail: it shrinks only a little. The detail shrinks to fit.
    page.insert_htmlbox(fitz.Rect(left, margin, right, split),
                        top, css=_COVER_CSS, scale_low=0.6)
    page.draw_line((left, split + 6), (right, split + 6),
                   color=(0.6, 0.6, 0.6), width=0.75)
    page.insert_htmlbox(fitz.Rect(left, split + 16, right, height - margin - 14),
                        "".join(details), css=_COVER_CSS, scale_low=0)
    page.insert_text((left, height - margin + 4), f"{COVER_MARKER} · paper {paper.id}",
                     fontsize=7, color=(0.55, 0.55, 0.55))
    return doc.tobytes()


def page_stamp(paper_id: int, index: int) -> str:
    """The stamp on page ``index`` (0 is the cover) of paper ``paper_id``'s upload."""
    return f"{PAGE_STAMP}:{paper_id}:{index}"


def with_cover(paper: ArticleORM, pdf: bytes) -> bytes:
    """``pdf`` with a cover page the size of its first page in front, every page stamped.

    The stamp is invisible text (render mode 3) in the bottom-left corner; it adds no
    drawings, so the ink count the annotation pipeline relies on is unchanged.
    """
    with fitz.open(stream=pdf, filetype="pdf") as original:
        size = original[0].rect if original.page_count else A4
        with fitz.open(stream=build_cover(paper, size), filetype="pdf") as out:
            out.insert_pdf(original)
            for index, page in enumerate(out):
                corner = page.rect.bottom_left + (2, -2)
                page.insert_text(corner, page_stamp(paper.id, index), fontsize=2,
                                 render_mode=3)
            return out.tobytes(garbage=3, deflate=True)


# --- Upload -------------------------------------------------------------------


def drive_filename(paper: ArticleORM) -> str:
    """``<id> - <short title>.pdf``: the leading ID matches an export back to its paper."""
    title = _UNSAFE.sub(" ", paper.title or "untitled")
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > TITLE_CHARS:
        title = title[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(" .,;:-")
    return f"{paper.id} - {title or 'untitled'}.pdf"


def local_copy_path(paper_id: int) -> Path:
    """Where the exact uploaded file is kept, for comparing annotated exports against."""
    return data_path("papers", f"{paper_id}.pdf")


def send_to_tablet(paper: ArticleORM) -> Optional[str]:
    """Upload ``paper`` (tablet-sized, with cover) to the To read folder; its Drive file ID.

    Returns None when there's no open-access PDF. Idempotent: if a file of the same
    name is already in the folder (a retry after the upload succeeded but recording
    it didn't), that one is reused.
    """
    folder = drive.ensure_folder(TO_READ)
    name = drive_filename(paper)
    existing = [f for f in drive.list_files(folder) if f["name"] == name]
    if existing:
        return existing[0]["id"]

    pdf = tablet_pdf(paper)
    if pdf is None:
        return None

    upload = with_cover(paper, pdf)
    local = local_copy_path(paper.id)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(upload)
    return drive.upload_file(local, folder, name=name)
