"""
ArXiv RSS feed fetching and processing.
"""

import re
import time
from datetime import date
from typing import Iterable, List, Optional

import feedparser  # type: ignore
import requests
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


# --- History (the arXiv API), for the seed backfill ---------------------------

ARXIV_API_URL = "https://export.arxiv.org/api/query"
API_PAGE_SIZE = 200
API_DELAY_SECONDS = 3.0  # arXiv asks for one request every three seconds
# arXiv's API has bad patches of 500s and error entries lasting minutes, so
# back off for up to ~8 minutes in all before giving up on a page.
API_RETRIES = 8
API_MAX_BACKOFF_SECONDS = 120.0


def _backoff(attempt: int) -> float:
    """Seconds to wait before attempt ``attempt`` (0-based)."""
    if attempt == 0:
        return API_DELAY_SECONDS
    return min(API_MAX_BACKOFF_SECONDS, 5.0 * 2 ** attempt)


def keyword_query(keywords: Iterable[str]) -> str:
    """An arXiv API query approximating the substring keyword net.

    Each keyword is a prefix match on its last word (``launder`` ->
    ``launder*``), with multi-word keywords requiring every word, over all
    fields. It is a superset; the exact substring filter is applied to the
    results.
    """
    clauses = {}
    for keyword in sorted(set(keywords)):
        words = re.findall(r"[a-z0-9]+", keyword.lower())
        if not words:
            continue
        terms = [f"all:{w}" for w in words[:-1]] + [f"all:{words[-1]}*"]
        clause = terms[0] if len(terms) == 1 else "(" + " AND ".join(terms) + ")"
        clauses[clause] = None
    return "(" + " OR ".join(clauses) + ")"


def _api_page(query: str, start: int, session: requests.Session) -> dict:
    """One page of API results; retries arXiv's intermittent error entries."""
    params = {
        "search_query": query, "start": start, "max_results": API_PAGE_SIZE,
        "sortBy": "submittedDate", "sortOrder": "ascending",
    }
    for attempt in range(API_RETRIES):
        time.sleep(_backoff(attempt))
        try:
            response = session.get(ARXIV_API_URL, params=params, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"arXiv API request failed (attempt {attempt + 1}): {e}")
            continue
        feed = feedparser.parse(response.text)
        entries = feed.get("entries", [])
        if len(entries) == 1 and entries[0].get("title") == "Error":
            logger.warning(f"arXiv API returned an error entry (attempt {attempt + 1})")
            continue
        return feed
    raise RuntimeError(f"arXiv API kept failing for start={start}")


def fetch_arxiv_history(
    start: date,
    end: date,
    profile: Optional[Profile] = None,
    session: Optional[requests.Session] = None,
) -> List[Article]:
    """Papers submitted in ``[start, end)`` that the daily scan would have caught.

    Queries the arXiv API (the RSS feeds only carry recent papers), then applies
    the daily scan's filters: a profile keyword in the title or abstract, and a
    profile category among the paper's categories (cross-lists included, as in
    the RSS feeds).
    """
    profile = profile or get_active_profile()
    session = session or requests.Session()
    last = date.fromordinal(end.toordinal() - 1)
    query = (
        f"{keyword_query(profile.keywords)} AND submittedDate:"
        f"[{start:%Y%m%d}0000 TO {last:%Y%m%d}2359]"
    )

    articles, offset, total = [], 0, None
    discovered_at = int(time.time())
    while total is None or offset < total:
        feed = _api_page(query, offset, session)
        total = int(feed.get("feed", {}).get("opensearch_totalresults", 0))
        entries = feed.get("entries", [])
        if not entries:
            break
        offset += len(entries)
        for entry in entries:
            paper_id = _extract_paper_id(entry.get("id", ""))
            categories = [t.get("term") for t in entry.get("tags", []) if t.get("term")]
            if not paper_id or not set(categories) & set(profile.arxiv_categories):
                continue
            title = " ".join(entry.get("title", "").split())
            abstract = " ".join(entry.get("summary", "").split())
            matching = _find_matching_keywords(f"{title} {abstract}", profile.keywords)
            if not matching:
                continue
            articles.append(Article(
                external_id=paper_id,
                source_type=SourceType.ARXIV,
                title=title,
                abstract=abstract,
                doi=f"10.48550/arxiv.{re.sub(r'v[0-9]+$', '', paper_id).lower()}",
                url=make_arxiv_url(paper_id),
                authors=_extract_authors(entry),
                categories=categories,
                keywords_matched=matching,
                surfaced_by=["keyword"],
                discovered_at=discovered_at,
            ))

    logger.info(
        f"arXiv history {start}..{last}: {total} API hits, {len(articles)} pass the filters"
    )
    return articles
