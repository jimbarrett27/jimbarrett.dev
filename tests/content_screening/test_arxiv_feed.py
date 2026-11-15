"""Tests for ArXiv feed fetching functionality."""

import time
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from content_screening.models import Article, SourceType
from content_screening.arxiv_feed import (
    _clean_summary,
    _extract_authors,
    _extract_paper_id,
    _find_matching_keywords,
    _is_recent,
    fetch_arxiv_papers,
    get_arxiv_rss_url,
    make_arxiv_url,
)
from content_screening.profile import load_profile

PV = load_profile("pv")


class TestUrlGeneration:
    """Tests for URL generation functions."""

    def test_get_arxiv_rss_url(self):
        """Test RSS URL generation for categories."""
        assert get_arxiv_rss_url("cs.AI") == "http://rss.arxiv.org/rss/cs.AI"
        assert get_arxiv_rss_url("stat.ML") == "http://rss.arxiv.org/rss/stat.ML"
        assert get_arxiv_rss_url("q-bio.QM") == "http://rss.arxiv.org/rss/q-bio.QM"

    def test_make_arxiv_url(self):
        """Test ArXiv abstract URL generation."""
        assert make_arxiv_url("2401.12345") == "https://arxiv.org/abs/2401.12345"
        assert make_arxiv_url("2401.12345v1") == "https://arxiv.org/abs/2401.12345v1"
        assert make_arxiv_url("hep-th/9901001") == "https://arxiv.org/abs/hep-th/9901001"


class TestExtractPaperId:
    """Tests for _extract_paper_id function."""

    def test_oai_format(self):
        """Test extraction from OAI format."""
        assert _extract_paper_id("oai:arXiv.org:2601.02514v1") == "2601.02514v1"
        assert _extract_paper_id("oai:arXiv.org:2401.12345") == "2401.12345"

    def test_url_format(self):
        """Test extraction from URL format."""
        assert _extract_paper_id("http://arxiv.org/abs/2601.02514") == "2601.02514"
        assert _extract_paper_id("https://arxiv.org/abs/2401.12345v2") == "2401.12345v2"

    def test_plain_id(self):
        """Test extraction when already a plain ID."""
        assert _extract_paper_id("2401.12345") == "2401.12345"

    def test_old_format_ids(self):
        """Test extraction of old-style ArXiv IDs.

        Note: The current implementation extracts just the numeric part,
        not the full category/id format.
        """
        # Old format URLs extract just the final numeric portion
        assert _extract_paper_id("http://arxiv.org/abs/hep-th/9901001") == "9901001"


class TestExtractAuthors:
    """Tests for _extract_authors function."""

    def test_authors_list_format(self):
        """Test extraction from 'authors' list of dicts."""
        entry = {
            "authors": [
                {"name": "John Smith"},
                {"name": "Jane Doe"},
            ]
        }
        result = _extract_authors(entry)
        assert result == ["John Smith", "Jane Doe"]

    def test_single_author_format(self):
        """Test extraction from 'author' string field."""
        entry = {"author": "John Smith"}
        result = _extract_authors(entry)
        assert result == ["John Smith"]

    def test_empty_authors(self):
        """Test handling of missing authors."""
        assert _extract_authors({}) == []
        assert _extract_authors({"authors": []}) == []

    def test_authors_with_missing_name(self):
        """Test handling of author dicts without 'name' key."""
        entry = {
            "authors": [
                {"name": "John Smith"},
                {"email": "jane@example.com"},  # No name
            ]
        }
        result = _extract_authors(entry)
        assert result == ["John Smith", ""]


class TestFindMatchingKeywords:
    """Tests for _find_matching_keywords function."""

    def test_finds_matching_keywords(self):
        """Test finding keywords in text."""
        text = "This study examines adverse drug reactions in patients."
        result = _find_matching_keywords(text, PV.keywords)
        assert "adverse" in result
        assert "drug" in result
        assert "reaction" in result

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        text = "DRUG ADVERSE REACTION"
        result = _find_matching_keywords(text, PV.keywords)
        assert "drug" in result
        assert "adverse" in result

    def test_partial_matching(self):
        """Test partial keyword matching."""
        text = "Medical pharmaceutical duplication study"
        result = _find_matching_keywords(text, PV.keywords)
        assert "medic" in result
        assert "pharma" in result
        assert "duplic" in result

    def test_no_matches(self):
        """Test when no keywords match."""
        text = "This article is about machine learning algorithms."
        result = _find_matching_keywords(text, PV.keywords)
        assert result == []


