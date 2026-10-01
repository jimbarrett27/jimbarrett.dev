"""The words of the day for the Swedish TRMNL panel.

Each day gets ``WORDS_PER_DAY`` words drawn from the flashcard deck, glossed by
one LLM call and stored in ``daily_words``. The panel then rotates through them
hour by hour, and every push after the first is a database read: the LLM is
only consulted when the day has no words yet, so a restart or a retried push
never re-rolls what is on the wall.

Selection leans hard. The deck is mostly the seeded word lists, plenty of which
are beginner vocabulary, so a uniform draw would put "en katt" up as often as
"en klippa". Reviewed cards are weighted by their FSRS difficulty; unreviewed
ones get the deck's typical difficulty, so they still surface. A weighted
sample of candidates goes to the LLM, which picks the most interesting few --
difficulty knows which words *this* learner struggles with, but not which
words are dull.
"""

import json
import logging
import random
from datetime import date, datetime, timedelta

from llm.llm_util import get_llm_response
from swedish.database import (
    get_all_cards,
    get_daily_words,
    get_recent_daily_words,
    save_daily_words,
)
from swedish.flash_card import DailyWord, FlashCard
from util.constants import REPO_ROOT
from util.timezone import stockholm_now

logger = logging.getLogger(__name__)

WORDS_PER_DAY = 4
N_CANDIDATES = 16
# Long enough that the wall doesn't repeat itself within a season, short enough
# that a 900-word deck never runs dry (4 a day * 60 days = 240 words).
NO_REPEAT_DAYS = 60
# Roughly the deck's mean FSRS difficulty (which runs 1-10) among reviewed cards.
UNSEEN_DIFFICULTY = 5.0
PROMPT = REPO_ROOT / "swedish/prompts/daily_words.jinja2"


def _weight(card: FlashCard) -> float:
    difficulty = card.difficulty if card.n_times_seen > 0 else UNSEEN_DIFFICULTY
    # Squared so a 9 is ~3x as likely as a 5, rather than not quite twice.
    return max(difficulty, 1.0) ** 2


def pick_candidates(cards: list[FlashCard], exclude: set[str], k: int = N_CANDIDATES,
                    rng: random.Random | None = None) -> list[str]:
    """Weighted sample of ``k`` distinct words, hardest-leaning, excluding ``exclude``.

    Efraimidis-Spirakis: each item draws ``u ** (1 / w)`` and the top ``k`` keys
    win, which is a weighted sample *without* replacement in one pass.
    """
    rng = rng or random.Random()
    pool = [c for c in cards if c.word_to_learn not in exclude]
    if len(pool) < WORDS_PER_DAY:  # deck exhausted by the no-repeat window
        pool = cards
    keyed = sorted(pool, key=lambda c: rng.random() ** (1 / _weight(c)), reverse=True)
    return [c.word_to_learn for c in keyed[:k]]


def _parse(response: str, candidates: list[str]) -> list[DailyWord]:
    """The LLM's picks, keeping only well-formed entries for words it was offered."""
    clean = response.replace("```json", "").replace("```", "").strip()
    entries = json.loads(clean)
    allowed = set(candidates)
    words, seen = [], set()
    for entry in entries:
        word = str(entry.get("word", "")).strip()
        fields = [entry.get(f) for f in ("translation", "example_sv", "example_en")]
        if word not in allowed or word in seen or not all(fields):
            logger.warning("dropping unusable LLM pick: %r", entry)
            continue
        seen.add(word)
        words.append(DailyWord(
            word_to_learn=word,
            word_class=str(entry.get("word_class") or ""),
            translation=str(fields[0]).strip(),
            example_sv=str(fields[1]).strip(),
            example_en=str(fields[2]).strip(),
        ))
    return words[:WORDS_PER_DAY]


def generate(candidates: list[str]) -> list[DailyWord]:
    """Have the LLM choose and gloss the day's words from ``candidates``."""
    response = get_llm_response(str(PROMPT), {"candidates": candidates, "n_words": WORDS_PER_DAY})
    words = _parse(response, candidates)
    if len(words) < WORDS_PER_DAY:
        raise ValueError(f"LLM returned {len(words)} usable words, wanted {WORDS_PER_DAY}")
    return words


def ensure_day(day: date) -> list[DailyWord]:
    """The words for ``day``, generating and storing them if this is the first ask."""
    key = day.isoformat()
    words = get_daily_words(key)
    if words:
        return words

    recent = get_recent_daily_words((day - timedelta(days=NO_REPEAT_DAYS)).isoformat())
    candidates = pick_candidates(get_all_cards(), exclude=recent)
    # One retry on a fresh sample: a malformed answer is usually a one-off, and
    # failing here just leaves yesterday's word up until the next hourly run.
    try:
        words = generate(candidates)
    except Exception:
        logger.exception("daily words generation failed; retrying with new candidates")
        candidates = pick_candidates(get_all_cards(), exclude=recent)
        words = generate(candidates)

    save_daily_words(key, words)
    logger.info("daily words for %s: %s", key, ", ".join(w.word_to_learn for w in words))
    return words


def current_slot(now: datetime, n_words: int = WORDS_PER_DAY) -> int:
    """Which word is up: the hour mod the count, so it is stateless across restarts."""
    return now.hour % n_words


def _font_size(word: str) -> int:
    """Headline size that keeps the word on one line across the 800px panel."""
    for limit, size in ((10, 120), (14, 96), (18, 76), (24, 60)):
        if len(word) <= limit:
            return size
    return 48


def as_merge_variables(word: DailyWord, slot: int, n_words: int, day: date) -> dict:
    """What the Liquid template reads."""
    return {
        "word": word.word_to_learn,
        "word_size": _font_size(word.word_to_learn),
        "word_class": word.word_class,
        "translation": word.translation,
        "example_sv": word.example_sv,
        "example_en": word.example_en,
        "position": f"{slot + 1} / {n_words}",
        "date": day.strftime("%-d %b").upper(),
    }


def current_merge_variables(now: datetime | None = None, slot: int | None = None) -> dict:
    """Ensure today's words exist and return the variables for the one that's up."""
    now = now or stockholm_now()
    words = ensure_day(now.date())
    slot = current_slot(now, len(words)) if slot is None else slot % len(words)
    return as_merge_variables(words[slot], slot, len(words), now.date())
