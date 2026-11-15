"""Tests for interest profiles."""

from pathlib import Path

import pytest

from content_screening.profile import (
    PROFILE_ENV_VAR,
    PROFILES_DIR,
    ProfileError,
    get_active_profile,
    load_profile,
    load_profile_file,
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(body)
    return path


MINIMAL = """
name: demo
model: some/model
description: |
  Interested in demos.
"""


class TestPvProfile:
    """profiles/pv.yaml must reproduce the pre-profile PV configuration."""

    def test_keywords_and_categories_match_the_old_constants(self):
        pv = load_profile("pv")
        assert pv.keywords == {
            "drug", "pharma", "adverse", "reaction", "medic", "duplic", "linkage",
        }
        assert pv.arxiv_categories == {
            "cs.AI", "cs.CE", "cs.CL", "cs.LG", "stat.AP", "stat.CO", "stat.ME",
            "stat.ML", "stat.TH", "math.ST", "q-bio.QM",
        }

    def test_sources_and_model(self):
        pv = load_profile("pv")
        assert pv.model == "deepseek/deepseek-v4.1-flash"
        assert len(pv.feeds) == 16
        assert [t["id"] for t in pv.openalex.topics] == [
            "T11943", "T10508", "T13702", "T11396",
        ]
        assert [i["id"] for i in pv.openalex.institutions] == ["I111684115"]
        # The contact address is not part of a profile.
        assert pv.openalex.mailto == ""
        assert pv.rubric == ()
        assert pv.threshold is None

    def test_description_carries_the_pv_interests(self):
        pv = load_profile("pv")
        assert pv.description.startswith("You are a research paper relevance assessor")
        assert "Uppsala Monitoring Centre" in pv.description
        assert pv.description.rstrip().endswith("incremental/routine?")


def test_every_shipped_profile_loads():
    names = sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))
    assert "pv" in names
    for name in names:
        assert load_profile(name).name == name


class TestActiveProfile:
    def test_defaults_to_pv(self):
        assert get_active_profile().name == "pv"

    def test_env_var_selects_profile(self, monkeypatch, tmp_path):
        _write(tmp_path, "demo", MINIMAL)
        monkeypatch.setattr("content_screening.profile.PROFILES_DIR", tmp_path)
        monkeypatch.setenv(PROFILE_ENV_VAR, "demo")
        assert get_active_profile().name == "demo"

    def test_unknown_profile_fails_loudly(self, monkeypatch):
        monkeypatch.setenv(PROFILE_ENV_VAR, "no-such-profile")
        with pytest.raises(ProfileError, match="not found"):
            get_active_profile()


class TestParsing:
    def test_minimal_profile_has_empty_sources(self, tmp_path):
        profile = load_profile_file(_write(tmp_path, "demo", MINIMAL))
        assert profile.keywords == frozenset()
        assert profile.feeds == ()
        assert profile.openalex.topics == []
        assert profile.description == "Interested in demos."

    def test_keywords_are_lowercased(self, tmp_path):
        profile = load_profile_file(
            _write(tmp_path, "demo", MINIMAL + "keywords: [Fraud, AML]\n")
        )
        assert profile.keywords == {"fraud", "aml"}

    def test_name_must_match_file(self, tmp_path):
        with pytest.raises(ProfileError, match="does not match"):
            load_profile_file(_write(tmp_path, "other", MINIMAL))

    @pytest.mark.parametrize("key", ["name", "model", "description"])
    def test_required_keys(self, tmp_path, key):
        body = "\n".join(
            line for line in MINIMAL.splitlines()
            if not line.startswith(f"{key}:")
        )
        if key == "description":
            body = body.replace("  Interested in demos.", "")
        with pytest.raises(ProfileError):
            load_profile_file(_write(tmp_path, "demo", body))

    def test_rubric_and_threshold(self, tmp_path):
        body = MINIMAL + """
threshold: 3.5
rubric:
  - id: on_topic
    statement: The paper is about demos.
    weight: 2
    required: true
  - id: survey
    statement: It is mainly a survey.
    weight: -1
"""
        profile = load_profile_file(_write(tmp_path, "demo", body))
        assert profile.threshold == 3.5
        assert [s.id for s in profile.rubric] == ["on_topic", "survey"]
        assert profile.rubric[0].required is True
        assert profile.rubric[1].required is False
        assert profile.rubric[1].weight == -1.0

    def test_signal_bonuses(self, tmp_path):
        body = MINIMAL + "signal_bonuses: {author: 2, citation: 1.5}\n"
        profile = load_profile_file(_write(tmp_path, "demo", body))
        assert profile.signal_bonuses == {"author": 2.0, "citation": 1.5}
        assert load_profile_file(_write(tmp_path, "demo", MINIMAL)).signal_bonuses == {}

    def test_rubric_ids_must_be_unique(self, tmp_path):
        body = MINIMAL + """
rubric:
  - {id: a, statement: One., weight: 1}
  - {id: a, statement: Two., weight: 1}
"""
        with pytest.raises(ProfileError, match="duplicate"):
            load_profile_file(_write(tmp_path, "demo", body))

    def test_rubric_item_needs_a_weight(self, tmp_path):
        body = MINIMAL + "rubric:\n  - {id: a, statement: One.}\n"
        with pytest.raises(ProfileError, match="malformed"):
            load_profile_file(_write(tmp_path, "demo", body))
