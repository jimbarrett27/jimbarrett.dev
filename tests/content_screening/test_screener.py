"""Tests for the screener, with the LLM faked (no OpenRouter calls)."""

import dataclasses
import json

import pytest
from langchain_core.prompts import PromptTemplate

from content_screening import screener
from content_screening.models import Article, SourceType
from content_screening.profile import load_profile

FINCRIME = dataclasses.replace(
    load_profile("fincrime"), threshold=5.0, signal_bonuses={"citation": 2.0}
)


def _article(**kw) -> Article:
    return Article(
        external_id="x1",
        source_type=SourceType.ARXIV,
        title=kw.pop("title", "Graph learning for money mule detection"),
        abstract=kw.pop("abstract", "We detect mule accounts in bank transfers."),
        url="https://arxiv.org/abs/x1",
        **kw,
    )


def _all(label: str) -> dict:
    return {s.id: {"justification": "j", "answer": label} for s in FINCRIME.rubric}


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace get_llm_response; records each call, replies with ``reply``."""
    calls = []
    state = {"reply": "{}"}

    def fake(template_path, params, model_name):
        calls.append({"template": template_path, "params": params, "model": model_name})
        reply = state["reply"]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(screener, "get_llm_response", fake)
    fake.calls = calls
    fake.state = state
    return fake


def _render(call) -> str:
    """Render the prompt exactly as llm_util does."""
    with open(call["template"]) as f:
        template = PromptTemplate.from_template(f.read(), template_format="jinja2")
    return template.format(**call["params"])


class TestRubricScreening:
    def test_prompt_lists_every_statement_and_the_paper(self, fake_llm):
        fake_llm.state["reply"] = json.dumps({"answers": _all("agree"), "summary": "s"})
        screener.screen_article(_article(), FINCRIME)

        call = fake_llm.calls[0]
        assert call["model"] == FINCRIME.model
        prompt = _render(call)
        assert prompt.startswith("You are assessing research papers")
        for s in FINCRIME.rubric:
            assert f"`{s.id}`: {s.statement}" in prompt
            assert f'"{s.id}": {{"justification": "...", "answer": "..."}}' in prompt
        assert "money mule detection" in prompt
        assert "judge from the title alone" not in prompt

    def test_title_only_papers_are_flagged_in_the_prompt(self, fake_llm):
        fake_llm.state["reply"] = json.dumps({"answers": {}})
        screener.screen_article(_article(abstract=None), FINCRIME)
        assert "judge from the title alone" in _render(fake_llm.calls[0])

    def test_scores_in_code_and_queues_above_threshold(self, fake_llm):
        answers = _all("disagree")
        answers["fincrime"]["answer"] = "strongly_agree"
        answers["transfer"]["answer"] = "agree"
        fake_llm.state["reply"] = "```json\n" + json.dumps({
            "answers": answers, "summary": "A mule-detection paper.", "tags": ["aml"],
        }) + "\n```"

        result = screener.screen_article(_article(surfaced_by=["citation"]), FINCRIME)

        # fincrime 3*2 + transfer 2*1, every other statement disagree (-1):
        # positives -(2+1.5+1.5+1+1+1) = -8, negatives (survey -1, legal -2) +3,
        # plus the citation bonus 2.
        assert result.score == 6 + 2 - 8 + 3 + 2
        assert result.status == "pending"
        assert result.reasoning == "A mule-detection paper."
        assert result.tags == ["aml"]
        assert result.rubric_answers["fincrime"] == {
            "answer": "strongly_agree", "justification": "j",
        }

    def test_below_threshold_is_auto_rejected_but_kept_whole(self, fake_llm):
        fake_llm.state["reply"] = json.dumps({"answers": _all("cant_tell")})
        result = screener.screen_article(_article(), FINCRIME)
        assert (result.status, result.score) == ("auto_rejected", 0.0)
        assert set(result.rubric_answers) == {s.id for s in FINCRIME.rubric}

    def test_required_statement_rejects(self, fake_llm):
        answers = _all("strongly_agree")
        answers["fincrime"]["answer"] = "strongly_disagree"
        fake_llm.state["reply"] = json.dumps({"answers": answers})
        result = screener.screen_article(_article(), FINCRIME)
        assert result.score > FINCRIME.threshold
        assert result.status == "auto_rejected"

    def test_missing_summary_falls_back_to_justifications(self, fake_llm):
        fake_llm.state["reply"] = json.dumps(
            {"answers": {"fincrime": {"answer": "agree", "justification": "About AML."}}}
        )
        result = screener.screen_article(_article(), FINCRIME)
        assert result.reasoning == "fincrime: About AML."

    @pytest.mark.parametrize("reply", ["not json", "[1, 2]", RuntimeError("timeout")])
    def test_failure_is_rejected_without_a_score(self, fake_llm, reply):
        fake_llm.state["reply"] = reply
        result = screener.screen_article(_article(), FINCRIME)
        assert result.status == "auto_rejected"
        assert result.score is None
        assert result.rubric_answers is None
        assert result.reasoning.startswith("Screening failed")


class TestLegacyScreening:
    PV = load_profile("pv")

    def test_relevant(self, fake_llm):
        fake_llm.state["reply"] = json.dumps({
            "relevance": "HIGH", "confidence": "MEDIUM", "reasoning": "r", "tags": ["t"],
        })
        result = screener.screen_article(_article(), self.PV)
        assert fake_llm.calls[0]["template"].endswith("screen_article.jinja2")
        assert "suggested_depth" not in _render(fake_llm.calls[0])
        assert (result.status, result.score, result.rubric_answers) == ("pending", 0.6, None)

    def test_not_relevant_scores_zero(self, fake_llm):
        fake_llm.state["reply"] = json.dumps({"relevance": "LOW", "confidence": "HIGH"})
        result = screener.screen_article(_article(), self.PV)
        assert (result.status, result.score) == ("auto_rejected", 0.0)

    def test_unparseable_is_rejected(self, fake_llm):
        fake_llm.state["reply"] = "nope"
        assert screener.screen_article(_article(), self.PV).status == "auto_rejected"

    def test_error_defaults_to_queued(self, fake_llm):
        fake_llm.state["reply"] = RuntimeError("down")
        result = screener.screen_article(_article(), self.PV)
        assert (result.status, result.score) == ("pending", 0.5)
