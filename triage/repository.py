"""Database queries for the triage backend.

Thin functions over the shared ``content_screening`` ORM. They take an
explicit ``Session`` so the same logic is trivially testable and composable.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from content_screening.orm_models import ArticleORM
from triage.schemas import Decision


def get_pending_papers(
    session: Session, min_relevance_score: float = 0.0
) -> list[ArticleORM]:
    """Papers awaiting a triage decision, newest screening first.

    Only papers the screener found relevant (score strictly above
    ``min_relevance_score``) are included; the rest are noise kept only for
    record-keeping by the pipeline.
    """
    stmt = (
        select(ArticleORM)
        .where(
            ArticleORM.status == "pending",
            ArticleORM.llm_interest_score > min_relevance_score,
        )
        .order_by(ArticleORM.discovered_at.desc())
    )
    return list(session.scalars(stmt))


def get_decided_papers(session: Session, limit: int = 200) -> list[ArticleORM]:
    """Papers that have been triaged by the user (kept or dismissed), newest
    decision first. Powers the history view. Excludes ``pending``,
    ``auto_rejected`` and ``archived`` rows — none of those is a user decision."""
    stmt = (
        select(ArticleORM)
        .where(ArticleORM.status.notin_(["pending", "auto_rejected", "archived"]))
        .order_by(ArticleORM.decided_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def get_paper(session: Session, paper_id: int) -> Optional[ArticleORM]:
    """Fetch a single paper by id, or ``None`` if it doesn't exist."""
    return session.get(ArticleORM, paper_id)


def apply_decision(paper: ArticleORM, decision: Decision) -> None:
    """Record a triage decision. (Routing side effects come in later steps.)"""
    paper.status = decision
    paper.decided_at = datetime.now(timezone.utc).isoformat()


def clear_decision(paper: ArticleORM) -> None:
    """Revert a paper to the pending state (the undo action)."""
    paper.status = "pending"
    paper.decided_at = None


def within_undo_window(paper: ArticleORM, window_seconds: int) -> bool:
    """Whether ``paper`` was decided recently enough to still be undone."""
    if not paper.decided_at:
        return False
    decided = datetime.fromisoformat(paper.decided_at)
    return (datetime.now(timezone.utc) - decided).total_seconds() <= window_seconds