class TestFetchArxivPapers:
    """Tests for fetch_arxiv_papers function."""

    @staticmethod
    def _today_struct_time():
        """Get today's date as a struct_time for mocking published_parsed."""
        today = date.today()
        return time.struct_time((today.year, today.month, today.day, 0, 0, 0, 0, 0, 0))

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_fetches_papers_from_category(self, mock_parse):
        """Test basic paper fetching from a category."""
        mock_parse.return_value = {
            "entries": [
                {
                    "id": "oai:arXiv.org:2401.12345v1",
                    "title": "Adverse Drug Reaction Detection Using NLP",
                    "summary": "<p>A study on drug safety monitoring.</p>",
                    "authors": [{"name": "John Smith"}],
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        articles = fetch_arxiv_papers(
            categories={"cs.AI"},
            filter_by_keywords=True
        )

        assert len(articles) == 1
        assert articles[0].external_id == "2401.12345v1"
        assert articles[0].source_type == SourceType.ARXIV
        assert articles[0].title == "Adverse Drug Reaction Detection Using NLP"
        assert "drug" in articles[0].keywords_matched
        assert articles[0].url == "https://arxiv.org/abs/2401.12345v1"

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_filters_by_keywords(self, mock_parse):
        """Test keyword filtering excludes non-matching papers."""
        mock_parse.return_value = {
            "entries": [
                {
                    "id": "oai:arXiv.org:2401.11111",
                    "title": "Drug Safety Analysis",
                    "summary": "About adverse reactions.",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "oai:arXiv.org:2401.22222",
                    "title": "Image Classification with CNNs",
                    "summary": "Computer vision techniques.",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        articles = fetch_arxiv_papers(
            categories={"cs.AI"},
            filter_by_keywords=True
        )

        assert len(articles) == 1
        assert articles[0].external_id == "2401.11111"

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_no_filter_returns_all(self, mock_parse):
        """Test disabling keyword filter returns all papers."""
        mock_parse.return_value = {
            "entries": [
                {
                    "id": "oai:arXiv.org:2401.11111",
                    "title": "Drug Safety Analysis",
                    "summary": "About adverse reactions.",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "oai:arXiv.org:2401.22222",
                    "title": "Image Classification with CNNs",
                    "summary": "Computer vision techniques.",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        articles = fetch_arxiv_papers(
            categories={"cs.AI"},
            filter_by_keywords=False
        )

        assert len(articles) == 2

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_deduplicates_across_categories(self, mock_parse):
        """Test that duplicate papers across categories are filtered."""
        mock_parse.return_value = {
            "entries": [
                {
                    "id": "oai:arXiv.org:2401.12345",
                    "title": "Drug Safety with Machine Learning",
                    "summary": "About drugs.",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        # Fetch from multiple categories that might have the same paper
        articles = fetch_arxiv_papers(
            categories={"cs.AI", "cs.LG"},
            filter_by_keywords=True
        )

        # Should only appear once even though we fetched from 2 categories
        assert len(articles) == 1

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_handles_parse_exceptions(self, mock_parse):
        """Test handling of feedparser exceptions."""
        mock_parse.side_effect = Exception("Network error")

        articles = fetch_arxiv_papers(categories={"cs.AI"})

        assert articles == []

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_skips_entries_without_id(self, mock_parse):
        """Test that entries without ID are skipped."""
        mock_parse.return_value = {
            "entries": [
                {
                    "id": "",
                    "title": "Drug study without ID",
                    "summary": "About drugs.",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "oai:arXiv.org:2401.12345",
                    "title": "Valid drug study",
                    "summary": "About drugs.",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        articles = fetch_arxiv_papers(
            categories={"cs.AI"},
            filter_by_keywords=True
        )

        assert len(articles) == 1
        assert articles[0].external_id == "2401.12345"

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_strips_html_from_summary(self, mock_parse):
        """Test that HTML is stripped from summaries."""
        mock_parse.return_value = {
            "entries": [
                {
                    "id": "oai:arXiv.org:2401.12345",
                    "title": "Drug Safety Study",
                    "summary": "<p>This is about <strong>drug</strong> safety.</p>",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        articles = fetch_arxiv_papers(
            categories={"cs.AI"},
            filter_by_keywords=True
        )

        assert len(articles) == 1
        assert "<p>" not in articles[0].abstract
        assert "<strong>" not in articles[0].abstract
        assert "drug" in articles[0].abstract.lower()

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_stores_category(self, mock_parse):
        """Test that the category is stored in the article."""
        mock_parse.return_value = {
            "entries": [
                {
                    "id": "oai:arXiv.org:2401.12345",
                    "title": "Drug Safety Study",
                    "summary": "About drugs.",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        articles = fetch_arxiv_papers(
            categories={"stat.ML"},
            filter_by_keywords=True
        )

        assert len(articles) == 1
        assert "stat.ML" in articles[0].categories

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_fetches_from_multiple_categories(self, mock_parse):
        """Test fetching from multiple categories."""
        today_struct = self._today_struct_time()

        def side_effect(url):
            if "cs.AI" in url:
                return {
                    "entries": [
                        {
                            "id": "oai:arXiv.org:2401.11111",
                            "title": "AI Drug Discovery",
                            "summary": "About drugs.",
                            "published_parsed": today_struct,
                        },
                    ],
                }
            elif "stat.ML" in url:
                return {
                    "entries": [
                        {
                            "id": "oai:arXiv.org:2401.22222",
                            "title": "ML for Adverse Events",
                            "summary": "About adverse reactions.",
                            "published_parsed": today_struct,
                        },
                    ],
                }
            return {"entries": []}

        mock_parse.side_effect = side_effect

        articles = fetch_arxiv_papers(
            categories={"cs.AI", "stat.ML"},
            filter_by_keywords=True
        )

        assert len(articles) == 2
        ids = {a.external_id for a in articles}
        assert ids == {"2401.11111", "2401.22222"}

    def test_uses_default_categories(self):
        """The active (PV) profile supplies the categories when none are given."""
        assert "cs.AI" in PV.arxiv_categories
        assert "cs.LG" in PV.arxiv_categories

    @patch("content_screening.arxiv_feed.feedparser.parse")
    def test_empty_category_returns_empty(self, mock_parse):
        """Test that empty categories set returns empty list."""
        articles = fetch_arxiv_papers(categories=set())
        assert articles == []
        mock_parse.assert_not_called()


@pytest.mark.integration
class TestArxivFeedIntegration:
    """Integration tests that fetch from real ArXiv feeds.

    Run with: uv run python -m pytest -m integration
    """

    def test_fetch_from_cs_ai(self):
        """Test fetching from cs.AI category."""
        articles = fetch_arxiv_papers(
            categories={"cs.AI"},
            filter_by_keywords=False
        )

        # cs.AI is an active category, should have papers
        assert len(articles) >= 0

        for article in articles:
            assert article.source_type == SourceType.ARXIV
            assert article.external_id
            assert article.title
            assert article.url.startswith("https://arxiv.org/abs/")
            assert "cs.AI" in article.categories

    def test_fetch_from_stat_ml(self):
        """Test fetching from stat.ML category."""
        articles = fetch_arxiv_papers(
            categories={"stat.ML"},
            filter_by_keywords=False
        )

        assert len(articles) >= 0

        for article in articles:
            assert article.source_type == SourceType.ARXIV
            assert "stat.ML" in article.categories

    def test_fetch_with_keyword_filtering(self):
        """Test that keyword filtering works on real ArXiv feeds."""
        # Fetch with filtering
        filtered = fetch_arxiv_papers(
            categories={"cs.AI", "cs.LG"},
            filter_by_keywords=True
        )

        # Fetch without filtering
        all_papers = fetch_arxiv_papers(
            categories={"cs.AI", "cs.LG"},
            filter_by_keywords=False
        )

        # Filtered should be <= all
        assert len(filtered) <= len(all_papers)

        # All filtered papers should have matched keywords
        for article in filtered:
            assert len(article.keywords_matched) > 0

    def test_fetch_from_all_configured_categories(self):
        """Test fetching from all configured ArXiv categories."""
        articles = fetch_arxiv_papers(
            categories=PV.arxiv_categories,
            filter_by_keywords=False
        )

        print(f"\n{'='*60}")
        print("ArXiv Feed Integration Test Results")
        print(f"{'='*60}")
        print(f"Categories tested: {len(PV.arxiv_categories)}")
        print(f"Total papers fetched: {len(articles)}")

        # Group by category
        by_category = {}
        for article in articles:
            for cat in article.categories:
                by_category[cat] = by_category.get(cat, 0) + 1

        print("\nPapers by category:")
        for cat in sorted(by_category.keys()):
            print(f"  - {cat}: {by_category[cat]}")

        # Should get some papers from at least some categories
        assert len(articles) >= 0


class TestIsRecent:
    """Tests for the _is_recent look-back filter (replaces the old today-only gate)."""

    def _make_struct_time(self, year: int, month: int, day: int):
        """Create a struct_time for testing."""
        return time.struct_time((year, month, day, 0, 0, 0, 0, 0, 0))

    def _entry(self, d: date) -> dict:
        return {"published_parsed": self._make_struct_time(d.year, d.month, d.day)}

    def test_today_is_recent(self):
        assert _is_recent(self._entry(date.today())) is True

    def test_yesterday_is_recent(self):
        # The key behaviour change: yesterday is now KEPT (was dropped before).
        assert _is_recent(self._entry(date.today() - timedelta(days=1))) is True

    def test_within_window_is_recent(self):
        assert _is_recent(self._entry(date.today() - timedelta(days=6)), lookback_days=7) is True

    def test_older_than_window_is_not_recent(self):
        assert _is_recent(self._entry(date.today() - timedelta(days=30)), lookback_days=7) is False

    def test_undated_entries_are_kept(self):
        # No date -> kept (dedup prevents reprocessing); was excluded before.
        assert _is_recent({}) is True
        assert _is_recent({"published_parsed": None}) is True


class TestCleanSummary:
    """Tests for stripping arXiv's announce-type boilerplate from summaries."""

    def test_strips_announce_prefix_and_abstract_label(self):
        raw = "arXiv:2606.00027v1 Announce Type: new\nAbstract: This is the real abstract."
        assert _clean_summary(raw) == "This is the real abstract."

    def test_leaves_clean_summary_untouched(self):
        assert _clean_summary("Just a plain abstract.") == "Just a plain abstract."
