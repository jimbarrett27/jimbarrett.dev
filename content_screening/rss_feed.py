"""
Generic RSS feed fetching and processing.
"""

import hashlib
import re
import time
from datetime import date
from typing import List, Optional

import feedparser  # type: ignore
from html2text import html2text

from content_screening.constants import SCAN_LOOKBACK_DAYS, find_matching_keywords
from content_screening.models import Article, SourceType
from content_screening.profile import FeedConfig, Profile, get_active_profile
from util.logging_util import setup_logger

logger = setup_logger(__name__)

__all__ = ["FeedConfig", "fetch_rss_articles"]


def _generate_external_id(entry: dict, feed_url: str) -> str:
    """Generate a unique external ID for an RSS entry.

    Uses the entry's id/guid if available, otherwise creates a hash
    from the URL and title.
    """
    entry_id = entry.get("id") or entry.get("link")
    if entry_id:
        return entry_id

    # Fallback: hash of feed URL + title
    title = entry.get("title", "")
    hash_input = f"{feed_url}:{title}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:32]


def _extract_authors(entry: dict) -> List[str]:
    """Extract author names from an RSS entry.

    Handles various formats:
    - String with semicolon/comma separated names (IEEE)
    - List of dicts with 'name' key (Lancet, Wiley)
    - Single 'author' string
    """
    if "authors" in entry:
        authors = entry["authors"]
        if isinstance(authors, str):
            # IEEE format: "Name1;Name2;" or "Name1, Name2"
            authors = authors.replace(";", ",")
            return [a.strip() for a in authors.split(",") if a.strip()]
        elif isinstance(authors, list):
            # List of dicts with 'name' key
            result = []
            for author in authors:
                if isinstance(author, dict):
                    name = author.get("name", "")
                    # Wiley format may have newlines
                    name = name.replace("\n", ", ")
                    result.append(name.strip())
                elif isinstance(author, str):
                    result.append(author.strip())
            return [a for a in result if a]
    elif "author" in entry:
        author = entry["author"]
        if isinstance(author, str):
            return [author.strip()] if author.strip() else []
    return []


# Many journal RSS links ARE DOIs (e.g. Wiley: https://doi.org/10.1111/...).
# Extracting it gives a cross-source dedup key for free.
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


def _doi_from_link(link: str) -> Optional[str]:
    """Pull a normalized DOI out of an RSS link, if it contains one."""
    if not link:
        return None
    match = _DOI_RE.search(link)
    return match.group(0).lower() if match else None


def _extract_summary(entry: dict) -> str:
    """Extract and clean summary/description from an RSS entry."""
    summary = entry.get("summary", "") or entry.get("description", "")
    if not summary:
        return ""
    # Convert HTML to plain text
    return html2text(summary).strip()


# ScienceDirect/Elsevier feeds carry no author field and no abstract; the summary
# is just a metadata blob, e.g. "Publication date: …\n**Source:** …\nAuthor(s): a, b, c".
_AUTHORS_LINE_RE = re.compile(r"Author\(s\):\s*(.+)", re.IGNORECASE)
_PREAMBLE_LINE_RE = re.compile(
    r"^\s*(?:Publication date:|\*{0,2}Source:\*{0,2}|Author\(s\):).*$",
    re.IGNORECASE | re.MULTILINE,
)


def _authors_from_summary(text: str) -> List[str]:
    """Parse an Elsevier 'Author(s): a, b, c' line out of the summary text."""
    match = _AUTHORS_LINE_RE.search(text)
    if not match:
        return []
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


def _strip_metadata_preamble(text: str) -> str:
    """Drop the Elsevier 'Publication date / Source / Author(s)' lines, leaving
    only the real abstract (often empty for these feeds — better empty than noise)."""
    cleaned = _PREAMBLE_LINE_RE.sub("", text)
    return re.sub(r"\n{2,}", "\n\n", cleaned).strip()


def _find_matching_keywords(text: str, keywords) -> List[str]:
    """Find profile keywords that match in the given text (delegates to the shared helper)."""
    return find_matching_keywords(text, keywords)


def _is_recent(entry: dict, lookback_days: int = SCAN_LOOKBACK_DAYS) -> bool:
    """Whether an entry is within the look-back window.

    Undated entries are kept (return True) — many journal feeds expose no parsed
    date, and the old "exactly today" gate dropped them entirely. Deduplication
    by external_id (in the scanner) prevents anything being reprocessed.
    """
    published_parsed = entry.get("published_parsed")
    if published_parsed is None:
        return True

    entry_date = date(
        published_parsed.tm_year, published_parsed.tm_mon, published_parsed.tm_mday
    )
    return (date.today() - entry_date).days <= lookback_days


def fetch_rss_articles(
    feed_configs: List[FeedConfig] = None,
    filter_by_keywords: bool = True,
    keywords: set = None,
    profile: Profile = None,
) -> List[Article]:
    """
    Fetch articles from RSS feeds.

    Args:
        feed_configs: Feed configurations to fetch from. Defaults to the profile's.
        filter_by_keywords: Whether to filter by the profile's keywords.
        keywords: Keywords to filter by. Defaults to the profile's.
        profile: Interest profile. Defaults to the active one.

    Returns:
        List of Article objects matching the criteria.
    """
    if feed_configs is None or keywords is None:
        profile = profile or get_active_profile()
    if feed_configs is None:
        feed_configs = list(profile.feeds)
    if keywords is None:
        keywords = profile.keywords

    if not feed_configs:
        logger.warning("No RSS feeds configured")
        return []

    seen_ids = set()
    articles = []
    discovered_at = int(time.time())

    for feed_config in feed_configs:
        try:
            rss_content = feedparser.parse(feed_config.url)
        except Exception as e:
            logger.error(f"Error fetching RSS for {feed_config.name}: {e}")
            continue

        status = rss_content.get("status")
        if status and status >= 400:
            logger.warning(f"HTTP {status} for feed {feed_config.name}")
            continue

        for entry in rss_content.get("entries", []):
            external_id = _generate_external_id(entry, feed_config.url)

            if external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            # Only consider articles within the look-back window (dedup does the rest)
            if not _is_recent(entry):
                continue

            title = entry.get("title", "").strip()
            if not title:
                continue

            raw_summary = _extract_summary(entry)
            # Elsevier feeds bury authors in the summary and have no author field;
            # parse them out before stripping the metadata preamble from the abstract.
            authors = _extract_authors(entry) or _authors_from_summary(raw_summary)
            abstract = _strip_metadata_preamble(raw_summary)
            link = entry.get("link", "")
            if not link:
                continue

            if filter_by_keywords:
                search_text = f"{title} {abstract}"
                matching_keywords = _find_matching_keywords(search_text, keywords)
                if not matching_keywords:
                    continue
            else:
                matching_keywords = []

            article = Article(
                external_id=external_id,
                source_type=SourceType.RSS,
                title=title,
                abstract=abstract,
                doi=_doi_from_link(link),
                url=link,
                authors=authors,
                categories=[feed_config.name],
                keywords_matched=matching_keywords,
                surfaced_by=["keyword"] if matching_keywords else [],
                discovered_at=discovered_at,
                metadata={
                    "feed_url": feed_config.url,
                    "feed_category": feed_config.category,
                    "published": entry.get("published", ""),
                },
            )
            articles.append(article)

    logger.info(f"Fetched {len(articles)} articles matching criteria from {len(feed_configs)} RSS feeds")
    return articles
