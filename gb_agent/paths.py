"""Where gb_agent keeps its data: ROMs, start states and runs.

Runs are big (save states, frames, clips for every step) and written constantly, so
they get their own location rather than sharing ``JIMBARRETT_DATA_DIR`` with the
bots' SQLite databases. On the server ``GB_AGENT_DIR`` points at the 4 TB disk
(``/mnt/storage/data/gb_agent``). Unset, it falls back to ``gb_agent/`` under
``util.paths.data_dir()``, as before, so dev and tests are unaffected.

Read on every call, like ``util.paths.data_dir``, so a test can point it elsewhere.
"""

import os
from pathlib import Path

from util.paths import data_path


def gb_agent_dir() -> Path:
    configured = os.environ.get("GB_AGENT_DIR")
    return Path(configured).expanduser() if configured else data_path("gb_agent")


def gb_agent_path(*parts: str) -> Path:
    return gb_agent_dir().joinpath(*parts)
