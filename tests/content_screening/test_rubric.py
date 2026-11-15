"""Tests for rubric scoring (pure code, no LLM)."""

import dataclasses

import pytest

from content_screening import rubric
from content_screening.profile import DiscoveryConfig, Profile, RubricStatement, load_profile


def _profile(threshold=None, bonuses=None) -> Profile:
    return Profile(
        name="demo",
        description="d",
        model="m",
        keywords=frozenset(),
        arxiv_categories=frozenset(),
        feeds=(),
        openalex=DiscoveryConfig(),
        rubric=(
            RubricStatement("topic", "On topic.", 3, required=True),
            RubricStatement("genai", "Uses GenAI.", 2),
            RubricStatement("survey", "Is a survey.", -1),
        ),
        threshold=threshold,
        signal_bonuses=bonuses or {},
    )


def _answers(**labels):
    return {k: {"answer": v, "justification": ""} for k, v in labels.items()}


class TestNormaliseAnswer:
    @pytest.mark.parametrize("raw,expected", [
        ("strongly_agree", "strongly_agree"),
        ("Strongly Agree", "strongly_agree"),
        ("strongly-disagree", "strongly_disagree"),
        ("AGREE", "agree"),
        ("can't tell", "cant_tell"),
        ("Cannot tell", "cant_tell"),
        ("neither agree nor disagree", "neutral"),
        ("+2", "strongly_agree"),
        (-1, "disagree"),
        ("maybe", None),
        (None, None),
    ])
    def test_variants(self, raw, expected):
        assert rubric.normalise_answer(raw) == expected


class TestParseAnswers:
    def test_one_entry_per_statement_in_rubric_order(self):
        parsed = rubric.parse_answers(_profile(), {
            "survey": {"answer": "disagree", "justification": " New method. "},
            "topic": {"answer": "agree", "justification": "Fraud."},
            "genai": {"answer": "cant_tell", "justification": "Unclear."},
            "extra": {"answer": "agree"},  # not in the rubric: dropped
        })
        assert list(parsed) == ["topic", "genai", "survey"]
        assert parsed["survey"] == {"answer": "disagree", "justification": "New method."}

    def test_missing_and_garbled_answers_become_cant_tell(self):
        parsed = rubric.parse_answers(_profile(), {"topic": {"answer": "sort of"}})
        assert parsed["topic"] == {
            "answer": "cant_tell", "justification": "", "raw_answer": "sort of",
        }
        assert parsed["genai"]["answer"] == "cant_tell"

    def test_bare_string_answers_are_accepted(self):
        parsed = rubric.parse_answers(_profile(), {"topic": "agree"})
        assert parsed["topic"]["answer"] == "agree"

    def test_non_dict_input(self):
        parsed = rubric.parse_answers(_profile(), None)
        assert all(a["answer"] == "cant_tell" for a in parsed.values())


class TestScore:
    def test_weighted_sum(self):
        answers = _answers(topic="strongly_agree", genai="disagree", survey="strongly_disagree")
        # 3*2 + 2*-1 + -1*-2
        assert rubric.rubric_score(_profile(), answers) == 6.0

    def test_cant_tell_and_missing_count_zero(self):
        assert rubric.rubric_score(_profile(), _answers(topic="cant_tell")) == 0.0

    def test_signal_bonuses_added_once_per_signal(self):
        profile = _profile(bonuses={"author": 2, "citation": 1.5})
        answers = _answers(topic="agree")
        assert rubric.score(profile, answers, ["keyword", "author", "citation", "author"]) == 6.5
        assert rubric.score(profile, answers, []) == 3.0


class TestIntake:
    def test_no_threshold_queues_nothing(self):
        answers = _answers(topic="strongly_agree", genai="strongly_agree")
        assert rubric.intake_status(_profile(), answers, 10.0) == "auto_rejected"

    def test_threshold_is_inclusive(self):
        profile = _profile(threshold=4)
        answers = _answers(topic="agree")
        assert rubric.intake_status(profile, answers, 4.0) == "pending"
        assert rubric.intake_status(profile, answers, 3.9) == "auto_rejected"

    def test_required_strongly_disagree_rejects_whatever_the_score(self):
        profile = _profile(threshold=-100)
        answers = _answers(topic="strongly_disagree", genai="strongly_agree")
        assert rubric.failed_required(profile, answers) == ["topic"]
        assert rubric.intake_status(profile, answers, 50.0) == "auto_rejected"

    @pytest.mark.parametrize("label", ["disagree", "cant_tell"])
    def test_required_only_fails_on_strongly_disagree(self, label):
        profile = _profile(threshold=-100)
        assert rubric.intake_status(profile, _answers(topic=label), 0.0) == "pending"


def test_fincrime_weights_match_the_documented_range():
    """The comment in fincrime.yaml quotes a -36..+36 range; keep it honest."""
    fincrime = dataclasses.replace(load_profile("fincrime"), signal_bonuses={})
    best = {s.id: {"answer": "strongly_agree" if s.weight > 0 else "strongly_disagree"}
            for s in fincrime.rubric}
    assert rubric.rubric_score(fincrime, best) == 36.0
