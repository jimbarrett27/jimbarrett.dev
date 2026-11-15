"""Routes triage decisions into external tools (Zotero, the reMarkable via Drive, Obsidian).

Side effects mutate the paper row in place (``zotero_key``/``zotero_error`` and
``obsidian_path``/``obsidian_error``); the caller persists them. Failures are
recorded on the row rather than raised, so a decision always succeeds even if
routing doesn't — matching the spec's best-effort tolerance.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from content_screening.orm_models import ArticleORM
from triage.config import Settings
from remarkable_drive import outbound
from triage import obsidian, zotero
from util.logging_util import setup_logger

logger = setup_logger(__name__)

# `kept` → Zotero + Obsidian; legacy `deep` and `filed` are preserved here so
# any half-routed row written before the migration can still complete routing.
# `dismissed` → nothing.
_ZOTERO_DECISIONS = {"kept", "deep"}
_OBSIDIAN_DECISIONS = {"kept", "deep", "filed"}
# Only fresh `kept` decisions go to the tablet; legacy rows predate it.
_DRIVE_DECISIONS = {"kept"}

# Upper bound on the exponential backoff between retries.
_RETRY_CAP_SECONDS = 3600


def route_decision(paper: ArticleORM, settings: Settings) -> None:
    """Perform the external side effects for a freshly-decided paper."""
    # Zotero first so a fresh `kept` stub can embed the returned item key.
    if paper.status in _ZOTERO_DECISIONS:
        _route_zotero(paper, settings)
    # Before Obsidian, so a paywalled paper's stub is written straight to paywalled/.
    if paper.status in _DRIVE_DECISIONS:
        _route_drive(paper, settings)
    if paper.status in _OBSIDIAN_DECISIONS:
        _route_obsidian(paper, settings)


def is_routing_complete(paper: ArticleORM, settings: Settings) -> bool:
    """Whether every *enabled* routing target for this decision has succeeded.

    A target that's disabled (e.g. Zotero off) is not considered outstanding, so
    a paper isn't retried forever waiting on a target that will never run.
    """
    if (
        paper.status in _ZOTERO_DECISIONS
        and settings.zotero_enabled
        and not paper.zotero_key
    ):
        return False
    if (
        paper.status in _DRIVE_DECISIONS
        and settings.drive_enabled
        and not (paper.drive_file_id or paper.pdf_unavailable)
    ):
        return False
    if (
        paper.status in _OBSIDIAN_DECISIONS
        and settings.obsidian_vault
        and not paper.obsidian_path
    ):
        return False
    return True


def _next_retry_at(attempts: int, settings: Settings) -> str:
    """ISO timestamp for the next retry, exponential-backoff from ``attempts``."""
    delay = min(
        settings.routing_retry_base_seconds * (2 ** (attempts - 1)),
        _RETRY_CAP_SECONDS,
    )
    return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()


def route_and_schedule(paper: ArticleORM, settings: Settings) -> None:
    """Attempt routing, then update the retry bookkeeping on the row.

    Shared by the initial (background) attempt and the retry loop. Clears
    ``next_retry_at`` once routing is complete or the attempt cap is reached;
    otherwise schedules the next backoff. ``route_decision`` is idempotent, so
    already-succeeded targets aren't re-pushed.
    """
    route_decision(paper, settings)
    if is_routing_complete(paper, settings):
        paper.next_retry_at = None
        return
    paper.routing_attempts += 1
    if paper.routing_attempts >= settings.routing_max_attempts:
        # Give up; the error stays on the row for the UI to surface.
        paper.next_retry_at = None
        logger.warning(
            "giving up routing paper %s after %d attempts",
            paper.id,
            paper.routing_attempts,
        )
    else:
        paper.next_retry_at = _next_retry_at(paper.routing_attempts, settings)


def _route_zotero(paper: ArticleORM, settings: Settings) -> None:
    if not settings.zotero_enabled:
        logger.info("Zotero not configured; skipping push for paper %s", paper.id)
        return
    # Idempotency: already pushed (safe to call repeatedly from the retry loop).
    if paper.zotero_key:
        return

    try:
        paper.zotero_key = zotero.push_paper(paper)
        paper.zotero_error = None
        logger.info("pushed paper %s to Zotero: %s", paper.id, paper.zotero_key)
    except Exception as exc:  # noqa: BLE001 - record any failure on the row
        paper.zotero_error = str(exc)
        logger.error("Zotero push failed for paper %s: %s", paper.id, exc)


def _route_drive(paper: ArticleORM, settings: Settings) -> None:
    if not settings.drive_enabled:
        logger.info("Drive not enabled; not sending paper %s to the reMarkable", paper.id)
        return
    # Idempotency: already uploaded, or already known to have no open-access PDF.
    if paper.drive_file_id or paper.pdf_unavailable:
        return

    try:
        file_id = outbound.send_to_tablet(paper)
    except Exception as exc:  # noqa: BLE001 - record any failure on the row
        paper.drive_error = str(exc)
        logger.error("Sending paper %s to the reMarkable failed: %s", paper.id, exc)
        return

    paper.drive_error = None
    if file_id:
        paper.drive_file_id = file_id
        logger.info("sent paper %s to the reMarkable: %s", paper.id, file_id)
        return

    paper.pdf_unavailable = True
    logger.info("no open-access PDF for paper %s", paper.id)
    # A stub written on an earlier attempt (while Drive was failing) is in unread/.
    if paper.obsidian_path and settings.obsidian_vault:
        paper.obsidian_path = obsidian.move_to_paywalled(
            Path(settings.obsidian_vault), paper.obsidian_path,
            settings.obsidian_inbox_subdir)


def _route_obsidian(paper: ArticleORM, settings: Settings) -> None:
    if not settings.obsidian_vault:
        logger.info("Obsidian vault not configured; skipping stub for paper %s", paper.id)
        return

    vault = Path(settings.obsidian_vault)
    # Idempotency: if we've already written this paper's stub and it still
    # exists, do nothing (safe to call repeatedly, e.g. from the retry loop).
    if paper.obsidian_path and (vault / paper.obsidian_path).exists():
        return

    try:
        rel_path = obsidian.write_stub(vault, paper, settings.obsidian_inbox_subdir)
        paper.obsidian_path = rel_path
        paper.obsidian_error = None
        logger.info("wrote Obsidian stub for paper %s: %s", paper.id, rel_path)
    except Exception as exc:  # noqa: BLE001 - record any failure on the row
        paper.obsidian_error = str(exc)
        logger.error("Obsidian write failed for paper %s: %s", paper.id, exc)
