"""Seed backfill for a new interest profile (REWORK_PLAN 1.5).

Screens history so the triage queue starts with a batch of good papers and the
profile gets a calibrated threshold. Three stages, run by hand::

    uv run python -m content_screening.seed_backfill --dry-run   # free: fetch and count
    uv run python -m content_screening.seed_backfill             # paid: screen
    uv run python -m content_screening.seed_backfill --promote   # top N -> pending

``--rescreen-failed`` retries papers whose rubric screen failed (stored with no
answers, e.g. malformed JSON from the model).

**Screen.** Works backwards from the current month, one calendar month at a
time, until ``--target`` new papers have been screened or ``--months`` months
are covered. Candidates are what the daily scan would have caught then: arXiv
via the API (keyword + category filters) and the OpenAlex author / citation /
topic / institution signals by publication date. RSS feeds carry no history and
are skipped. Everything is screened with the threshold forced off, so it all
lands as ``auto_rejected`` with full rubric answers. ``--max-papers`` is a hard
cap on LLM calls. Already-stored papers are skipped, so an interrupted run can
simply be restarted.

**Promote.** Rescores every stored paper of the profile from its stored rubric
answers with the profile's *current* weights and bonuses (no LLM calls), then
moves the top ``--top`` that pass the required statements to ``pending``. The
score of the last one promoted is the provisional threshold to put in the
profile YAML.
"""

import argparse
import dataclasses
from datetime import date, timedelta
from typing import Iterator, List, Optional, Tuple

from sqlalchemy import select

from content_screening import rubric
from content_screening.arxiv_feed import fetch_arxiv_history
from content_screening.database import add_to_dedup_index, is_duplicate, load_dedup_index
from content_screening.db_engine import get_session
from content_screening.models import Article
from content_screening.openalex import fetch_openalex_articles
from content_screening.orm_models import ArticleORM, article_orm_to_dataclass
from content_screening.profile import Profile, get_active_profile, load_profile
from content_screening.scanner import process_new_articles
from content_screening.screener import screen_article
from util.logging_util import setup_logger

logger = setup_logger(__name__)


def month_windows(today: date, months: int) -> Iterator[Tuple[date, date]]:
    """``[start, end)`` calendar months, newest first; the first ends tomorrow."""
    end = today + timedelta(days=1)
    start = today.replace(day=1)
    for _ in range(months):
        yield start, end
        end = start
        start = (start - timedelta(days=1)).replace(day=1)


def fetch_window(profile: Profile, start: date, end: date) -> List[Article]:
    """Candidates for one window, from every source that has history."""
    articles = fetch_arxiv_history(start, end, profile)
    articles += fetch_openalex_articles(
        profile.openalex, keywords=profile.keywords,
        from_date=start, to_date=end - timedelta(days=1),
    )
    return articles


def _new_only(articles: List[Article], dedup_index) -> List[Article]:
    """Drop papers already stored, and repeats within the batch (DOI/title/id)."""
    doi_set, title_set, id_set = (set(s) for s in dedup_index)
    fresh = []
    for article in articles:
        if is_duplicate(article, doi_set, title_set, id_set):
            continue
        fresh.append(article)
        add_to_dedup_index(article, doi_set, title_set, id_set)
    return fresh


def screen(profile: Profile, months: int, target: int, max_papers: int, dry_run: bool) -> None:
    if not profile.rubric:
        raise SystemExit(f"Profile {profile.name!r} has no rubric to score with.")
    # Nothing is queued while screening; promotion decides the first batch.
    profile = dataclasses.replace(profile, threshold=None)
    dedup_index = load_dedup_index()
    screened = 0
    for start, end in month_windows(date.today(), months):
        articles = _new_only(fetch_window(profile, start, end), dedup_index)
        budget = max_papers - screened
        if not dry_run and len(articles) > budget:
            logger.warning(f"Hard cap: screening {budget} of {len(articles)} in this window")
            articles = articles[:budget]
        if dry_run:
            inserted = len(articles)
        else:
            inserted, _ = process_new_articles(articles, dedup_index, profile)
        screened += inserted
        verb = "would screen" if dry_run else "screened"
        print(f"{start:%Y-%m}: {verb} {inserted} (total {screened})", flush=True)
        if screened >= target or screened >= max_papers:
            break
    print(f"\nDone: {screened} papers {'to screen' if dry_run else 'screened'}.")


def rescreen_failed(profile: Profile) -> None:
    """Screen again the profile's papers that have no rubric answers."""
    profile = dataclasses.replace(profile, threshold=None)
    with get_session() as session:
        rows = list(session.scalars(
            select(ArticleORM).where(
                ArticleORM.profile == profile.name,
                ArticleORM.rubric_answers.is_(None),
            )
        ))
        fixed = 0
        for row in rows:
            result = screen_article(article_orm_to_dataclass(row), profile)
            if result.rubric_answers is None:
                continue
            row.llm_interest_score = result.score
            row.llm_reasoning = result.reasoning
            row.llm_tags = result.tags
            row.rubric_answers = result.rubric_answers
            row.status = result.status
            fixed += 1
    print(f"Rescreened {fixed} of {len(rows)} failed papers.")


def promote(profile: Profile, top: int, apply: bool) -> Optional[float]:
    """Rescore the profile's papers and move the best ``top`` to pending."""
    with get_session() as session:
        rows = list(session.scalars(
            select(ArticleORM).where(
                ArticleORM.profile == profile.name,
                ArticleORM.rubric_answers.is_not(None),
            )
        ))
        if any(r.status == "pending" for r in rows) and apply:
            raise SystemExit("This profile already has pending papers; promote once only.")
        eligible = []
        for row in rows:
            row.llm_interest_score = rubric.score(profile, row.rubric_answers, row.surfaced_by)
            if row.status == "auto_rejected" and not rubric.failed_required(
                profile, row.rubric_answers
            ):
                eligible.append(row)
        eligible.sort(key=lambda r: (r.llm_interest_score, r.discovered_at), reverse=True)
        chosen = eligible[:top]
        for row in chosen:
            print(f"{row.llm_interest_score:+6.1f}  {row.title[:100]}")
        threshold = chosen[-1].llm_interest_score if chosen else None
        print(
            f"\n{len(rows)} papers scored, {len(eligible)} pass the required statements; "
            f"{'promoted' if apply else 'would promote'} {len(chosen)}. "
            f"Provisional threshold: {threshold}"
        )
        if apply:
            for row in chosen:
                row.status = "pending"
        else:
            session.rollback()
            print("Nothing written. Run with --promote --apply to write.")
    return threshold


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", help="profile name (default: the active one)")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--target", type=int, default=1000)
    parser.add_argument("--max-papers", type=int, default=1500,
                        help="hard cap on papers screened (LLM calls)")
    parser.add_argument("--dry-run", action="store_true", help="fetch and count only")
    parser.add_argument("--promote", action="store_true",
                        help="rescore and show the top --top (add --apply to write)")
    parser.add_argument("--rescreen-failed", action="store_true",
                        help="retry papers whose rubric screen failed")
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    profile = load_profile(args.profile) if args.profile else get_active_profile()
    if args.rescreen_failed:
        rescreen_failed(profile)
    elif args.promote:
        promote(profile, args.top, args.apply)
    else:
        screen(profile, args.months, args.target, args.max_papers, args.dry_run)


if __name__ == "__main__":
    main()
