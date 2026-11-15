"""
Constants for the content screening system.
"""

from pathlib import Path
from typing import Iterable, List

MODULE_ROOT = Path(__file__).parent

PROMPTS_DIR = MODULE_ROOT / "prompts"

DB_NAME = "content_screening.db"


def find_matching_keywords(text: str, keywords: Iterable[str]) -> List[str]:
    """Return the keywords that appear (as substrings) in ``text``.

    ``keywords`` comes from the active interest profile and is already lowercase.

    Shared by all discovery sources (arXiv, RSS, OpenAlex) so the broad keyword
    recall net behaves identically everywhere.
    """
    text_lower = text.lower()
    return sorted(kw for kw in keywords if kw in text_lower)


# How often to scan feeds (in seconds)
SCAN_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours

# Feed entries published within this many days are considered for screening.
# Undated entries are kept regardless; deduplication by external_id (in the
# scanner) prevents anything being screened or stored twice, so this window only
# bounds how far back a *first* sighting can be — it is not a "today only" gate.
SCAN_LOOKBACK_DAYS = 7
