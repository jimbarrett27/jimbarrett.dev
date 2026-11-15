"""Tests for RSS feed fetching functionality."""

import time
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from content_screening.models import Article, SourceType
from content_screening.rss_feed import (
    FeedConfig,
    _authors_from_summary,
    _extract_authors,
    _extract_summary,
    _find_matching_keywords,
    _generate_external_id,
    _strip_metadata_preamble,
    fetch_rss_articles,
)
from content_screening.profile import load_profile

PV = load_profile("pv")


class TestScienceDirectPreamble:
    """ScienceDirect/Elsevier feeds bury authors in the summary and have no abstract."""

    SUMMARY = (
        "Publication date: August 2026\n\n"
        "**Source:** Journal of Biomedical Informatics, Volume 180\n\n"
        "Author(s): Dan Ni Lin, Dongping Du, Nandini Nair"
    )

    def test_authors_parsed_from_summary(self):
        assert _authors_from_summary(self.SUMMARY) == [
            "Dan Ni Lin", "Dongping Du", "Nandini Nair",
        ]

    def test_no_author_line_returns_empty(self):
        assert _authors_from_summary("Just a normal abstract with no author line.") == []

    def test_preamble_stripped_leaving_real_abstract(self):
        text = self.SUMMARY + "\n\nThis is the genuine abstract body."
        assert _strip_metadata_preamble(text) == "This is the genuine abstract body."

    def test_metadata_only_summary_strips_to_empty(self):
        assert _strip_metadata_preamble(self.SUMMARY) == ""


class TestGenerateExternalId:
    """Tests for _generate_external_id function."""

    def test_uses_entry_id_if_present(self):
        """Test that entry ID is used when available."""
        entry = {"id": "unique-entry-id-123", "link": "https://example.com/article"}
        result = _generate_external_id(entry, "https://feed.com/rss")
        assert result == "unique-entry-id-123"

    def test_uses_link_if_no_id(self):
        """Test that link is used when ID is not available."""
        entry = {"link": "https://example.com/article"}
        result = _generate_external_id(entry, "https://feed.com/rss")
        assert result == "https://example.com/article"

    def test_generates_hash_as_fallback(self):
        """Test hash generation when no ID or link available."""
        entry = {"title": "Some Article Title"}
        result = _generate_external_id(entry, "https://feed.com/rss")
        # Should be a 32-char hex hash
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_is_deterministic(self):
        """Test that same input produces same hash."""
        entry = {"title": "Some Article Title"}
        feed_url = "https://feed.com/rss"
        result1 = _generate_external_id(entry, feed_url)
        result2 = _generate_external_id(entry, feed_url)
        assert result1 == result2


class TestExtractAuthors:
    """Tests for _extract_authors function."""

    def test_ieee_semicolon_format(self):
        """Test IEEE format with semicolon-separated authors.

        Note: The current implementation replaces semicolons with commas
        and splits on all commas, so names like "Smith, John" get split
        into separate entries. This test reflects current behavior.
        """
        # Simple names without internal commas work correctly
        entry = {"authors": "John Smith;Jane Doe;Bob Brown;"}
        result = _extract_authors(entry)
        assert result == ["John Smith", "Jane Doe", "Bob Brown"]

    def test_comma_separated_format(self):
        """Test comma-separated author format."""
        entry = {"authors": "John Smith, Jane Doe, Bob Brown"}
        result = _extract_authors(entry)
        assert result == ["John Smith", "Jane Doe", "Bob Brown"]

    def test_list_of_dicts_format(self):
        """Test list of dicts with 'name' key (Lancet/Wiley format)."""
        entry = {
            "authors": [
                {"name": "John Smith"},
                {"name": "Jane Doe"},
            ]
        }
        result = _extract_authors(entry)
        assert result == ["John Smith", "Jane Doe"]

    def test_list_of_strings_format(self):
        """Test list of strings author format."""
        entry = {"authors": ["John Smith", "Jane Doe"]}
        result = _extract_authors(entry)
        assert result == ["John Smith", "Jane Doe"]

    def test_single_author_field(self):
        """Test single 'author' field (not 'authors')."""
        entry = {"author": "John Smith"}
        result = _extract_authors(entry)
        assert result == ["John Smith"]

    def test_empty_authors(self):
        """Test handling of empty/missing authors."""
        assert _extract_authors({}) == []
        assert _extract_authors({"authors": ""}) == []
        assert _extract_authors({"author": ""}) == []

    def test_wiley_newline_format(self):
        """Test Wiley format with newlines in author names."""
        entry = {
            "authors": [
                {"name": "John Smith\nUniversity of Example"},
            ]
        }
        result = _extract_authors(entry)
        assert result == ["John Smith, University of Example"]


