"""
Data models for the content screening system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class SourceType(Enum):
    ARXIV = "arxiv"
    BLOG = "blog"
    NEWSLETTER = "newsletter"
    RSS = "rss"
    OPENALEX = "openalex"


@dataclass
class Article:
    """Unified article representation for all content sources."""
    external_id: str
    source_type: SourceType
    title: str
    url: str
    id: Optional[int] = None
    abstract: Optional[str] = None
    # Normalized DOI (lowercase, bare identifier — no https://doi.org/ prefix).
    # Primary cross-source dedup key; populated by OpenAlex, derivable for others.
    doi: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    keywords_matched: List[str] = field(default_factory=list)
    # Which discovery signal(s) surfaced this paper: 'keyword' | 'topic' |
    # 'author' | 'citation' | 'institution'. A paper can match several.
    surfaced_by: List[str] = field(default_factory=list)
    discovered_at: int = 0
    llm_interest_score: Optional[float] = None
    llm_reasoning: Optional[str] = None
    llm_tags: List[str] = field(default_factory=list)
    # PV-era triage routing hint from the screening LLM: 'file' | 'skim' | 'deep'.
    # Kept for history; rubric scoring will stop writing it.
    suggested_depth: Optional[str] = None
    embedding: Optional[bytes] = None
    metadata: dict = field(default_factory=dict)
    # Interest profile this article was screened under (e.g. 'pv', 'fincrime').
    profile: Optional[str] = None
    # OpenRouter model that screened it, so model evaluations can tell them apart.
    screening_model: Optional[str] = None
    # Raw per-statement rubric answers, keyed by statement id. None for rows
    # scored before rubric scoring existed (the PV era).
    rubric_answers: Optional[dict] = None
