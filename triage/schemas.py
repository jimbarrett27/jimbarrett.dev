"""Pydantic response models for the triage API.

These are the public JSON shapes the Angular frontend consumes. They are kept
separate from the ``content_screening`` dataclasses/ORM so the wire format can
evolve independently of the storage model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from content_screening.orm_models import ArticleORM

# A triage decision. The value doubles as the resulting paper `status`.
Decision = Literal["kept", "dismissed"]


class PaperOut(BaseModel):
    """A single paper as presented in the triage queue / history."""

    id: int
    title: str
    authors: list[str]
    source_type: str
    url: str
    abstract: str | None
    # When the screening pipeline discovered the paper (UTC).
    discovered_at: datetime
    llm_interest_score: float | None
    # The "why this surfaced" reason shown on the card.
    llm_reasoning: str | None
    llm_tags: list[str]
    # Discovery signal(s) that surfaced the paper: 'keyword' | 'topic' |
    # 'author' | 'citation' | 'institution'.
    surfaced_by: list[str]
    # PV-era screener hint ('deep' | 'skim' | 'file'); null for new papers.
    suggested_depth: str | None
    status: str
    # Set when a triage decision is made; null while pending.
    decided_at: datetime | None
    # Routing outcomes (populated as papers are routed to Zotero/Obsidian).
    zotero_key: str | None
    zotero_error: str | None
    obsidian_path: str | None
    obsidian_error: str | None
    # reMarkable via Drive: the uploaded file, the last failure, or no open-access PDF.
    drive_file_id: str | None = None
    drive_error: str | None = None
    pdf_unavailable: bool = False
    # Retry bookkeeping for failed routing (step 8). `next_retry_at` is the
    # scheduled time of the next attempt, or null when complete / given up.
    routing_attempts: int
    next_retry_at: datetime | None

    @classmethod
    def from_orm_article(cls, article: ArticleORM) -> "PaperOut":
        return cls(
            id=article.id,
            title=article.title,
            authors=article.authors or [],
            source_type=article.source_type,
            url=article.url,
            abstract=article.abstract,
            discovered_at=datetime.fromtimestamp(
                article.discovered_at, tz=timezone.utc
            ),
            llm_interest_score=article.llm_interest_score,
            llm_reasoning=article.llm_reasoning,
            llm_tags=article.llm_tags or [],
            surfaced_by=article.surfaced_by or [],
            suggested_depth=article.suggested_depth,
            status=article.status,
            decided_at=article.decided_at,
            zotero_key=article.zotero_key,
            zotero_error=article.zotero_error,
            obsidian_path=article.obsidian_path,
            obsidian_error=article.obsidian_error,
            drive_file_id=article.drive_file_id,
            drive_error=article.drive_error,
            pdf_unavailable=bool(article.pdf_unavailable),
            routing_attempts=article.routing_attempts,
            next_retry_at=article.next_retry_at,
        )
