"""Tests for the seed backfill (no network, no LLM)."""

import dataclasses
from datetime import date

import pytest
from sqlalchemy import create_engine, select

from content_screening import db_engine, seed_backfill
from content_screening.arxiv_feed import keyword_query
from content_screening.models import Article, SourceType
from content_screening.orm_models import ArticleORM, Base
from content_screening.profile import load_profile
from content_screening.screener import ScreeningResult

FINCRIME = dataclasses.replace(load_profile("fincrime"), threshold=50.0)


@pytest.fixture
def temp_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db_engine.set_engine(engine)
    yield engine
    db_engine.reset_engine()


def _article(i: int) -> Article:
    return Article(
        external_id=f"W{i}", source_type=SourceType.OPENALEX,
        title=f"Paper number {i}", abstract="About fraud.", url=f"https://x/{i}",
    )


def test_month_windows_newest_first():
    windows = list(seed_backfill.month_windows(date(2026, 11, 15), 3))
    assert windows == [
        (date(2026, 11, 1), date(2026, 11, 16)),
        (date(2026, 10, 1), date(2026, 11, 1)),
        (date(2026, 9, 1), date(2026, 10, 1)),
    ]


def test_month_windows_across_a_year():
    assert list(seed_backfill.month_windows(date(2026, 1, 31), 2))[1] == (
        date(2025, 12, 1), date(2026, 1, 1),
    )


def test_keyword_query_mirrors_the_substring_net():
    q = keyword_query({"launder", "suspicious activit", "financial crime", "financial-crime"})
    assert q == (
        "((all:financial AND all:crime*) OR all:launder* OR "
        "(all:suspicious AND all:activit*))"
    )


class TestScreen:
    def _fakes(self, monkeypatch, per_window: int):
        counter = iter(range(10_000))
        windows = []

        def fake_fetch(profile, start, end):
            windows.append(start)
            return [_article(next(counter)) for _ in range(per_window)]

        screened = []

        def fake_screen(article, profile):
            screened.append(profile.threshold)
            return ScreeningResult(status="auto_rejected", score=1.0, reasoning="r",
                                   rubric_answers={})

        from content_screening import scanner
        monkeypatch.setattr(seed_backfill, "fetch_window", fake_fetch)
        monkeypatch.setattr(scanner, "screen_article", fake_screen)
        monkeypatch.setattr(scanner, "compute_article_embedding", lambda _a: None)
        return windows, screened

    def test_stops_at_target_and_forces_threshold_off(self, temp_db, monkeypatch):
        windows, screened = self._fakes(monkeypatch, per_window=40)
        seed_backfill.screen(FINCRIME, months=12, target=100, max_papers=1500, dry_run=False)
        assert len(windows) == 3
        assert len(screened) == 120
        assert set(screened) == {None}
        with db_engine.get_session() as session:
            statuses = set(session.scalars(select(ArticleORM.status)))
        assert statuses == {"auto_rejected"}

    def test_hard_cap_on_llm_calls(self, temp_db, monkeypatch):
        _, screened = self._fakes(monkeypatch, per_window=40)
        seed_backfill.screen(FINCRIME, months=12, target=1000, max_papers=50, dry_run=False)
        assert len(screened) == 50

    def test_dry_run_screens_nothing(self, temp_db, monkeypatch):
        windows, screened = self._fakes(monkeypatch, per_window=40)
        seed_backfill.screen(FINCRIME, months=2, target=1000, max_papers=1500, dry_run=True)
        assert (len(windows), screened) == (2, [])

    def test_already_stored_papers_are_skipped(self, temp_db, monkeypatch):
        _, screened = self._fakes(monkeypatch, per_window=0)
        monkeypatch.setattr(seed_backfill, "fetch_window",
                            lambda p, s, e: [_article(1), _article(1), _article(2)])
        seed_backfill.screen(FINCRIME, months=2, target=1000, max_papers=1500, dry_run=False)
        assert len(screened) == 2  # W1 once, W2 once; the second month finds both stored


