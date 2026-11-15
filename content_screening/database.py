"""
Database operations for the content screening system.

Uses SQLAlchemy ORM for database access. The public API uses dataclass models
from models.py, with conversion to/from ORM models handled internally.
"""

import html
import re
import time
from typing import Optional, Tuple

from sqlalchemy import select, exists

from content_screening.db_engine import get_engine, get_session
from content_screening.models import Article, SourceType
from content_screening.orm_models import (
    Base,
    ArticleORM,
    ScanHistoryORM,
    article_orm_to_dataclass,
    article_dataclass_to_orm,
)


def init_db():
    """Initialize the database schema."""
    engine = get_engine()
    Base.metadata.create_all(engine)


# --- Deduplication ----------------------------------------------------------
#
# The dedup index holds three identity keys so a paper is skipped before insert:
#   1. (source_type, external_id) -- the AUTHORITATIVE same-source key (matches
#      the table's unique constraint). Always works, even with no DOI/title.
#   2. normalized DOI -- the robust cross-source key (same paper from arXiv / a
#      journal RSS feed / OpenAlex gets different external_ids but one DOI).
#   3. normalized title -- cross-source fallback when a DOI is absent (the only
#      reliable arXiv<->OpenAlex bridge).
# Without (1), a re-scanned paper that has no DOI and a title that normalizes to
# nothing (e.g. an all-Cyrillic title) would slip past (2)/(3) and hit the unique
# constraint on insert.

# Keep Unicode word characters (so non-Latin titles don't collapse to empty);
# everything else (punctuation, whitespace) becomes a single space.
_TITLE_NONWORD_RE = re.compile(r"[^\w]+", re.UNICODE)


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Normalize a DOI to a bare lowercase identifier (no URL prefix)."""
    if not doi:
        return None
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi or None


def normalize_title(title: Optional[str]) -> Optional[str]:
    """Normalize a title for fuzzy identity: decode HTML entities, drop tags,
    lowercase, and collapse non-word runs to single spaces. Unicode-aware so
    non-Latin titles still yield a usable key."""
    if not title:
        return None
    text = html.unescape(title)
    # Drop HTML tags that sometimes survive in feed titles (e.g. <em>...</em>).
    text = re.sub(r"<[^>]+>", "", text)
    text = _TITLE_NONWORD_RE.sub(" ", text.lower()).strip()
    return text or None


def _article_key(source_type, external_id) -> tuple:
    """The (source_type, external_id) identity tuple, source_type as its value."""
    st = source_type.value if isinstance(source_type, SourceType) else source_type
    return (st, external_id)


def load_dedup_index() -> Tuple[set, set, set]:
    """Load existing articles' identity keys into in-memory sets.

    Returns ``(doi_set, title_set, id_set)`` where ``id_set`` holds
    ``(source_type, external_id)`` tuples. A few thousand rows is trivial to hold
    in memory; built once per scan and consulted before each insert.
    """
    doi_set: set = set()
    title_set: set = set()
    id_set: set = set()
    with get_session() as session:
        rows = session.execute(
            select(
                ArticleORM.doi, ArticleORM.title,
                ArticleORM.source_type, ArticleORM.external_id,
            )
        ).all()
    for doi, title, source_type, external_id in rows:
        nd = normalize_doi(doi)
        if nd:
            doi_set.add(nd)
        nt = normalize_title(title)
        if nt:
            title_set.add(nt)
        id_set.add(_article_key(source_type, external_id))
    return doi_set, title_set, id_set


def is_duplicate(article: Article, doi_set: set, title_set: set, id_set: set) -> bool:
    """Whether ``article`` is already known, by exact (source, external_id) key
    (authoritative), then DOI, then normalized title (cross-source)."""
    if _article_key(article.source_type, article.external_id) in id_set:
        return True
    nd = normalize_doi(article.doi)
    if nd and nd in doi_set:
        return True
    nt = normalize_title(article.title)
    if nt and nt in title_set:
        return True
    return False


def add_to_dedup_index(article: Article, doi_set: set, title_set: set, id_set: set) -> None:
    """Record an article's identity keys so later candidates in the same run
    dedup against it (within-run, across sources)."""
    id_set.add(_article_key(article.source_type, article.external_id))
    nd = normalize_doi(article.doi)
    if nd:
        doi_set.add(nd)
    nt = normalize_title(article.title)
    if nt:
        title_set.add(nt)


def insert_article(article: Article, status: str = "pending") -> int:
    """Insert a new article into the database.

    Returns the article id.
    """
    discovered_at = article.discovered_at or int(time.time())
    orm = article_dataclass_to_orm(article, discovered_at, status=status)

    with get_session() as session:
        session.add(orm)
        session.flush()
        return orm.id


def get_article_by_external_id(source_type: SourceType, external_id: str) -> Optional[Article]:
    """Get an article by its external ID and source type."""
    with get_session() as session:
        stmt = select(ArticleORM).where(
            ArticleORM.source_type == source_type.value,
            ArticleORM.external_id == external_id,
        )
        orm = session.execute(stmt).scalar_one_or_none()
        if orm is None:
            return None
        return article_orm_to_dataclass(orm)


def get_article_by_id(article_id: int) -> Optional[Article]:
    """Get an article by its database ID."""
    with get_session() as session:
        orm = session.get(ArticleORM, article_id)
        if orm is None:
            return None
        return article_orm_to_dataclass(orm)


def article_exists(source_type: SourceType, external_id: str) -> bool:
    """Check if an article already exists in the database."""
    with get_session() as session:
        stmt = select(
            exists().where(
                ArticleORM.source_type == source_type.value,
                ArticleORM.external_id == external_id,
            )
        )
        return session.execute(stmt).scalar()


def get_last_scan_time(source_type: SourceType) -> Optional[int]:
    """Get the last scan time for a source type."""
    with get_session() as session:
        orm = session.get(ScanHistoryORM, source_type.value)
        if orm is None:
            return None
        return orm.last_scan_epoch


def update_scan_history(source_type: SourceType, articles_found: int = 0, articles_interesting: int = 0):
    """Update the scan history for a source type."""
    with get_session() as session:
        orm = session.get(ScanHistoryORM, source_type.value)
        if orm is None:
            orm = ScanHistoryORM(
                source_type=source_type.value,
                last_scan_epoch=int(time.time()),
                articles_found=articles_found,
                articles_interesting=articles_interesting,
            )
            session.add(orm)
        else:
            orm.last_scan_epoch = int(time.time())
            orm.articles_found = articles_found
            orm.articles_interesting = articles_interesting
