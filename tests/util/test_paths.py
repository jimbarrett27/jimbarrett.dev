"""Data-directory resolution.

The load-bearing case is the default one: with JIMBARRETT_DATA_DIR unset every
path has to land exactly where it did before the indirection existed, or a
deploy silently starts a fresh, empty database next to the checkout.
"""

import pytest

from util.paths import REPO_ROOT, data_dir, data_path, sqlite_url


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("JIMBARRETT_DATA_DIR", raising=False)


def test_defaults_to_repo_root():
    assert data_dir() == REPO_ROOT


@pytest.mark.parametrize(
    "parts, legacy",
    [
        (("content_screening.db",), REPO_ROOT / "content_screening.db"),
        (("flashcards.db",), REPO_ROOT / "flashcards.db"),
        (("dnd.db",), REPO_ROOT / "dnd.db"),
        (("diary", "entries"), REPO_ROOT / "diary" / "entries"),
        (("memes", "recent_templates.json"), REPO_ROOT / "memes" / "recent_templates.json"),
    ],
)
def test_default_paths_match_the_pre_datadir_locations(parts, legacy):
    assert data_path(*parts) == legacy


def test_env_var_redirects(monkeypatch, tmp_path):
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path
    assert data_path("dnd.db") == tmp_path / "dnd.db"


def test_env_var_is_read_per_call(monkeypatch, tmp_path):
    """Not captured at import, so a unit or a test can set it late."""
    assert data_dir() == REPO_ROOT
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def test_user_home_is_expanded(monkeypatch):
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", "~/data")
    assert data_dir().is_absolute()
    assert "~" not in str(data_dir())


def test_sqlite_url_is_absolute_four_slash_form(monkeypatch, tmp_path):
    """sqlite:///relative and sqlite:////absolute mean different things."""
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path))
    url = sqlite_url("dnd.db")
    assert url.startswith("sqlite:////")
    assert url == f"sqlite:///{tmp_path / 'dnd.db'}"


def test_engines_follow_the_env_var(monkeypatch, tmp_path):
    """The whole point: the app's engine opens the configured file."""
    from dnd import db_engine

    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path))
    db_engine.reset_engine()
    try:
        assert str(tmp_path) in str(db_engine.get_engine().url)
    finally:
        db_engine.reset_engine()