def _row(i, answers, surfaced_by=(), status="auto_rejected", profile="fincrime"):
    return ArticleORM(
        external_id=f"W{i}", source_type="openalex", title=f"Paper {i}",
        url=f"https://x/{i}", discovered_at=1000 + i, status=status, profile=profile,
        rubric_answers=answers, surfaced_by=list(surfaced_by), llm_interest_score=-99.0,
        routing_attempts=0,
    )


def _answers(fincrime, transfer):
    return {"fincrime": {"answer": fincrime}, "transfer": {"answer": transfer}}


class TestPromote:
    def _seed(self):
        with db_engine.get_session() as session:
            session.add(_row(1, _answers("agree", "agree")))                    # 3+2 = 5
            session.add(_row(2, _answers("strongly_agree", "agree")))           # 6+2 = 8
            session.add(_row(3, _answers("agree", "neutral"), ["citation"]))    # 3+0+2 = 5
            session.add(_row(4, _answers("strongly_disagree", "strongly_agree"), ["author"]))
            session.add(_row(5, _answers("agree", "agree"), profile="pv"))
            session.add(_row(6, None))

    def test_rescoring_and_dry_run(self, temp_db):
        self._seed()
        threshold = seed_backfill.promote(FINCRIME, top=2, apply=False)
        assert threshold == 5.0
        with db_engine.get_session() as session:
            rows = {r.external_id: (r.status, r.llm_interest_score)
                    for r in session.scalars(select(ArticleORM))}
        assert rows["W2"] == ("auto_rejected", -99.0)  # nothing written

    def test_apply_promotes_the_best_that_pass_required(self, temp_db):
        self._seed()
        assert seed_backfill.promote(FINCRIME, top=2, apply=True) == 5.0
        with db_engine.get_session() as session:
            rows = {r.external_id: (r.status, r.llm_interest_score)
                    for r in session.scalars(select(ArticleORM))}
        # Ties on score go to the newer paper (W3 over W1).
        assert rows["W2"] == ("pending", 8.0)
        assert rows["W3"] == ("pending", 5.0)
        assert rows["W1"] == ("auto_rejected", 5.0)
        # Failed the required statement: rescored but never promoted.
        assert rows["W4"] == ("auto_rejected", -6.0 + 4.0 + 2.0)
        assert rows["W5"] == ("auto_rejected", -99.0)  # other profile untouched
        assert rows["W6"] == ("auto_rejected", -99.0)  # no answers: untouched

    def test_promotes_once_only(self, temp_db):
        self._seed()
        seed_backfill.promote(FINCRIME, top=1, apply=True)
        with pytest.raises(SystemExit):
            seed_backfill.promote(FINCRIME, top=1, apply=True)


def test_rescreen_failed_fills_in_missing_answers(temp_db, monkeypatch):
    with db_engine.get_session() as session:
        session.add(_row(1, None))
        session.add(_row(2, None))
        session.add(_row(3, _answers("agree", "agree")))

    calls = []

    def fake_screen(article, profile):
        calls.append((article.external_id, profile.threshold))
        if article.external_id == "W2":  # still failing
            return ScreeningResult(status="auto_rejected", score=None, reasoning="x")
        return ScreeningResult(status="auto_rejected", score=4.0, reasoning="ok",
                               tags=["t"], rubric_answers=_answers("agree", "neutral"))

    monkeypatch.setattr(seed_backfill, "screen_article", fake_screen)
    seed_backfill.rescreen_failed(FINCRIME)

    assert sorted(calls) == [("W1", None), ("W2", None)]
    with db_engine.get_session() as session:
        rows = {r.external_id: (r.llm_interest_score, r.rubric_answers is not None, r.status)
                for r in session.scalars(select(ArticleORM))}
    assert rows["W1"] == (4.0, True, "auto_rejected")
    assert rows["W2"] == (-99.0, False, "auto_rejected")