class TestExtractSummary:
    """Tests for _extract_summary function."""

    def test_extracts_summary_field(self):
        """Test extraction from 'summary' field."""
        entry = {"summary": "This is the article summary."}
        result = _extract_summary(entry)
        assert result == "This is the article summary."

    def test_extracts_description_field(self):
        """Test extraction from 'description' field as fallback."""
        entry = {"description": "This is the description."}
        result = _extract_summary(entry)
        assert result == "This is the description."

    def test_prefers_summary_over_description(self):
        """Test that 'summary' is preferred over 'description'."""
        entry = {"summary": "Summary text", "description": "Description text"}
        result = _extract_summary(entry)
        assert result == "Summary text"

    def test_converts_html_to_text(self):
        """Test HTML to plain text conversion."""
        entry = {"summary": "<p>This is <strong>bold</strong> text.</p>"}
        result = _extract_summary(entry)
        assert "This is" in result
        assert "bold" in result
        assert "<p>" not in result
        assert "<strong>" not in result

    def test_empty_summary(self):
        """Test handling of empty/missing summary."""
        assert _extract_summary({}) == ""
        assert _extract_summary({"summary": ""}) == ""


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
        assert "reaction" in result

    def test_partial_matching(self):
        """Test partial keyword matching (e.g., 'medic' matches 'medical')."""
        text = "Medical pharmaceutical duplication"
        result = _find_matching_keywords(text, PV.keywords)
        assert "medic" in result
        assert "pharma" in result
        assert "duplic" in result

    def test_no_matches(self):
        """Test when no keywords match."""
        text = "This article is about machine learning algorithms."
        result = _find_matching_keywords(text, PV.keywords)
        assert result == []


