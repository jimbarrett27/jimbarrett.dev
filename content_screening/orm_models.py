"""
SQLAlchemy ORM models for the content screening system.

These models are internal to the database layer. The public interface
uses the dataclass models from models.py.
"""

import json
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from content_screening.models import Article, SourceType


class JSONEncodedList(TypeDecorator):
    """Represents a list as a JSON-encoded string."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[List], dialect) -> Optional[str]:
        if value is None or value == []:
            return None
        return json.dumps(value)

    def process_result_value(self, value: Optional[str], dialect) -> List:
        if value is None:
            return []
        return json.loads(value)


class JSONEncodedDict(TypeDecorator):
    """Represents a dict as a JSON-encoded string."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[dict], dialect) -> Optional[str]:
        if value is None or value == {}:
            return None
        return json.dumps(value)

    def process_result_value(self, value: Optional[str], dialect) -> dict:
        if value is None:
            return {}
        return json.loads(value)


class NullableJSON(TypeDecorator):
    """Any JSON value, with SQL NULL kept distinct from an empty container."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect) -> Optional[str]:
        return None if value is None else json.dumps(value)

    def process_result_value(self, value: Optional[str], dialect):
        return None if value is None else json.loads(value)


class Base(DeclarativeBase):
    pass


class ArticleORM(Base):
    """SQLAlchemy model for articles table."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    doi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[List[str]] = mapped_column(JSONEncodedList, nullable=True)
    categories: Mapped[List[str]] = mapped_column(JSONEncodedList, nullable=True)
    keywords_matched: Mapped[List[str]] = mapped_column(JSONEncodedList, nullable=True)
    surfaced_by: Mapped[List[str]] = mapped_column(JSONEncodedList, nullable=True)
    discovered_at: Mapped[int] = mapped_column(Integer, nullable=False)
    llm_interest_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_tags: Mapped[List[str]] = mapped_column(JSONEncodedList, nullable=True)
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    # 'metadata' is reserved in SQLAlchemy, so we use 'metadata_' as the Python attribute
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONEncodedDict, nullable=True
    )

    # --- Interest profile (migration 006) ---
    # Profile the article was screened under. Every row has one: the PV era was
    # backfilled to 'pv'. Nullable at the DB level only because SQLite can't add
    # a NOT NULL column without a default.
    profile: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screening_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rubric_answers: Mapped[Optional[dict]] = mapped_column(NullableJSON, nullable=True)

    # --- Triage fields (consumed by the triage UI; the Telegram bot ignores them) ---
    # Screening LLM routing hint: 'file' | 'skim' | 'deep'.
    suggested_depth: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Triage decision lifecycle:
    #   'pending'       – awaiting user decision (relevant papers only)
    #   'kept'          – user kept it → Zotero + Obsidian
    #   'dismissed'     – user rejected it
    #   'auto_rejected' – LLM screened out (score 0), never shown to user
    #   'archived'      – screened as relevant but never triaged before its
    #                     profile was retired (the PV queue); never shown
    # Legacy values 'deep' / 'filed' map to 'kept' (Chunk C migration).
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    decided_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    zotero_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    zotero_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    obsidian_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    obsidian_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # --- reMarkable (kept papers sent to the tablet via Drive; migration 005) ---
    drive_file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    drive_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # No open-access PDF found: Drive routing is complete without an upload.
    pdf_unavailable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    routing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_type", "external_id", name="uq_source_external"),
        Index("idx_articles_source_type", "source_type"),
        Index("idx_articles_discovered_at", "discovered_at"),
        Index("idx_articles_doi", "doi"),
        Index("idx_articles_status", "status", "discovered_at"),
        Index("idx_articles_profile", "profile", "status"),
        Index(
            "idx_articles_retry",
            "next_retry_at",
            sqlite_where=text("next_retry_at IS NOT NULL"),
        ),
    )


# The two tables below belong to the retired Telegram rating flow. Nothing reads
# or writes them any more; they are kept so the old ratings survive.


class ArticleRatingORM(Base):
    """SQLAlchemy model for article_ratings table."""

    __tablename__ = "article_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    rated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class PendingNotificationORM(Base):
    """SQLAlchemy model for pending_article_notifications table."""

    __tablename__ = "pending_article_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    notified_at: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_received: Mapped[int] = mapped_column(Integer, default=0)


class ScanHistoryORM(Base):
    """SQLAlchemy model for scan_history table."""

    __tablename__ = "scan_history"

    source_type: Mapped[str] = mapped_column(Text, primary_key=True)
    last_scan_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    articles_found: Mapped[int] = mapped_column(Integer, default=0)
    articles_interesting: Mapped[int] = mapped_column(Integer, default=0)


# Conversion functions between ORM models and dataclasses


def article_orm_to_dataclass(orm: ArticleORM) -> Article:
    """Convert an ArticleORM instance to an Article dataclass."""
    return Article(
        id=orm.id,
        external_id=orm.external_id,
        source_type=SourceType(orm.source_type),
        title=orm.title,
        abstract=orm.abstract,
        url=orm.url,
        doi=orm.doi,
        authors=orm.authors or [],
        categories=orm.categories or [],
        keywords_matched=orm.keywords_matched or [],
        surfaced_by=orm.surfaced_by or [],
        discovered_at=orm.discovered_at,
        llm_interest_score=orm.llm_interest_score,
        llm_reasoning=orm.llm_reasoning,
        llm_tags=orm.llm_tags or [],
        suggested_depth=orm.suggested_depth,
        embedding=orm.embedding,
        metadata=orm.metadata_ or {},
        profile=orm.profile,
        screening_model=orm.screening_model,
        rubric_answers=orm.rubric_answers,
    )


def article_dataclass_to_orm(
    article: Article, discovered_at: int, status: str = "pending"
) -> ArticleORM:
    """Convert an Article dataclass to an ArticleORM instance."""
    return ArticleORM(
        external_id=article.external_id,
        source_type=article.source_type.value,
        title=article.title,
        abstract=article.abstract,
        url=article.url,
        doi=article.doi,
        authors=article.authors if article.authors else None,
        categories=article.categories if article.categories else None,
        keywords_matched=article.keywords_matched if article.keywords_matched else None,
        surfaced_by=article.surfaced_by if article.surfaced_by else None,
        discovered_at=discovered_at,
        llm_interest_score=article.llm_interest_score,
        llm_reasoning=article.llm_reasoning,
        llm_tags=article.llm_tags if article.llm_tags else None,
        suggested_depth=article.suggested_depth,
        embedding=article.embedding,
        metadata_=article.metadata if article.metadata else None,
        profile=article.profile,
        screening_model=article.screening_model,
        rubric_answers=article.rubric_answers,
        status=status,
    )

