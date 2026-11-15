"""Tests for triage.repository query functions.

Uses an in-memory SQLite DB wired into the shared db_engine, following the same
pattern as tests/triage/test_retry.py.
"""

import time

import pytest
from sqlalchemy import create_engine, select

from content_screening import db_engine
from content_screening.orm_models import ArticleORM, Base


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db_engine.set_engine(engine)
    yield engine
    db_engine.reset_engine()


def _make_orm(
    external_id: str,
    status: str,
    decided_at: str | None = None,
    score: float | None = None,
    discovered_at: int | None = None,
) -> ArticleORM:
    return ArticleORM(
        external_id=external_id,
        source_type="arxiv",
        title=f"Paper {external_id}",
        url=f"https://arxiv.org/abs/{external_id}",
        discovered_at=discovered_at or int(time.time()),
        status=status,
        llm_interest_score=score,
        decided_at=decided_at,
        routing_attempts=0,
    )


class TestGetPendingPapers:
    def test_best_score_first_ties_newest_first_unscored_last(self, memory_db):
        with db_engine.get_session() as session:
            session.add(_make_orm("low", "pending", score=-3.0, discovered_at=300))
            session.add(_make_orm("none", "pending", score=None, discovered_at=400))
            session.add(_make_orm("high-old", "pending", score=12.5, discovered_at=100))
            session.add(_make_orm("high-new", "pending", score=12.5, discovered_at=200))
            session.add(_make_orm("mid", "pending", score=4.0, discovered_at=500))
            session.add(_make_orm("rejected", "auto_rejected", score=20.0))
            session.add(_make_orm("archived", "archived", score=1.0))

        with db_engine.get_session() as session:
            from triage.repository import get_pending_papers
            ids = [r.external_id for r in get_pending_papers(session)]

        assert ids == ["high-new", "high-old", "mid", "low", "none"]


class TestGetDecidedPapers:
    """get_decided_papers returns only human decisions (kept / dismissed)."""

    def test_excludes_pending(self, memory_db):
        with db_engine.get_session() as session:
            session.add(_make_orm("p1", "pending"))

        with db_engine.get_session() as session:
            from triage.repository import get_decided_papers
            result = get_decided_papers(session)
            ids = [r.external_id for r in result]

        assert ids == []

    def test_excludes_auto_rejected(self, memory_db):
        with db_engine.get_session() as session:
            session.add(_make_orm("ar1", "auto_rejected"))

        with db_engine.get_session() as session:
            from triage.repository import get_decided_papers
            result = get_decided_papers(session)
            ids = [r.external_id for r in result]

        assert ids == []

    def test_excludes_archived(self, memory_db):
        """The archived PV queue was never triaged, so it isn't history."""
        with db_engine.get_session() as session:
            session.add(_make_orm("arch1", "archived"))
            session.add(_make_orm("k1", "kept", decided_at="2026-06-10T00:00:00+00:00"))

        with db_engine.get_session() as session:
            from triage.repository import get_decided_papers
            ids = [r.external_id for r in get_decided_papers(session)]

        assert ids == ["k1"]

    def test_includes_kept(self, memory_db):
        with db_engine.get_session() as session:
            session.add(_make_orm("k1", "kept", decided_at="2026-06-01T12:00:00+00:00"))

        with db_engine.get_session() as session:
            from triage.repository import get_decided_papers
            result = get_decided_papers(session)
            ids = [r.external_id for r in result]

        assert ids == ["k1"]

    def test_includes_dismissed(self, memory_db):
        with db_engine.get_session() as session:
            session.add(_make_orm("d1", "dismissed", decided_at="2026-06-01T11:00:00+00:00"))

        with db_engine.get_session() as session:
            from triage.repository import get_decided_papers
            result = get_decided_papers(session)
            ids = [r.external_id for r in result]

        assert ids == ["d1"]

    def test_mixed_statuses_only_human_decisions_returned(self, memory_db):
        """With pending, auto_rejected, kept and dismissed rows in the DB,
        only the human-decided ones (kept/dismissed) are returned."""
        with db_engine.get_session() as session:
            session.add(_make_orm("p1", "pending"))
            session.add(_make_orm("ar1", "auto_rejected"))
            session.add(_make_orm("k1", "kept", decided_at="2026-06-02T10:00:00+00:00"))
            session.add(_make_orm("d1", "dismissed", decided_at="2026-06-01T10:00:00+00:00"))

        with db_engine.get_session() as session:
            from triage.repository import get_decided_papers
            result = get_decided_papers(session)
            returned_ids = {r.external_id for r in result}

        assert returned_ids == {"k1", "d1"}

    def test_legacy_deep_and_filed_are_included(self, memory_db):
        """Legacy 'deep' / 'filed' rows (pre-migration) are human decisions and
        must still appear in history."""
        with db_engine.get_session() as session:
            session.add(_make_orm("old-deep", "deep", decided_at="2026-05-01T10:00:00+00:00"))
            session.add(_make_orm("old-filed", "filed", decided_at="2026-05-01T09:00:00+00:00"))

        with db_engine.get_session() as session:
            from triage.repository import get_decided_papers
            result = get_decided_papers(session)
            returned_ids = {r.external_id for r in result}

        assert "old-deep" in returned_ids
        assert "old-filed" in returned_ids
