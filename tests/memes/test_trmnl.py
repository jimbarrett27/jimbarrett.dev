"""Unit tests for the meme panel's merge variables (no network)."""

from memes.trmnl import MAX_HEADLINE_CHARS, _headline


def test_headline_falls_back_when_the_agent_named_no_story():
    assert _headline(None) == "Today's front page"
    assert _headline({}) == "Today's front page"


def test_short_headlines_pass_through():
    assert _headline({"title": "Rust 2.0 released"}) == "Rust 2.0 released"


def test_long_headlines_are_truncated_with_an_ellipsis():
    result = _headline({"title": "word " * 60})
    assert len(result) <= MAX_HEADLINE_CHARS
    assert result.endswith("…")
