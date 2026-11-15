"""
Rubric scoring (REWORK_PLAN 1.3), computed in code from the LLM's raw answers.

The screening LLM answers each rubric statement on a five-point agreement scale,
or "can't tell". Only the raw answers are trusted to the LLM; the numbers are
here, so weights can be retuned (or fitted to triage decisions) and every stored
paper rescored without another LLM call.

Stored answers (``articles.rubric_answers``) look like::

    {"fincrime": {"answer": "strongly_agree", "justification": "..."}, ...}
"""

from typing import Dict, Iterable, Optional

from content_screening.profile import Profile

STRONGLY_DISAGREE = "strongly_disagree"
CANT_TELL = "cant_tell"

ANSWER_VALUES: Dict[str, int] = {
    STRONGLY_DISAGREE: -2,
    "disagree": -1,
    "neutral": 0,
    "agree": 1,
    "strongly_agree": 2,
    CANT_TELL: 0,
}

# Spellings an LLM plausibly uses for the canonical labels above.
_ALIASES = {
    "neither": "neutral",
    "neither_agree_nor_disagree": "neutral",
    "cannot_tell": CANT_TELL,
    "can_t_tell": CANT_TELL,
    "cant_tell": CANT_TELL,
    "unknown": CANT_TELL,
    "unclear": CANT_TELL,
    "n_a": CANT_TELL,
}

_NUMERIC = {"-2": STRONGLY_DISAGREE, "-1": "disagree", "0": "neutral",
            "1": "agree", "+1": "agree", "2": "strongly_agree", "+2": "strongly_agree"}


def normalise_answer(raw) -> Optional[str]:
    """Map an LLM answer to a canonical label, or None if unrecognised."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in _NUMERIC:
        return _NUMERIC[text]
    key = "".join(c if c.isalnum() else "_" for c in text).strip("_")
    while "__" in key:
        key = key.replace("__", "_")
    key = _ALIASES.get(key, key)
    return key if key in ANSWER_VALUES else None


def parse_answers(profile: Profile, raw_answers: dict) -> dict:
    """Validate the LLM's ``answers`` object against the profile's rubric.

    Returns one entry per rubric statement, in rubric order. A statement the LLM
    skipped, or answered with an unrecognised label, is recorded as "can't tell"
    with the raw answer kept alongside, so nothing is silently invented.
    """
    raw_answers = raw_answers if isinstance(raw_answers, dict) else {}
    parsed = {}
    for statement in profile.rubric:
        item = raw_answers.get(statement.id)
        if isinstance(item, dict):
            raw, justification = item.get("answer"), item.get("justification")
        else:
            raw, justification = item, None
        answer = normalise_answer(raw)
        entry = {
            "answer": answer or CANT_TELL,
            "justification": str(justification or "").strip(),
        }
        if answer is None:
            entry["raw_answer"] = raw
        parsed[statement.id] = entry
    return parsed


def rubric_score(profile: Profile, answers: dict) -> float:
    """Weighted sum of the answers (missing statements count as 0)."""
    total = 0.0
    for statement in profile.rubric:
        label = (answers.get(statement.id) or {}).get("answer", CANT_TELL)
        total += statement.weight * ANSWER_VALUES.get(label, 0)
    return total


def signal_bonus(profile: Profile, surfaced_by: Iterable[str]) -> float:
    """Metadata points for how the paper was found (monitored author, etc.)."""
    return sum(profile.signal_bonuses.get(s, 0.0) for s in set(surfaced_by or ()))


def score(profile: Profile, answers: dict, surfaced_by: Iterable[str] = ()) -> float:
    """The paper's score: rubric weighted sum plus discovery-signal bonuses."""
    return rubric_score(profile, answers) + signal_bonus(profile, surfaced_by)


def failed_required(profile: Profile, answers: dict) -> list:
    """Ids of required statements answered "strongly disagree" ("can't tell" passes)."""
    return [
        s.id for s in profile.rubric
        if s.required
        and (answers.get(s.id) or {}).get("answer") == STRONGLY_DISAGREE
    ]


def intake_status(profile: Profile, answers: dict, paper_score: float) -> str:
    """'pending' if the paper enters the triage queue, else 'auto_rejected'.

    With no threshold set yet (before the seed backfill has calibrated one),
    nothing is queued automatically.
    """
    if failed_required(profile, answers):
        return "auto_rejected"
    if profile.threshold is None or paper_score < profile.threshold:
        return "auto_rejected"
    return "pending"
