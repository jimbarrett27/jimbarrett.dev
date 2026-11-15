"""Kept papers → a PDF with a screening cover page → ``reMarkable/Papers/To read``.

Called from the triage backend's routing (:mod:`triage.routing`) when a paper is
kept. The steps:

1. **Find an open-access PDF.** arXiv papers have one by construction; anything
   else is looked up on OpenAlex (``best_oa_location``, then any location with a
   ``pdf_url``). Publishers often answer a PDF link with an HTML page, so only a
   response that is actually a PDF counts.
2. **Prepend a cover page** summarising why the paper is there: legible as the
   tablet's thumbnail at the top, the screening detail below. Its text carries
   :data:`COVER_MARKER` so the annotation pipeline can recognise it.
3. **Upload** as ``<id> - <short title>.pdf``. The leading ID is how an annotated
   export is matched back to its paper. A copy of exactly what was uploaded is kept
   under ``papers/`` in the data dir, for comparing annotated exports against.

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
from util.logging_util import setup_logger
from util.paths import data_path

logger = setup_logger(__name__)

TO_READ = "reMarkable/Papers/To read"
COVER_MARKER = "triage-cover"
USER_AGENT = "jimbarrett.dev-triage/1.0"
MAX_PDF_BYTES = 60 * 1024 * 1024
TITLE_CHARS = 60
A4 = fitz.paper_rect("a4")

_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')



# --- Finding the PDF ----------------------------------------------------------


def _openalex_pdf_url(paper: ArticleORM) -> Optional[str]:
    # Imported here: content_screening.openalex pulls in the whole discovery stack.
    from content_screening.openalex import _get, load_discovery_config

    metadata = paper.metadata_ or {}
    if metadata.get("openalex_id"):
        key = metadata["openalex_id"]
    elif paper.doi:
        key = f"doi:{paper.doi}"
    else:
        return None
    try:
        work = _get(f"works/{key}", {"select": "best_oa_location,locations"},
                    load_discovery_config().mailto)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise
    candidates = [work.get("best_oa_location")] + list(work.get("locations") or [])
    for location in candidates:
        if location and location.get("pdf_url"):
            return location["pdf_url"]
    return None


def find_pdf_url(paper: ArticleORM) -> Optional[str]:
    """Where to download an open-access PDF of ``paper``, or None if there isn't one."""
    if paper.source_type == "arxiv":
        return f"https://arxiv.org/pdf/{paper.external_id}"
    match = _ARXIV_DOI.match(paper.doi or "")
    if match:
        return f"https://arxiv.org/pdf/{match.group(1)}"
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


# --- Cover page ---------------------------------------------------------------


def _e(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _authors(authors: list[str] | None) -> str:
    authors = list(authors or [])
    if len(authors) > 4:
        return ", ".join(authors[:3]) + " et al."
    return ", ".join(authors)


def _rubric_rows(paper: ArticleORM) -> str:
    """Rubric answers, once the rubric scoring exists (REWORK_PLAN §1.3).

    Expected shape: a list of {statement, answer (-2..2 or None), justification}.
    Anything else is ignored, so this keeps working while that shape settles.
    """
    answers = getattr(paper, "rubric_answers", None)
    if not isinstance(answers, list):
        return ""
    labels = {2: "strongly agree", 1: "agree", 0: "neutral", -1: "disagree",
              -2: "strongly disagree", None: "can't tell"}
    rows = []
    for answer in answers:
        if not isinstance(answer, dict) or "statement" not in answer:
            continue
        rows.append(
            f"<tr><td class='stmt'>{_e(answer['statement'])}</td>"
            f"<td class='ans'>{_e(labels.get(answer.get('answer'), answer.get('answer')))}</td>"
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
td.stmt { width: 180pt; }
td.ans { width: 80pt; font-weight: bold; }
"""


def build_cover(paper: ArticleORM) -> bytes:
    """A one-page A4 PDF summarising why ``paper`` is on the reading list."""
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
    page = doc.new_page(width=A4.width, height=A4.height)
    margin = 48
    split = A4.height * 0.45
    # The top half is the thumbnail: it never shrinks. The detail shrinks to fit.
    page.insert_htmlbox(fitz.Rect(margin, margin, A4.width - margin, split),
                        top, css=_COVER_CSS, scale_low=0.6)
    page.draw_line((margin, split + 6), (A4.width - margin, split + 6),
                   color=(0.6, 0.6, 0.6), width=0.75)
    page.insert_htmlbox(fitz.Rect(margin, split + 16, A4.width - margin, A4.height - margin - 14),
                        "".join(details), css=_COVER_CSS, scale_low=0)
    page.insert_text((margin, A4.height - margin + 4), f"{COVER_MARKER} · paper {paper.id}",
                     fontsize=7, color=(0.55, 0.55, 0.55))
    return doc.tobytes()


def with_cover(paper: ArticleORM, pdf: bytes) -> bytes:
    """``pdf`` with the cover page in front."""
    with fitz.open(stream=build_cover(paper), filetype="pdf") as out, \
            fitz.open(stream=pdf, filetype="pdf") as original:
        out.insert_pdf(original)
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
    """Upload ``paper`` (with cover) to the To read folder; its Drive file ID.

    Returns None when there's no open-access PDF. Idempotent: if a file of the same
    name is already in the folder (a retry after the upload succeeded but recording
    it didn't), that one is reused.
    """
    url = find_pdf_url(paper)
    pdf = fetch_pdf(url) if url else None
    if pdf is None:
        return None

    folder = drive.ensure_folder(TO_READ)
    name = drive_filename(paper)
    existing = [f for f in drive.list_files(folder) if f["name"] == name]

    upload = with_cover(paper, pdf)
    local = local_copy_path(paper.id)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(upload)

    if existing:
        return existing[0]["id"]
    return drive.upload_file(local, folder, name=name)