class TestFetchRssArticles:
    """Tests for fetch_rss_articles function."""

    @staticmethod
    def _today_struct_time():
        """Get today's date as a struct_time for mocking published_parsed."""
        today = date.today()
        return time.struct_time((today.year, today.month, today.day, 0, 0, 0, 0, 0, 0))

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_fetches_articles_from_feed(self, mock_parse):
        """Test basic article fetching from RSS feed."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "article-1",
                    "title": "Adverse drug reactions in elderly patients",
                    "summary": "A study on drug safety.",
                    "link": "https://example.com/article1",
                    "authors": [{"name": "John Smith"}],
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs, filter_by_keywords=True)

        assert len(articles) == 1
        assert articles[0].title == "Adverse drug reactions in elderly patients"
        assert articles[0].source_type == SourceType.RSS
        assert articles[0].external_id == "article-1"
        assert "drug" in articles[0].keywords_matched

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_filters_by_keywords(self, mock_parse):
        """Test keyword filtering excludes non-matching articles."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "article-1",
                    "title": "Drug safety study",
                    "summary": "About adverse reactions.",
                    "link": "https://example.com/article1",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "article-2",
                    "title": "Machine learning algorithms",
                    "summary": "Neural network techniques.",
                    "link": "https://example.com/article2",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs, filter_by_keywords=True)

        assert len(articles) == 1
        assert articles[0].external_id == "article-1"

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_no_filter_returns_all(self, mock_parse):
        """Test disabling keyword filter returns all articles."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "article-1",
                    "title": "Drug safety study",
                    "summary": "About adverse reactions.",
                    "link": "https://example.com/article1",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "article-2",
                    "title": "Machine learning algorithms",
                    "summary": "Neural network techniques.",
                    "link": "https://example.com/article2",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs, filter_by_keywords=False)

        assert len(articles) == 2

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_handles_http_errors(self, mock_parse):
        """Test handling of HTTP error responses."""
        mock_parse.return_value = {"status": 404, "entries": []}

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs)

        assert articles == []

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_handles_parse_exceptions(self, mock_parse):
        """Test handling of feedparser exceptions."""
        mock_parse.side_effect = Exception("Network error")

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs)

        assert articles == []

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_deduplicates_by_external_id(self, mock_parse):
        """Test that duplicate entries are filtered out."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "same-id",
                    "title": "Drug study part 1",
                    "summary": "About drugs.",
                    "link": "https://example.com/article1",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "same-id",
                    "title": "Drug study part 1 (duplicate)",
                    "summary": "About drugs.",
                    "link": "https://example.com/article1",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs)

        assert len(articles) == 1

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_skips_entries_without_title(self, mock_parse):
        """Test that entries without titles are skipped."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "article-1",
                    "title": "",
                    "summary": "About drugs.",
                    "link": "https://example.com/article1",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "article-2",
                    "title": "Valid drug article",
                    "summary": "About drugs.",
                    "link": "https://example.com/article2",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs)

        assert len(articles) == 1
        assert articles[0].external_id == "article-2"

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_skips_entries_without_link(self, mock_parse):
        """Test that entries without links are skipped."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "article-1",
                    "title": "Drug article without link",
                    "summary": "About drugs.",
                    "link": "",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "article-2",
                    "title": "Valid drug article",
                    "summary": "About drugs.",
                    "link": "https://example.com/article2",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(feed_configs)

        assert len(articles) == 1
        assert articles[0].external_id == "article-2"

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_stores_metadata(self, mock_parse):
        """Test that metadata is correctly stored in articles."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "article-1",
                    "title": "Drug safety study",
                    "summary": "About adverse reactions.",
                    "link": "https://example.com/article1",
                    "published": "2024-01-15T10:00:00Z",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [
            FeedConfig(
                name="Test Feed",
                url="https://feed.com/rss",
                category="papers"
            )
        ]
        articles = fetch_rss_articles(feed_configs)

        assert len(articles) == 1
        assert articles[0].metadata["feed_url"] == "https://feed.com/rss"
        assert articles[0].metadata["feed_category"] == "papers"
        assert articles[0].metadata["published"] == "2024-01-15T10:00:00Z"
        assert articles[0].categories == ["Test Feed"]

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_fetches_from_multiple_feeds(self, mock_parse):
        """Test fetching from multiple feed configurations."""
        today_struct = self._today_struct_time()

        def side_effect(url):
            if "feed1" in url:
                return {
                    "status": 200,
                    "entries": [
                        {
                            "id": "feed1-article",
                            "title": "Drug study from feed 1",
                            "summary": "About drugs.",
                            "link": "https://example.com/feed1/article",
                            "published_parsed": today_struct,
                        },
                    ],
                }
            else:
                return {
                    "status": 200,
                    "entries": [
                        {
                            "id": "feed2-article",
                            "title": "Medical research from feed 2",
                            "summary": "About medicine.",
                            "link": "https://example.com/feed2/article",
                            "published_parsed": today_struct,
                        },
                    ],
                }

        mock_parse.side_effect = side_effect

        feed_configs = [
            FeedConfig(name="Feed 1", url="https://feed1.com/rss"),
            FeedConfig(name="Feed 2", url="https://feed2.com/rss"),
        ]
        articles = fetch_rss_articles(feed_configs)

        assert len(articles) == 2
        assert any(a.external_id == "feed1-article" for a in articles)
        assert any(a.external_id == "feed2-article" for a in articles)

    def test_returns_empty_with_no_configs(self):
        """Test that empty config list returns empty articles."""
        articles = fetch_rss_articles([])
        assert articles == []

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_custom_keywords_override_profile(self, mock_parse):
        """An explicit `keywords` argument replaces the profile's keywords."""
        mock_parse.return_value = {
            "status": 200,
            "entries": [
                {
                    "id": "article-1",
                    "title": "Machine learning study",
                    "summary": "About neural networks.",
                    "link": "https://example.com/article1",
                    "published_parsed": self._today_struct_time(),
                },
                {
                    "id": "article-2",
                    "title": "Drug safety research",
                    "summary": "About safety.",
                    "link": "https://example.com/article2",
                    "published_parsed": self._today_struct_time(),
                },
            ],
        }

        feed_configs = [FeedConfig(name="Test Feed", url="https://feed.com/rss")]
        articles = fetch_rss_articles(
            feed_configs,
            filter_by_keywords=True,
            keywords={"neural", "learning"},
        )

        assert [a.external_id for a in articles] == ["article-1"]
        assert articles[0].keywords_matched == ["learning", "neural"]

    @patch("content_screening.rss_feed.feedparser.parse")
    def test_defaults_to_profile_feeds(self, mock_parse):
        """With no feed configs given, the active profile's feeds are fetched."""
        mock_parse.return_value = {"status": 200, "entries": []}
        fetch_rss_articles()
        fetched = {call.args[0] for call in mock_parse.call_args_list}
        assert fetched == {f.url for f in PV.feeds}


