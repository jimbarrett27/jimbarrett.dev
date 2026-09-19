"""Where the bots' runtime state lives.

The databases and cooldown files the bots write are deliberately not tied to the
checkout they are launched from. The server runs production out of a deploy
clone that is meant to be disposable -- delete it, re-clone it, move it to a new
commit -- and that is only safe if 130 MB of screening history isn't sitting
inside it. Point ``JIMBARRETT_DATA_DIR`` at somewhere stable and it won't be.

Leave the variable unset and everything resolves to the repo root, which is
where these files already live, so dev and the test suite are unaffected.

Resolving against the repo root rather than the process's cwd is the other half
of this. ``sqlite:///content_screening.db`` was relative to whatever directory
the bot happened to be started from, so the same command run from a subdirectory
would quietly open (or create) a different, empty database.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """The directory holding runtime state.

    Read from the environment on every call rather than captured at import, so
    a test can point it at a tmp_path and a systemd unit can set it without
    caring about import order.
    """
    configured = os.environ.get("JIMBARRETT_DATA_DIR")
    return Path(configured).expanduser() if configured else REPO_ROOT


def data_path(*parts: str) -> Path:
    """Path to one piece of runtime state, under :func:`data_dir`."""
    return data_dir().joinpath(*parts)


def sqlite_url(*parts: str) -> str:
    """SQLAlchemy URL for a SQLite file under :func:`data_dir`.

    :func:`data_path` is always absolute, so this yields the four-slash form
    (``sqlite:////home/...``) that SQLAlchemy reads as an absolute path.
    """
    return f"sqlite:///{data_path(*parts)}"
