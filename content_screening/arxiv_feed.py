"""
ArXiv RSS feed fetching and processing.
"""

import re
import time
from datetime import date
from typing import List

import feedparser  # type: ignore
from html2text import html2text

from content_screening.constants import SCAN_LOOKBACK_DAYS, find_matching_keywords
from content_screening.models import Article, SourceType
from content_screening.profile import Profile, get_active_profile
from util.logging_util import setup_logger

logger = setup_logger(__name__)

# arXiv's RSS now prefixes each summary with e.g.
# "arXiv:2606.00027v1 Announce Type: new\nAbstract: <text>". Strip that boilerplate
# so only the abstract is screened/stored.
_ARXIV_ANNOUNCE_RE = re.compile(r"^\s*arXiv:\S+\s+Announce Type:\s+\S+\s*", re.IGNORECASE)
_ABSTRACT_LABEL_RE = re.compile(r"^\s*Abstract:\s*", re.IGNORECASE)


def _clean_summary(raw_summary: str) -> str:
    """Convert the feed summary to plain text and drop arXiv's announce prefix."""
    text = html2text(raw_summary).strip()
    text = _ARXIV_ANNOUNCE_RE.sub("", text)
    text = _ABSTRACT_LABEL_RE.sub("", text)
    return text.strip()


def get_arxiv_rss_url(arxiv_category: str) -> str:
    """Get the RSS URL for an ArXiv category."""
    return f"http://rss.arxiv.org/rss/{arxiv_category}"


def make_arxiv_url(paper_id: str) -> str:
    """Create a URL to the ArXiv abstract page for a paper."""
    return f"https://arxiv.org/abs/{paper_id}"


def _extract_paper_id(entry_id: str) -> str:
    """Extract the paper ID from an RSS entry ID.

    Handles formats like:
    - oai:arXiv.org:2601.02514v1
    - http://arxiv.org/abs/2601.02514
    """
    if entry_id.startswith("oai:"):
        return entry_id.split(":")[-1]
    return entry_id.split("/")[-1]


def _extract_authors(entry: dict) -> List[str]:
    """Extract author names from an RSS entry."""
    if 'authors' in entry:
        return [author.get('name', '') for author in entry.get('authors', [])]
    elif 'author' in entry:
        return [entry['author']]
    return []


def _find_matching_keywords(text: str, keywords) -> List[str]:
    """Find profile keywords that match in the given text (delegates to the shared helper)."""
    return find_matching_keywords(text, keywords)


def _is_recent(entry: dict, lookback_days: int = SCAN_LOOKBACK_DAYS) -> bool:
    """Whether an entry is within the look-back window.

    Undated entries are kept (return True) — deduplication by external_id stops
    them being reprocessed. This replaces the old "exactly today" gate, which
    dropped undated feeds entirely and missed anything published off the run day.
    """
    published_parsed = entry.get("published_parsed")
    if published_parsed is None:
        return True

    entry_date = date(
        published_parsed.tm_year, published_parsed.tm_mon, published_parsed.tm_mday
    )
    return (date.today() - entry_date).days <= lookback_days


def fetch_arxiv_papers(
    categories: set = None,
    filter_by_keywords: bool = True,
    keywords: set = None,
    profile: Profile = None,
) -> List[Article]:
    """
    Fetch papers from ArXiv RSS feeds.

    Args:
        categories: ArXiv categories to fetch from. Defaults to the profile's.
        filter_by_keywords: Whether to filter by the profile's keywords.
        keywords: Keywords to filter by. Defaults to the profile's.
        profile: Interest profile. Defaults to the active one.

    Returns:
        List of Article objects matching the criteria.
    """
    if categories is None or keywords is None:
        profile = profile or get_active_profile()
    if categories is None:
        categories = profile.arxiv_categories
    if keywords is None:
        keywords = profile.keywords

    seen_ids = set()
    articles = []
    discovered_at = int(time.time())

    for category in categories:
        url = get_arxiv_rss_url(category)
        try:
            rss_content = feedparser.parse(url)
        except Exception as e:
            logger.error(f"Error fetching RSS for {category}: {e}")
            continue

        for entry in rss_content.get("entries", []):
            paper_id = _extract_paper_id(entry.get("id", ""))

            if not paper_id or paper_id in seen_ids:
                continue
            seen_ids.add(paper_id)

            # Only consider papers within the look-back window (dedup does the rest)
            if not _is_recent(entry):
                continue

            title = entry.get("title", "").strip()
            abstract = _clean_summary(entry.get("summary", ""))

            if filter_by_keywords:
                search_text = f"{title} {abstract}"
                matching_keywords = _find_matching_keywords(search_text, keywords)
                if not matching_keywords:
                    continue
            else:
                matching_keywords = []

            article = Article(
                external_id=paper_id,
                source_type=SourceType.ARXIV,
                title=title,
                abstract=abstract,
                doi=f"10.48550/arxiv.{re.sub(r'v[0-9]+$', '', paper_id).lower()}",
                url=make_arxiv_url(paper_id),
                authors=_extract_authors(entry),
                categories=[category],
                keywords_matched=matching_keywords,
                surfaced_by=["keyword"] if matching_keywords else [],
                discovered_at=discovered_at,
            )
            articles.append(article)

    logger.info(f"Fetched {len(articles)} papers matching criteria from {len(categories)} categories")
    return articles