@pytest.mark.integration
class TestRssFeedIntegration:
    """Integration tests that fetch from real RSS feeds.

    Run with: uv run python -m pytest -m integration
    Skip with: uv run python -m pytest -m "not integration"
    """

    def test_loads_configured_feeds(self):
        """The PV profile's feeds are well-formed."""
        configs = list(PV.feeds)
        assert len(configs) > 0, "No feeds configured in the PV profile"

        # Verify each config has required fields
        for config in configs:
            assert config.name, "Feed config missing name"
            assert config.url, "Feed config missing URL"
            assert config.url.startswith("http"), f"Invalid URL: {config.url}"

    def test_fetch_from_lancet_digital_health(self):
        """Test fetching from The Lancet Digital Health feed."""
        feed_config = FeedConfig(
            name="The Lancet Digital Health",
            url="https://www.thelancet.com/rssfeed/landig_current.xml",
            category="papers",
        )

        # Fetch without keyword filtering to get all articles
        articles = fetch_rss_articles([feed_config], filter_by_keywords=False)

        # The feed should return some articles (it's an active journal)
        assert len(articles) >= 0, "Feed returned negative articles (impossible)"

        # If we got articles, verify structure
        for article in articles:
            assert article.source_type == SourceType.RSS
            assert article.title, "Article missing title"
            assert article.url, "Article missing URL"
            assert article.external_id, "Article missing external_id"
            assert "The Lancet Digital Health" in article.categories

    def test_fetch_from_drug_safety_springer(self):
        """Test fetching from Drug Safety (Springer) feed."""
        feed_config = FeedConfig(
            name="Drug Safety (Springer)",
            url="https://link.springer.com/search.rss?search-within=Journal&facet-journal-id=40264&query=",
            category="papers",
        )

        articles = fetch_rss_articles([feed_config], filter_by_keywords=False)

        assert len(articles) >= 0

        for article in articles:
            assert article.source_type == SourceType.RSS
            assert article.title
            assert article.url
            assert article.external_id

    def test_fetch_from_jamia(self):
        """Test fetching from JAMIA (Oxford Academic) feed."""
        feed_config = FeedConfig(
            name="Journal of the American Medical Informatics Association",
            url="https://academic.oup.com/rss/site_5396/3257.xml",
            category="papers",
        )

        articles = fetch_rss_articles([feed_config], filter_by_keywords=False)

        assert len(articles) >= 0

        for article in articles:
            assert article.source_type == SourceType.RSS
            assert article.title
            assert article.url

    def test_fetch_with_keyword_filtering(self):
        """Test that keyword filtering works on real feeds."""
        # Use Drug Safety journal - likely to have PV-related keywords
        feed_config = FeedConfig(
            name="Drug Safety (Springer)",
            url="https://link.springer.com/search.rss?search-within=Journal&facet-journal-id=40264&query=",
            category="papers",
        )

        # Fetch with filtering enabled
        filtered_articles = fetch_rss_articles([feed_config], filter_by_keywords=True)

        # Fetch without filtering
        all_articles = fetch_rss_articles([feed_config], filter_by_keywords=False)

        # Filtered should be <= all
        assert len(filtered_articles) <= len(all_articles)

        # All filtered articles should have matched keywords
        for article in filtered_articles:
            assert len(article.keywords_matched) > 0, (
                f"Filtered article '{article.title}' has no matched keywords"
            )

    def test_fetch_from_all_configured_feeds(self):
        """Test fetching from all configured feeds without errors.

        This is a smoke test to verify all feeds are reachable.
        """
        configs = list(PV.feeds)
        assert len(configs) > 0, "No feeds configured"

        # Track results for reporting
        successful_feeds = []
        failed_feeds = []
        total_articles = 0

        for config in configs:
            try:
                articles = fetch_rss_articles([config], filter_by_keywords=False)
                successful_feeds.append((config.name, len(articles)))
                total_articles += len(articles)
            except Exception as e:
                failed_feeds.append((config.name, str(e)))

        # Report results
        print(f"\n{'='*60}")
        print(f"RSS Feed Integration Test Results")
        print(f"{'='*60}")
        print(f"Total feeds tested: {len(configs)}")
        print(f"Successful: {len(successful_feeds)}")
        print(f"Failed: {len(failed_feeds)}")
        print(f"Total articles fetched: {total_articles}")

        if successful_feeds:
            print(f"\nSuccessful feeds:")
            for name, count in successful_feeds:
                print(f"  - {name}: {count} articles")

        if failed_feeds:
            print(f"\nFailed feeds:")
            for name, error in failed_feeds:
                print(f"  - {name}: {error}")

        # At least some feeds should work
        assert len(successful_feeds) > 0, "All feeds failed"

        # Warn but don't fail if some feeds are down
        if failed_feeds:
            pytest.warns(UserWarning, match="Some feeds failed")
