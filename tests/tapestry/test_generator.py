"""Unit tests for the panel retry loop (the LLM itself is stubbed out)."""

import json
from pathlib import Path

import pytest

from tapestry import generator
from tapestry.style import style_directive
from tapestry.svg import PANEL_HEIGHT, PANEL_WIDTH

STORIES = [
    {"title": f"Story {i}", "summary": f"Summary {i}", "link": f"https://example.com/{i}"}
    for i in range(generator.STORIES_PER_PANEL)
]

# Enough drawable elements to clear the "truncated or near-empty" check.
VALID_SVG = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{PANEL_WIDTH}" '
    f'height="{PANEL_HEIGHT}" viewBox="0 0 {PANEL_WIDTH} {PANEL_HEIGHT}">'
    '<rect x="0" y="40" width="1600" height="160" fill="#d9c9a3"/>'
    + "".join(
        f'<circle cx="{100 * i}" cy="120" r="20" fill="#8b5a2b"/>' for i in range(10)
    )
    + "</svg>"
)


def replies(monkeypatch, *outcomes):
    """Stub the LLM with one outcome per call; exceptions are raised, str returned.

    Returns the list of ``problem`` values the prompt was rendered with, so a test
    can assert what (if anything) was fed back into each retry.
    """
    seen_problems = []
    remaining = list(outcomes)

    def fake_get_llm_response(template_path, params, model):
        seen_problems.append(params["problem"])
        outcome = remaining.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(generator, "get_llm_response", fake_get_llm_response)
    return seen_problems


def test_api_failure_costs_one_attempt_not_the_whole_run(monkeypatch):
    """The bug that lost 2026-07-22: OpenRouter returned a body that wasn't JSON.

    The call to the model used to sit outside the retry loop's try block, so one
    flaky response aborted all three attempts and the day went un-drawn.
    """
    api_error = json.JSONDecodeError("Expecting value", "\n" * 1386, 7623)
    seen = replies(monkeypatch, api_error, VALID_SVG)

    panel = generator.generate_panel(STORIES)

    assert panel.svg.startswith("<svg")
    assert len(seen) == 2


def test_api_failure_is_not_fed_back_as_a_prompt_problem(monkeypatch):
    # There's no model output to critique, so the retry must be asked afresh
    # rather than told to "fix" an error the model never saw.
    seen = replies(monkeypatch, ConnectionError("upstream stalled"), VALID_SVG)

    generator.generate_panel(STORIES)

    assert seen == [None, None]


def test_invalid_svg_is_fed_back_into_the_retry(monkeypatch):
    seen = replies(monkeypatch, "not markup at all", VALID_SVG)

    generator.generate_panel(STORIES)

    assert seen[0] is None
    assert seen[1], "the retry should be told what was wrong with attempt 1"


def test_gives_up_after_max_attempts_and_reports_the_last_failure(monkeypatch):
    seen = replies(monkeypatch, *[ConnectionError("upstream stalled")] * 3)

    with pytest.raises(RuntimeError, match="upstream stalled"):
        generator.generate_panel(STORIES, max_attempts=3)

    assert len(seen) == 3


# --- What the previous panel hands over ------------------------------------


def rendered_prompts(monkeypatch, *outcomes):
    """Stub the LLM and return the fully rendered prompt text of each call.

    Asserting on the rendered template (rather than the params dict) is the
    point: it's the only way to be sure nothing leaks yesterday's markup into
    what the model actually reads.
    """
    from jinja2 import Template

    template = Template(Path(generator.PROMPT_TEMPLATE).read_text())
    prompts = []
    remaining = list(outcomes)

    def fake_get_llm_response(template_path, params, model):
        prompts.append(template.render(**params))
        return remaining.pop(0)

    monkeypatch.setattr(generator, "get_llm_response", fake_get_llm_response)
    return prompts


YESTERDAY = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="200" '
    'viewBox="0 0 1600 200">'
    '<defs><pattern id="linen" width="10" height="10">'
    '<rect width="10" height="10" fill="#FDFAF5"/></pattern></defs>'
    '<rect x="0" y="40" width="1600" height="170" fill="url(#linen)"/>'
    '<path d="M 0 150 L 1600 210 L 0 210 Z" fill="#a87c51"/>'
    '<circle cx="42" cy="120" r="9" fill="#b53c2c" id="manchester-bee"/>'
    "</svg>"
)


def test_yesterdays_markup_never_reaches_the_prompt(monkeypatch):
    """The convergence bug: panels used to be given the whole previous SVG.

    The model then inherited its palette and motifs and, by 2026-07-22, was
    reproducing its <defs> block byte-for-byte -- so every day looked alike.
    """
    prompts = rendered_prompts(monkeypatch, VALID_SVG)

    generator.generate_panel(STORIES, previous_svg=YESTERDAY, day="2026-07-21")

    prompt = prompts[0]
    assert "<pattern" not in prompt and "<rect" not in prompt
    assert "linen" not in prompt
    assert "manchester-bee" not in prompt


def test_the_seam_colours_do_reach_the_prompt(monkeypatch):
    # The seam still has to join invisibly, so the tones must survive.
    prompts = rendered_prompts(monkeypatch, VALID_SVG)

    generator.generate_panel(STORIES, previous_svg=YESTERDAY, day="2026-07-21")

    assert "#a87c51" in prompts[0]


def test_the_style_brief_is_seeded_on_the_day(monkeypatch):
    prompts = rendered_prompts(monkeypatch, VALID_SVG, VALID_SVG)

    generator.generate_panel(STORIES, previous_svg=YESTERDAY, day="2026-07-21")
    generator.generate_panel(STORIES, previous_svg=YESTERDAY, day="2026-07-22")

    assert style_directive("2026-07-21") in prompts[0]
    assert style_directive("2026-07-22") in prompts[1]
    assert prompts[0] != prompts[1], "consecutive days must be briefed differently"


def test_the_first_panel_is_not_asked_to_join_anything(monkeypatch):
    prompts = rendered_prompts(monkeypatch, VALID_SVG)

    generator.generate_panel(STORIES, day="2026-07-07")

    assert "the very first section" in prompts[0]
