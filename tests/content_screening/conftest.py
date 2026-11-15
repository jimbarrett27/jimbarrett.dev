"""Content-screening tests run under the PV profile unless they say otherwise,
whatever CONTENT_SCREENING_PROFILE the shell happens to have set."""

import pytest

from content_screening.profile import PROFILE_ENV_VAR


@pytest.fixture(autouse=True)
def _default_profile(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV_VAR, raising=False)
