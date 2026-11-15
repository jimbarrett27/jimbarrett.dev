"""Tests for the OpenAlex discovery source (no network — `_get` is mocked)."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from content_screening.models import Article, SourceType
from content_screening.openalex import (
    DiscoveryConfig,
    _is_future_date,
    _low_quality_journal,
    _short_id,
    _work_to_article,
    fetch_openalex_articles,
    reconstruct_abstract,
)


# --- abstract reconstruction ------------------------------------------------


class TestReconstructAbstract:
    def test_round_trips_inverted_index(self):
        inv = {"Hello": [0], "world": [1], "again": [2, 4], "hello": [3]}
        assert reconstruct_abstract(inv) == "Hello world again hello again"

    def test_none_and_empty(self):
        assert reconstruct_abstract(None) is None
        assert reconstruct_abstract({}) is None

    def test_orders_by_position(self):
        inv = {"second": [1], "first": [0], "third": [2]}
        assert reconstruct_abstract(inv) == "first second third"


# --- small helpers ----------------------------------------------------------


class TestHelpers:
    def test_short_id(self):
        assert _short_id("https://openalex.org/W123") == "W123"
        assert _short_id("https://openalex.org/W123/") == "W123"
        assert _short_id(None) is None

    def test_future_date_guard(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        past = (date.today() - timedelta(days=1)).isoformat()
        assert _is_future_date(future) is True
        assert _is_future_date(past) is False
        assert _is_future_date(None) is False
        assert _is_future_date("not-a-date") is False


# --- work -> Article mapping ------------------------------------------------


def _sample_work(**overrides) -> dict:
    work = {
        "id": "https://openalex.org/W42",
        "doi": "https://doi.org/10.1234/ABC.def",
        "title": "A study of <em>adverse</em> drug reactions",
        "publication_date": (date.today() - timedelta(days=2)).isoformat(),
        "abstract_inverted_index": {"Signal": [0], "detection": [1]},
        "authorships": [
            {
                "author_position": "first",
                "author": {
                    "id": "https://openalex.org/A5",
                    "display_name": "Marie Lindquist",
                    "orcid": "https://orcid.org/0000-0001-0001-0001",
                },
                "institutions": [
                    {"id": "https://openalex.org/I111684115", "display_name": "Uppsala Monitoring Centre"}
                ],
            },
            {
                "author_position": "last",
                "author": {"id": "https://openalex.org/A6", "display_name": "I. Ralph Edwards"},
                "institutions": [],
            },
        ],
        "primary_location": {
            "landing_page_url": "https://example.org/article/42",
            "source": {"display_name": "Drug Safety"},
        },
        "topics": [{"id": "https://openalex.org/T11943", "display_name": "Pharmacovigilance"}],
    }
    work.update(overrides)
    return work


class TestWorkToArticle:
    def test_maps_core_fields(self):
        art = _work_to_article(_sample_work(), ["topic"], {"adverse", "drug"})
        assert art is not None
        assert art.external_id == "W42"
        assert art.source_type == SourceType.OPENALEX
        # DOI normalized: lowercase, no https://doi.org/ prefix.
        assert art.doi == "10.1234/abc.def"
        assert art.abstract == "Signal detection"
        assert art.authors == ["Marie Lindquist", "I. Ralph Edwards"]
        assert art.surfaced_by == ["topic"]
        assert art.categories == ["Pharmacovigilance"]
        # Keyword net still annotates (title contains "adverse").
        assert "adverse" in art.keywords_matched
        assert art.url == "https://example.org/article/42"

    def test_metadata_carries_affiliations_and_positions(self):
        art = _work_to_article(_sample_work(), ["institution"])
        rich = art.metadata["authorships"]
        assert rich[0]["position"] == "first"
        assert rich[0]["author_id"] == "A5"
        assert rich[0]["institutions"] == ["Uppsala Monitoring Centre"]
        assert art.metadata["venue"] == "Drug Safety"
        assert art.metadata["topic_ids"] == ["T11943"]

    def test_future_date_dropped(self):
        future = (date.today() + timedelta(days=10)).isoformat()
        assert _work_to_article(_sample_work(publication_date=future), ["topic"]) is None

    def test_missing_title_dropped(self):
        assert _work_to_article(_sample_work(title=""), ["topic"]) is None

    def test_url_falls_back_to_doi_then_id(self):
        art = _work_to_article(_sample_work(primary_location={}), ["topic"])
        assert art.url == "https://doi.org/10.1234/abc.def"
        art2 = _work_to_article(_sample_work(primary_location={}, doi=None), ["topic"])
        assert art2.url == "https://openalex.org/W42"


# --- fetch orchestration (mock the HTTP seam) -------------------------------


def _page(results):
    return {"results": results, "meta": {"next_cursor": None}}


class TestFetchOpenalexArticles:
    def test_topic_filter_and_mapping(self):
        cfg = DiscoveryConfig(topics=[{"id": "T11943", "name": "PV"}])

        captured = {}

        def fake_get(path, params, mailto):
            captured["path"] = path
            captured["filter"] = params["filter"]
            return _page([_sample_work()])

        with patch("content_screening.openalex._get", side_effect=fake_get):
            articles = fetch_openalex_articles(cfg)

        assert captured["path"] == "works"
        assert "topics.id:T11943" in captured["filter"]
        assert "from_publication_date:" in captured["filter"]
        assert len(articles) == 1
        assert articles[0].surfaced_by == ["topic"]

    def test_merges_surfaced_by_across_signals(self):
        # Same work id returned by both the topic and author signals.
        cfg = DiscoveryConfig(
            topics=[{"id": "T11943", "name": "PV"}],
            monitored_authors=["A5"],
        )

        def fake_get(path, params, mailto):
            return _page([_sample_work()])

        with patch("content_screening.openalex._get", side_effect=fake_get):
            articles = fetch_openalex_articles(cfg)

        assert len(articles) == 1
        assert set(articles[0].surfaced_by) == {"topic", "author"}

    def test_author_watchlist_splits_ids_and_orcids(self):
        cfg = DiscoveryConfig(
            monitored_authors=["A5", "0000-0001-0001-0001"],
        )
        filters = []

        def fake_get(path, params, mailto):
            filters.append(params["filter"])
            return _page([])

        with patch("content_screening.openalex._get", side_effect=fake_get):
            fetch_openalex_articles(cfg)

        assert any("authorships.author.id:A5" in f for f in filters)
        assert any("authorships.author.orcid:0000-0001-0001-0001" in f for f in filters)

    def test_institution_resolves_first_last_then_cites(self):
        cfg = DiscoveryConfig(
            institutions=[
                {"id": "I111684115", "name": "UMC", "author_positions": ["first", "last"]}
            ]
        )
        seed_work = {
            "id": "https://openalex.org/W100",
            "authorships": [
                {
                    "author_position": "first",
                    "institutions": [{"id": "https://openalex.org/I111684115"}],
                }
            ],
        }
        middle_only = {
            "id": "https://openalex.org/W200",
            "authorships": [
                {
                    "author_position": "middle",
                    "institutions": [{"id": "https://openalex.org/I111684115"}],
                }
            ],
        }
        calls = []

        def fake_get(path, params, mailto):
            calls.append(params["filter"])
            f = params["filter"]
            if f.startswith("authorships.institutions.id:"):
                return _page([seed_work, middle_only])
            if f.startswith("cites:"):
                return _page([_sample_work()])
            return _page([])

        with patch("content_screening.openalex._get", side_effect=fake_get):
            articles = fetch_openalex_articles(cfg)

        # Only the first-author seed work (W100) becomes a cites: seed, not W200.
        assert any(f == "cites:W100,from_publication_date:" + _today_window() for f in calls)
        assert all("W200" not in f for f in calls if f.startswith("cites:"))
        assert len(articles) == 1
        assert articles[0].surfaced_by == ["institution"]


class TestTopicKeywordGate:
    """Broad (require_keyword) topics need a PV keyword; focused topics don't.
    Author/citation/institution signals are never gated."""

    @staticmethod
    def _topic_work(wid: str, topic_id: str, title: str) -> dict:
        return {
            "id": f"https://openalex.org/{wid}",
            "title": title,
            "publication_date": (date.today() - timedelta(days=1)).isoformat(),
            "topics": [{"id": f"https://openalex.org/{topic_id}", "display_name": topic_id}],
            "authorships": [],
            "primary_location": {},
        }

    def _run(self, works):
        cfg = DiscoveryConfig(
            topics=[
                {"id": "T13702", "name": "ML", "require_keyword": True},  # broad/gated
                {"id": "T11943", "name": "PV"},                            # focused/ungated
            ]
        )

        def fake_get(path, params, mailto):
            if params["filter"].startswith("topics.id:"):
                return _page(works)
            return _page([])

        with patch("content_screening.openalex._get", side_effect=fake_get):
            return {a.external_id for a in fetch_openalex_articles(cfg)}

    def test_broad_topic_without_keyword_dropped(self):
        got = self._run([self._topic_work("W1", "T13702", "Stock price forecasting with neural nets")])
        assert got == set()

    def test_broad_topic_with_keyword_kept(self):
        got = self._run([self._topic_work("W2", "T13702", "Drug interaction prediction")])
        assert got == {"W2"}

    def test_focused_topic_without_keyword_kept(self):
        got = self._run([self._topic_work("W3", "T11943", "Patient simulation training")])
        assert got == {"W3"}

    def test_mixed_batch(self):
        got = self._run([
            self._topic_work("W1", "T13702", "Stock price forecasting"),       # gated out
            self._topic_work("W2", "T13702", "Adverse drug event mining"),     # kept (keyword)
            self._topic_work("W3", "T11943", "Nurse handover study"),          # kept (focused)
        ])
        assert got == {"W2", "W3"}


class TestVenueQualityDrop:
    """Topic-net works in unvetted *journals* are dropped; preprints and the
    high-precision signals are spared."""

    @staticmethod
    def _topic_work_in(wid: str, source: dict | None) -> dict:
        primary = {"source": source} if source is not None else {}
        return {
            "id": f"https://openalex.org/{wid}",
            "title": "Adverse drug reaction signal detection",  # carries a PV keyword
            "publication_date": (date.today() - timedelta(days=1)).isoformat(),
            "topics": [{"id": "https://openalex.org/T11943", "display_name": "PV"}],
            "authorships": [],
            "primary_location": primary,
        }

    def _run(self, works, cfg=None):
        cfg = cfg or DiscoveryConfig(topics=[{"id": "T11943", "name": "PV"}])

        def fake_get(path, params, mailto):
            return _page(works)

        with patch("content_screening.openalex._get", side_effect=fake_get):
            return {a.external_id for a in fetch_openalex_articles(cfg)}

    def test_metadata_carries_venue_quality(self):
        work = self._topic_work_in(
            "W1",
            {"display_name": "Junk J", "type": "journal", "is_core": False, "is_in_doaj": False},
        )
        art = _work_to_article(work, ["topic"])
        assert art.metadata["venue_type"] == "journal"
        assert art.metadata["venue_is_core"] is False
        assert art.metadata["venue_is_in_doaj"] is False

    def test_unvetted_journal_dropped(self):
        got = self._run([self._topic_work_in(
            "W1", {"display_name": "Junk J", "type": "journal", "is_core": False, "is_in_doaj": False}
        )])
        assert got == set()

    def test_core_journal_kept(self):
        got = self._run([self._topic_work_in(
            "W2", {"display_name": "Good J", "type": "journal", "is_core": True, "is_in_doaj": False}
        )])
        assert got == {"W2"}

    def test_doaj_journal_kept(self):
        got = self._run([self._topic_work_in(
            "W3", {"display_name": "OA J", "type": "journal", "is_core": False, "is_in_doaj": True}
        )])
        assert got == {"W3"}

    def test_preprint_repository_kept(self):
        # Repository (preprint) venue, neither core nor DOAJ -> not a journal, kept.
        got = self._run([self._topic_work_in(
            "W4", {"display_name": "bioRxiv", "type": "repository", "is_core": False, "is_in_doaj": False}
        )])
        assert got == {"W4"}

    def test_missing_venue_kept(self):
        got = self._run([self._topic_work_in("W5", None)])
        assert got == {"W5"}

    def test_drop_only_applies_to_topic_signal(self):
        # Same unvetted-journal work surfaced by a monitored author is kept.
        work = self._topic_work_in(
            "W6", {"display_name": "Junk J", "type": "journal", "is_core": False, "is_in_doaj": False}
        )
        work["authorships"] = [
            {"author_position": "first", "author": {"id": "https://openalex.org/A5", "display_name": "A B"}}
        ]
        cfg = DiscoveryConfig(
            topics=[{"id": "T11943", "name": "PV"}],
            monitored_authors=["A5"],
        )
        got = self._run([work], cfg=cfg)
        assert got == {"W6"}

    def test_helper_default_when_no_flags(self):
        # Older payloads may omit the flags entirely -> treated as unvetted.
        art = _work_to_article(
            self._topic_work_in("W7", {"display_name": "Old J", "type": "journal"}), ["topic"]
        )
        assert _low_quality_journal(art) is True

    def test_trusted_publisher_kept_despite_unvetted(self):
        # A new Nature Portfolio journal: not core, not DOAJ, but reputable publisher.
        got = self._run([self._topic_work_in(
            "W8",
            {
                "display_name": "npj Digital Public Health",
                "type": "journal",
                "is_core": False,
                "is_in_doaj": False,
                "host_organization_name": "Nature Portfolio",
            },
        )])
        assert got == {"W8"}

    def test_untrusted_publisher_still_dropped(self):
        got = self._run([self._topic_work_in(
            "W9",
            {
                "display_name": "Junk J",
                "type": "journal",
                "is_core": False,
                "is_in_doaj": False,
                "host_organization_name": "Predatory Press Ltd",
            },
        )])
        assert got == set()

    def test_extra_publisher_from_config_kept(self):
        # An allowlist entry supplied via discovery.yaml extends the defaults.
        cfg = DiscoveryConfig(
            topics=[{"id": "T11943", "name": "PV"}],
            trusted_publishers=["My Society Press"],
        )
        got = self._run(
            [self._topic_work_in(
                "W10",
                {
                    "display_name": "Society J",
                    "type": "journal",
                    "is_core": False,
                    "is_in_doaj": False,
                    "host_organization_name": "My Society Press",
                },
            )],
            cfg=cfg,
        )
        assert got == {"W10"}


def _today_window():
    from content_screening.constants import SCAN_LOOKBACK_DAYS

    return (date.today() - timedelta(days=SCAN_LOOKBACK_DAYS)).isoformat()


def test_date_window_filters(monkeypatch):
    """The seed backfill's [from_date, to_date] window reaches every signal's filter."""
    from datetime import date

    from content_screening import openalex
    from content_screening.profile import DiscoveryConfig

    filters = []

    def fake_paginate(filter_str, mailto, select=openalex.WORK_SELECT):
        filters.append(filter_str)
        return iter(())

    monkeypatch.setattr(openalex, "_paginate_works", fake_paginate)
    cfg = DiscoveryConfig(mailto="x", topics=[{"id": "T1"}], monitored_authors=["A1"],
                          seed_papers=["W1"])
    openalex.fetch_openalex_articles(cfg, keywords=[], from_date=date(2026, 10, 1),
                                     to_date=date(2026, 10, 31))
    assert len(filters) == 3
    for f in filters:
        assert f.endswith("from_publication_date:2026-10-01,to_publication_date:2026-10-31")
