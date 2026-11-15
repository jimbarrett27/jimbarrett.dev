"""Content-screening tests run under the PV profile unless they say otherwise,
whatever CONTENT_SCREENING_PROFILE the shell happens to have set. Many fixtures
are PV papers that only pass PV's keyword net."""

import pytest

from content_screening.profile import PROFILE_ENV_VAR


@pytest.fixture(autouse=True)
def _pv_profile(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV_VAR, "pv")
