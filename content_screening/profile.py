"""
Interest profiles: everything that defines "interesting" for one field.

A profile is one YAML file under ``content_screening/profiles/`` holding the
discovery sources (keywords, arXiv categories, RSS feeds, OpenAlex signals), the
prose interest description that fills the screening prompt, the screening model,
and the rubric and threshold used to score papers.

Exactly one profile is active at a time, chosen by ``CONTENT_SCREENING_PROFILE``
(default ``fincrime``). Its name is stored on every article screened under it, so the
fields never get mixed up in training data.

The OpenAlex contact address is deliberately not part of a profile; it lives in
``openalex.py``.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from content_screening.constants import MODULE_ROOT

PROFILES_DIR = MODULE_ROOT / "profiles"
PROFILE_ENV_VAR = "CONTENT_SCREENING_PROFILE"
DEFAULT_PROFILE = "fincrime"


@dataclass
class FeedConfig:
    """Configuration for a single RSS feed."""
    name: str
    url: str
    category: Optional[str] = None


@dataclass
class DiscoveryConfig:
    """OpenAlex discovery signals (the ``openalex`` block of a profile)."""

    mailto: str = ""
    topics: List[dict] = field(default_factory=list)          # [{id, name, require_keyword?}]
    monitored_authors: List[str] = field(default_factory=list)
    seed_papers: List[str] = field(default_factory=list)
    institutions: List[dict] = field(default_factory=list)    # [{id, name, author_positions}]
    trusted_publishers: List[str] = field(default_factory=list)  # extra allowlist, added to defaults


@dataclass(frozen=True)
class RubricStatement:
    """One rubric statement the screening LLM agrees or disagrees with.

    The LLM's answer maps to -2..+2 (or 0 for "can't tell"); the score is the
    weighted sum, computed in code. A ``required`` statement answered "strongly
    disagree" rejects the paper whatever the other answers are.
    """

    id: str
    statement: str
    weight: float
    required: bool = False


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    model: str
    keywords: frozenset
    arxiv_categories: frozenset
    feeds: tuple
    openalex: DiscoveryConfig
    rubric: tuple = ()
    threshold: Optional[float] = None
    # Points added to the rubric score per discovery signal on the paper
    # (e.g. {"author": 2, "citation": 2}), computed in code, never asked of
    # the LLM. Keys are ``Article.surfaced_by`` values.
    signal_bonuses: dict = field(default_factory=dict)


class ProfileError(ValueError):
    """A profile file is missing or malformed."""


def _parse_rubric(raw: list, path: Path) -> tuple:
    statements = []
    seen = set()
    for i, item in enumerate(raw or []):
        try:
            statement = RubricStatement(
                id=str(item["id"]),
                statement=str(item["statement"]).strip(),
                weight=float(item["weight"]),
                required=bool(item.get("required", False)),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ProfileError(f"{path}: rubric item {i} is malformed: {e}") from e
        if statement.id in seen:
            raise ProfileError(f"{path}: duplicate rubric id {statement.id!r}")
        seen.add(statement.id)
        statements.append(statement)
    return tuple(statements)


def _parse_signal_bonuses(raw: Optional[dict], path: Path) -> dict:
    try:
        return {str(k): float(v) for k, v in (raw or {}).items()}
    except (AttributeError, TypeError, ValueError) as e:
        raise ProfileError(f"{path}: signal_bonuses is malformed: {e}") from e


def _parse_openalex(raw: Optional[dict]) -> DiscoveryConfig:
    raw = raw or {}
    return DiscoveryConfig(
        topics=raw.get("topics") or [],
        monitored_authors=raw.get("monitored_authors") or [],
        seed_papers=raw.get("seed_papers") or [],
        institutions=raw.get("institutions") or [],
        trusted_publishers=raw.get("trusted_publishers") or [],
    )


def load_profile_file(path: Path) -> Profile:
    """Parse one profile YAML file."""
    if not path.exists():
        raise ProfileError(f"Profile not found: {path}")
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    for key in ("name", "description", "model"):
        if not data.get(key):
            raise ProfileError(f"{path}: missing required key {key!r}")
    if data["name"] != path.stem:
        raise ProfileError(
            f"{path}: name {data['name']!r} does not match the file name"
        )

    threshold = data.get("threshold")
    return Profile(
        name=data["name"],
        description=data["description"].strip(),
        model=data["model"],
        keywords=frozenset(str(k).lower() for k in data.get("keywords") or []),
        arxiv_categories=frozenset(data.get("arxiv_categories") or []),
        feeds=tuple(
            FeedConfig(name=f["name"], url=f["url"], category=f.get("category"))
            for f in data.get("feeds") or []
        ),
        openalex=_parse_openalex(data.get("openalex")),
        rubric=_parse_rubric(data.get("rubric"), path),
        threshold=float(threshold) if threshold is not None else None,
        signal_bonuses=_parse_signal_bonuses(data.get("signal_bonuses"), path),
    )


def load_profile(name: str) -> Profile:
    """Load the profile called ``name`` from ``profiles/``."""
    return load_profile_file(PROFILES_DIR / f"{name}.yaml")


def active_profile_name() -> str:
    return os.environ.get(PROFILE_ENV_VAR) or DEFAULT_PROFILE


def get_active_profile() -> Profile:
    """The profile selected by ``CONTENT_SCREENING_PROFILE`` (default ``fincrime``)."""
    return load_profile(active_profile_name())
