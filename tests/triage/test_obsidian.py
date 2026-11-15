"""Tests for the Obsidian stub writer and decision routing (build step 6)."""

import time
from datetime import datetime, timezone

import pytest
import yaml

from content_screening.orm_models import ArticleORM
from triage import obsidian, routing
from triage.config import Settings


def make_paper(**overrides) -> ArticleORM:
    defaults = dict(
        id=1,
        external_id="2401.00001",
        source_type="arxiv",
        title="A Great Paper, About Things!",
        url="https://arxiv.org/abs/2401.00001",
        abstract="An abstract.",
        authors=["Ada Lovelace", "Alan Turing"],
        categories=["cs.LG"],
        keywords_matched=[],
        discovered_at=int(time.time()),
        llm_interest_score=0.6,
        llm_reasoning="Directly relevant to signal detection.",
        llm_tags=["signal-detection"],
        suggested_depth="deep",
        status="kept",
        decided_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc).isoformat(),
        zotero_key=None,
        zotero_error=None,
        obsidian_path=None,
        obsidian_error=None,
        routing_attempts=0,
        next_retry_at=None,
    )
    defaults.update(overrides)
    return ArticleORM(**defaults)


def parse_frontmatter(text: str) -> dict:
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def test_slugify_basic():
    assert obsidian.slugify("Hello, World! A Test") == "hello-world-a-test"


def test_slugify_truncates_to_60_no_trailing_hyphen():
    slug = obsidian.slugify("word " * 40)
    assert len(slug) <= 60
    assert not slug.endswith("-")


def test_write_stub_path_and_frontmatter(tmp_path):
    rel = obsidian.write_stub(tmp_path, make_paper())
    assert rel == "literature/inbox/unread/2026-05-31-a-great-paper-about-things.md"

    content = (tmp_path / rel).read_text()
    fm = parse_frontmatter(content)
    assert fm["title"] == "A Great Paper, About Things!"
    assert fm["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert fm["status"] == "unread"  # 'kept' -> unread
    assert fm["tags"] == ["paper", "triage/kept"]
    assert fm["zotero"] == ""
    assert "Why this surfaced:" in content
    assert "signal detection" in content


def test_stub_written_to_unread_subfolder(tmp_path):
    """Stubs always land in .../unread/, never directly in the inbox root."""
    rel = obsidian.write_stub(tmp_path, make_paper())
    assert "/unread/" in rel


def test_collision_gets_suffix(tmp_path):
    p = make_paper()
    first = obsidian.write_stub(tmp_path, p)
    second = obsidian.write_stub(tmp_path, p)
    assert first.endswith("-about-things.md")
    assert second.endswith("-about-things-2.md")


def test_route_decision_writes_and_is_idempotent(tmp_path):
    settings = Settings(obsidian_vault=str(tmp_path))
    paper = make_paper()

    routing.route_decision(paper, settings)
    assert paper.obsidian_path is not None
    assert paper.obsidian_error is None
    first_path = paper.obsidian_path
    assert (tmp_path / first_path).exists()

    # Second call must not rewrite or create a duplicate.
    routing.route_decision(paper, settings)
    assert paper.obsidian_path == first_path
    unread = tmp_path / "literature" / "inbox" / "unread"
    assert len(list(unread.glob("*.md"))) == 1


def test_dismissed_has_no_side_effects(tmp_path):
    settings = Settings(obsidian_vault=str(tmp_path))
    paper = make_paper(status="dismissed")
    routing.route_decision(paper, settings)
    assert paper.obsidian_path is None
    assert not (tmp_path / "literature").exists()


def test_unconfigured_vault_is_a_noop():
    settings = Settings(obsidian_vault="")
    paper = make_paper()
    routing.route_decision(paper, settings)
    assert paper.obsidian_path is None
    assert paper.obsidian_error is None


# --- Richer stubs (REWORK_PLAN 1.6b) -------------------------------------------


def _fincrime_paper(**overrides) -> ArticleORM:
    return make_paper(**{
        "id": 42,
        "source_type": "openalex",
        "abstract": "  We detect money mules.  ",
        "metadata_": {"venue": "Decision Support Systems", "publication_date": "2026-10-02"},
        "profile": "fincrime",
        "llm_interest_score": 12.5,
        "llm_reasoning": "A mule-detection paper.",
        "rubric_answers": {
            "fincrime": {"answer": "strongly_agree", "justification": "Mules."},
            "genai": {"answer": "disagree", "justification": "A GNN."},
            "survey": {"answer": "agree", "justification": ""},
            "broken": "not a dict",
        },
        **overrides,
    })


def test_stub_frontmatter_for_finding_the_paper_again():
    fm = parse_frontmatter(obsidian.build_stub_markdown(_fincrime_paper()))
    assert fm["triage_id"] == 42
    assert fm["venue"] == "Decision Support Systems"
    assert fm["published"] == "2026-10-02"
    assert fm["profile"] == "fincrime"
    assert fm["score"] == 12.5
    # Agreed statements become tags, whatever their weight's sign.
    assert fm["tags"] == ["paper", "triage/kept", "rubric/fincrime", "rubric/survey"]
    assert list(fm)[:2] == ["title", "triage_id"]


def test_stub_body_has_abstract_and_rubric_before_notes():
    text = obsidian.build_stub_markdown(_fincrime_paper())
    assert "## Abstract\n\nWe detect money mules.\n\n" in text
    assert "Score 12.5 (fincrime profile)." in text
    assert "- `fincrime`: strongly agree. Mules." in text
    assert "- `genai`: disagree. A GNN." in text
    assert "- `survey`: agree\n" in text
    assert "broken" not in text
    # The annotation pipeline writes under ## Notes, so it stays last.
    assert text.index("## Abstract") < text.index("## Screening") < text.index("## Notes")


def test_pv_era_stub_has_no_rubric_section_but_keeps_its_score():
    paper = make_paper(abstract=None, metadata_=None, profile="pv")
    text = obsidian.build_stub_markdown(paper)
    fm = parse_frontmatter(text)
    assert (fm["venue"], fm["published"], fm["score"]) == (None, None, 0.6)
    assert fm["tags"] == ["paper", "triage/kept"]
    assert "## Abstract" not in text
    assert "Score 0.6 (pv profile)." in text
    assert "- `" not in text


@pytest.mark.parametrize("metadata,expected", [
    ({"publication_date": "2026-10-02"}, "2026-10-02"),
    ({"published": "Fri, 13 Nov 2026 17:07:39 -0800"}, "2026-11-13"),
    ({"published": "2026-11-15"}, "2026-11-15"),
    ({"published": "sometime"}, None),
    ({}, None),
])
def test_published_date(metadata, expected):
    assert obsidian.published_date(metadata) == expected
