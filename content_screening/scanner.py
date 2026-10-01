"""
Daily scan orchestration for content screening.
"""

import time
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from content_screening.arxiv_feed import fetch_arxiv_papers
from content_screening.constants import SCAN_INTERVAL_SECONDS
from content_screening.database import (
    add_to_dedup_index,
    is_duplicate,
    load_dedup_index,
    get_last_scan_time,
    insert_article,
    update_scan_history,
)
from content_screening.db_engine import get_session
from content_screening.embeddings import compute_article_embedding
from content_screening.models import Article, SourceType
from content_screening.openalex import fetch_openalex_articles
from content_screening.orm_models import ArticleORM
from content_screening.rss_feed import fetch_rss_articles
from content_screening.screener import screen_article
from util.logging_util import setup_logger

logger = setup_logger(__name__)


def process_new_articles(
    articles: List[Article],
    dedup_index: Optional[Tuple[set, set]] = None,
) -> tuple[int, int]:
    """Screen new (unseen) articles with the LLM and insert them.

    Deduplication is cross-source: a paper already present from a different feed
    (matched by DOI, or normalized title as a fallback) is skipped. Pass a shared
    ``dedup_index`` (``(doi_set, title_set)``) when scanning multiple sources in
    one run so duplicates are caught across them; otherwise one is loaded here.

    Triage replaces the old per-article Telegram notifications, so nothing is
    sent here — papers simply land in the DB for the triage queue. Returns
    ``(new_inserted, new_relevant)``.
    """
    doi_set, title_set, id_set = (
        dedup_index if dedup_index is not None else load_dedup_index()
    )

    new_inserted = 0
    new_relevant = 0
    for article in articles:
        if is_duplicate(article, doi_set, title_set, id_set):
            logger.debug(f"Duplicate article skipped: {article.external_id}")
            continue

        is_relevant, score, reasoning, tags, suggested_depth = screen_article(article)
        article.llm_interest_score = score if is_relevant else 0.0
        article.llm_reasoning = reasoning
        article.llm_tags = tags
        article.suggested_depth = suggested_depth

        # Embed every article (relevant or not) to accumulate feature vectors for
        # a future supervised relevance model — triage decisions are the labels.
        # Best-effort: None on failure, never blocks ingestion.
        article.embedding = compute_article_embedding(article)

        # Always insert (relevant ones enter the triage queue as 'pending'; the
        # rest are kept for record-keeping with status 'auto_rejected'). Guard
        # the insert so a single stray duplicate (e.g. a dedup-key miss) can't
        # abort the whole scan and drop the daily summary message.
        status = "pending" if is_relevant else "auto_rejected"
        try:
            article.id = insert_article(article, status=status)
        except IntegrityError:
            logger.warning(f"Skipping duplicate on insert: {article.external_id}")
            add_to_dedup_index(article, doi_set, title_set, id_set)
            continue
        # Record identity so later candidates in this run dedup against it.
        add_to_dedup_index(article, doi_set, title_set, id_set)
        new_inserted += 1
        if is_relevant:
            new_relevant += 1

    return new_inserted, new_relevant


def run_arxiv_scan(dedup_index: Optional[Tuple[set, set]] = None) -> tuple[int, int, int]:
    """Scan ArXiv feeds. Returns (total_found, new_inserted, new_relevant)."""
    logger.info("Starting ArXiv scan")
    articles = fetch_arxiv_papers()
    total_found = len(articles)
    new_inserted, new_relevant = process_new_articles(articles, dedup_index)
    update_scan_history(SourceType.ARXIV, total_found, new_relevant)
    logger.info(f"ArXiv scan complete: {total_found} found, {new_inserted} new, {new_relevant} relevant")
    return total_found, new_inserted, new_relevant


def run_rss_scan(dedup_index: Optional[Tuple[set, set]] = None) -> tuple[int, int, int]:
    """Scan RSS feeds. Returns (total_found, new_inserted, new_relevant)."""
    logger.info("Starting RSS scan")
    articles = fetch_rss_articles()
    total_found = len(articles)
    new_inserted, new_relevant = process_new_articles(articles, dedup_index)
    update_scan_history(SourceType.RSS, total_found, new_relevant)
    logger.info(f"RSS scan complete: {total_found} found, {new_inserted} new, {new_relevant} relevant")
    return total_found, new_inserted, new_relevant


def run_openalex_scan(dedup_index: Optional[Tuple[set, set]] = None) -> tuple[int, int, int]:
    """Scan OpenAlex. Returns (total_found, new_inserted, new_relevant)."""
    logger.info("Starting OpenAlex scan")
    articles = fetch_openalex_articles()
    total_found = len(articles)
    new_inserted, new_relevant = process_new_articles(articles, dedup_index)
    update_scan_history(SourceType.OPENALEX, total_found, new_relevant)
    logger.info(f"OpenAlex scan complete: {total_found} found, {new_inserted} new, {new_relevant} relevant")
    return total_found, new_inserted, new_relevant


def count_pending_triage() -> int:
    """How many screened-relevant papers are awaiting a triage decision."""
    with get_session() as session:
        return session.scalar(
            select(func.count())
            .select_from(ArticleORM)
            .where(ArticleORM.status == "pending", ArticleORM.llm_interest_score > 0)
        ) or 0


def run_full_scan() -> dict:
    """Run all source scans (silently) and return summary counts.

    A single dedup index is shared across the sources so the same paper arriving
    from more than one feed in this run is inserted only once. ``found`` counts
    everything the feeds returned before dedup, so zero means the feeds came back
    empty (the fetchers swallow per-feed errors) rather than "nothing new".
    """
    dedup_index = load_dedup_index()
    a_found, a_new, a_rel = run_arxiv_scan(dedup_index)
    r_found, r_new, r_rel = run_rss_scan(dedup_index)
    o_found, o_new, o_rel = run_openalex_scan(dedup_index)
    return {
        "found": a_found + r_found + o_found,
        "new": a_new + r_new + o_new,
        "relevant": a_rel + r_rel + o_rel,
        "pending": count_pending_triage(),
    }



def is_scan_due(source_type: SourceType) -> bool:
    """Check if a scan is due for the given source type."""
    last_scan = get_last_scan_time(source_type)
    if last_scan is None:
        return True
    return (time.time() - last_scan) >= SCAN_INTERVAL_SECONDS
