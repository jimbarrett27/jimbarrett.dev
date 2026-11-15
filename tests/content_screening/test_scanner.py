"""Tests for scanner.process_new_articles — status assignment at ingest.

Only the status-tagging behaviour is tested here; LLM and embedding calls are
mocked so no network is required.
"""

import pytest
from sqlalchemy import create_engine, select

from content_screening import db_engine
from content_screening.models import Article, SourceType
from content_screening.orm_models import ArticleORM, Base


@pytest.fixture
def temp_db():
    """In-memory SQLite with the full schema, wired into the shared engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db_engine.set_engine(engine)
    yield engine
    db_engine.reset_engine()


def _make_article(external_id: str) -> Article:
    # Each article must have a unique title so the title-based dedup index
    # does not collapse them into a single entry within one batch.
    return Article(
        external_id=external_id,
        source_type=SourceType.ARXIV,
        title=f"A unique paper about {external_id}",
        abstract="An abstract.",
        url=f"https://arxiv.org/abs/{external_id}",
    )


class TestProcessNewArticlesStatus:
    """process_new_articles assigns correct status based on screener output."""

    def _run(self, articles, monkeypatch, *, is_relevant: bool):
        """Run process_new_articles with screener and embedding both mocked.

        Patches via the scanner module's own namespace because scanner.py
        imports the functions with ``from ... import``.
        """
        from content_screening import scanner

        # Patch via the scanner module namespace so the already-bound names are replaced.
        score = 0.8 if is_relevant else 0.0
        monkeypatch.setattr(
            scanner,
            "screen_article",
            lambda _a, _profile=None: (is_relevant, score, "reason", ["tag"], "skim"),
        )
        monkeypatch.setattr(
            scanner,
            "compute_article_embedding",
            lambda _a: None,
        )

        return scanner.process_new_articles(articles)

    def test_rows_are_stamped_with_profile_and_model(self, temp_db, monkeypatch):
        """Every inserted row records the profile and model that screened it."""
        self._run([_make_article("stamp-001")], monkeypatch, is_relevant=False)

        with db_engine.get_session() as session:
            row = session.scalars(
                select(ArticleORM).where(ArticleORM.external_id == "stamp-001")
            ).one()
            stamped = (row.profile, row.screening_model, row.rubric_answers)
        assert stamped == ("pv", "deepseek/deepseek-v4.1-flash", None)

    def test_relevant_article_inserted_as_pending(self, temp_db, monkeypatch):
        """A screener-relevant article lands with status='pending'."""
        article = _make_article("rel-001")
        self._run([article], monkeypatch, is_relevant=True)

        with db_engine.get_session() as session:
            row = session.scalars(
                select(ArticleORM).where(ArticleORM.external_id == "rel-001")
            ).one()
            status = row.status  # read inside session to avoid DetachedInstanceError
        assert status == "pending"

    def test_non_relevant_article_inserted_as_auto_rejected(self, temp_db, monkeypatch):
        """A screener-rejected article lands with status='auto_rejected'."""
        article = _make_article("rej-001")
        self._run([article], monkeypatch, is_relevant=False)

        with db_engine.get_session() as session:
            row = session.scalars(
                select(ArticleORM).where(ArticleORM.external_id == "rej-001")
            ).one()
            status = row.status
        assert status == "auto_rejected"

    def test_mixed_batch_assigns_statuses_correctly(self, temp_db, monkeypatch):
        """Both relevant and non-relevant articles in the same batch get the
        right status."""
        from content_screening import scanner

        relevant_ids = {"rel-A", "rel-B"}
        non_relevant_ids = {"rej-X", "rej-Y"}

        def fake_screen(article, profile=None):
            is_rel = article.external_id in relevant_ids
            return (is_rel, 0.8 if is_rel else 0.0, "r", [], "skim")

        monkeypatch.setattr(scanner, "screen_article", fake_screen)
        monkeypatch.setattr(scanner, "compute_article_embedding", lambda _a: None)

        articles = [
            _make_article(eid)
            for eid in list(relevant_ids) + list(non_relevant_ids)
        ]
        new_inserted, new_relevant = scanner.process_new_articles(articles)

        assert new_inserted == 4
        assert new_relevant == 2

        with db_engine.get_session() as session:
            rows = session.scalars(select(ArticleORM)).all()
            statuses = {r.external_id: r.status for r in rows}

        for eid in relevant_ids:
            assert statuses[eid] == "pending", f"{eid} should be pending"
        for eid in non_relevant_ids:
            assert statuses[eid] == "auto_rejected", f"{eid} should be auto_rejected"
