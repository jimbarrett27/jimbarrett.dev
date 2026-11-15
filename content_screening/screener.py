"""
LLM-based interest screening for articles.

Two prompts, chosen by the profile:

- **Rubric** (profiles with a ``rubric``): the LLM answers each statement and the
  score is computed in code (``content_screening.rubric``). The raw answers are
  returned for storage. Intake is decided by the scanner from the score.
- **Legacy relevance** (profiles without one, i.e. PV): HIGH/MEDIUM/LOW relevance
  times confidence, as before.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional

from content_screening import rubric
from content_screening.constants import PROMPTS_DIR
from content_screening.models import Article
from content_screening.profile import Profile, get_active_profile
from llm.llm_util import get_llm_response
from util.logging_util import setup_logger

logger = setup_logger(__name__)

SCREEN_ARTICLE_TEMPLATE = PROMPTS_DIR / "screen_article.jinja2"
SCREEN_RUBRIC_TEMPLATE = PROMPTS_DIR / "screen_rubric.jinja2"

# Mapping from categorical relevance/confidence to numeric scores
RELEVANCE_SCORES = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.0}
CONFIDENCE_SCORES = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}


@dataclass
class ScreeningResult:
    """What the screener concluded about one article.

    ``status`` is the intake decision ('pending' or 'auto_rejected'). ``score``
    is None only when rubric screening failed outright; ``rubric_answers`` is
    None for legacy screening and for failures, so failed rubric screens can be
    found and rerun later (``rubric_answers IS NULL`` under a rubric profile).
    """

    status: str
    score: Optional[float]
    reasoning: str
    tags: List[str] = field(default_factory=list)
    rubric_answers: Optional[dict] = None


def _parse_json(response: str) -> dict:
    """Parse the LLM's JSON, tolerating a surrounding markdown code fence."""
    text = response.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:-1])
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError(f"expected a JSON object, got {type(result).__name__}")
    return result


def _tags(value) -> List[str]:
    return [str(t) for t in value] if isinstance(value, list) else []


def screen_article(article: Article, profile: Optional[Profile] = None) -> ScreeningResult:
    """Screen an article with the LLM against an interest profile.

    ``profile`` supplies the interest description, rubric, threshold and model;
    it defaults to the active profile.
    """
    profile = profile or get_active_profile()
    if profile.rubric:
        return _screen_rubric(article, profile)
    return _screen_legacy(article, profile)


def _screen_rubric(article: Article, profile: Profile) -> ScreeningResult:
    response = ""
    try:
        response = get_llm_response(
            str(SCREEN_RUBRIC_TEMPLATE),
            {
                "description": profile.description,
                "statements": [
                    {"id": s.id, "statement": s.statement} for s in profile.rubric
                ],
                "title": article.title,
                "abstract": article.abstract or "",
            },
            model_name=profile.model,
        )
        result = _parse_json(response)
    except Exception as e:
        # No answers, no score: never queued on a guess, but findable for a rerun.
        logger.error(f"Rubric screening failed for '{article.title[:50]}': {e}")
        if response:
            logger.error(f"Response was: {response}")
        return ScreeningResult(
            status="auto_rejected", score=None, reasoning=f"Screening failed: {e}"
        )

    answers = rubric.parse_answers(profile, result.get("answers"))
    paper_score = rubric.score(profile, answers, article.surfaced_by)
    status = rubric.intake_status(profile, answers, paper_score)
    failed = rubric.failed_required(profile, answers)
    reasoning = str(result.get("summary") or "").strip()
    if not reasoning:
        reasoning = "; ".join(
            f"{sid}: {a['justification']}" for sid, a in answers.items()
            if a["justification"]
        )[:500] or "No summary provided"

    logger.info(
        f"Screened '{article.title[:50]}...': score={paper_score:+.1f}, "
        f"status={status}" + (f", failed required {failed}" if failed else "")
    )
    return ScreeningResult(
        status=status,
        score=paper_score,
        reasoning=reasoning,
        tags=_tags(result.get("tags")),
        rubric_answers=answers,
    )


def _screen_legacy(article: Article, profile: Profile) -> ScreeningResult:
    response = ""
    try:
        response = get_llm_response(
            str(SCREEN_ARTICLE_TEMPLATE),
            {
                "description": profile.description,
                "title": article.title,
                "abstract": article.abstract or "",
            },
            model_name=profile.model,
        )
        result = _parse_json(response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Response was: {response}")
        return ScreeningResult(
            status="auto_rejected", score=0.0,
            reasoning=f"Failed to parse LLM response: {e}",
        )
    except Exception as e:
        logger.error(f"Error screening article: {e}")
        # Default to relevant on error to avoid missing papers
        return ScreeningResult(
            status="pending", score=0.5, reasoning=f"Error during screening: {e}"
        )

    relevance = str(result.get("relevance", "LOW")).upper()
    confidence = str(result.get("confidence", "LOW")).upper()
    is_relevant = relevance in ("HIGH", "MEDIUM")
    score = RELEVANCE_SCORES.get(relevance, 0.0) * CONFIDENCE_SCORES.get(confidence, 0.3)

    logger.info(
        f"Screened '{article.title[:50]}...': relevance={relevance}, "
        f"confidence={confidence}, score={score:.2f}"
    )
    return ScreeningResult(
        status="pending" if is_relevant else "auto_rejected",
        score=score if is_relevant else 0.0,
        reasoning=result.get("reasoning", "No reasoning provided"),
        tags=_tags(result.get("tags")),
    )
