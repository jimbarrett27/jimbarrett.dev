"""The agent's script library: a git repo, so every version of every script is kept.

Layout of a library repo:

    library/__init__.py
    library/<name>.py      one script each, defining a function also called <name>

    subagents/<name>.json  one sub-agent spec each (see gb_agent/subagents.py)

    snippets/stepNNNNN.py  the agent's one-off code (run_code), one file per step

Scripts are mounted read-only into the sandbox, where they import each other as
``from library.walk_to import walk_to``. Being a package, a script can't shadow a
standard-library module by its name.

Every change is a commit: the message is the agent's one-line reason, with the
agent, run and step in trailers. A script's *version* is the short hash of the
last commit that touched it, so ``git log``, ``diff`` and ``blame`` on the repo
show how each script evolved and which step wrote each line.

Usage (calls, failures, frames) is recorded per version in a JSONL file next to
the repo, not in it, so the history stays about code.

The files are written by the agent, so git is always run with hooks off, no
signing, and a fixed identity, and names are validated before they reach a path
or a git command.
"""

import ast
import json
import keyword
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "library"
SUBAGENTS = "subagents"  # sub-agent specs, as <name>.json; never mounted into the sandbox
SNIPPETS = "snippets"  # one-off code, kept for analysis; never mounted, never importable
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
VERSION_RE = re.compile(r"^[0-9a-f]{7,40}$")
MAX_SCRIPT_BYTES = 64_000

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "gb-agent",
    "GIT_AUTHOR_EMAIL": "gb-agent@localhost",
    "GIT_COMMITTER_NAME": "gb-agent",
    "GIT_COMMITTER_EMAIL": "gb-agent@localhost",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
}
_GIT_CONFIG = ["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
               "-c", "init.defaultBranch=main"]


class ScriptError(ValueError):
    """A script, name or version the library won't accept."""


@dataclass(frozen=True)
class ScriptInfo:
    name: str
    version: str
    signature: str  # e.g. "walk_to(game, x: int, y: int)"
    summary: str  # first line of the docstring


@dataclass(frozen=True)
class Change:
    version: str
    date: str
    reason: str


def check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name) or keyword.iskeyword(name):
        raise ScriptError(
            f"bad script name {name!r}: use lowercase letters, digits and underscores, "
            "starting with a letter, at most 40 characters"
        )
    return name


def check_script(name: str, code: str) -> ast.FunctionDef:
    """Check ``code`` is a valid script called ``name``; return its function."""
    check_name(name)
    if not isinstance(code, str) or len(code.encode()) > MAX_SCRIPT_BYTES:
        raise ScriptError(f"a script must be text of at most {MAX_SCRIPT_BYTES} bytes")
    try:
        tree = ast.parse(code, filename=f"{name}.py")
    except SyntaxError as e:
        raise ScriptError(f"syntax error on line {e.lineno}: {e.msg}") from None
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if not functions:
        raise ScriptError(f"a script called {name!r} must define a top-level function {name}()")
    function = functions[-1]
    params = function.args.posonlyargs + function.args.args
    if not params or params[0].arg != "game":
        raise ScriptError(f"{name}()'s first parameter must be `game`")
    if not ast.get_docstring(function):
        raise ScriptError(f"{name}() needs a docstring saying what it does")
    return function


def _signature(function: ast.FunctionDef) -> str:
    return f"{function.name}({ast.unparse(function.args)})"


def _summary(function: ast.FunctionDef) -> str:
    return (ast.get_docstring(function) or "").strip().splitlines()[0]


def _trailers(agent: str | None, run: str | None, step: int | None) -> str:
    lines = [f"{key}: {value}" for key, value in
             (("Agent", agent), ("Run", run), ("Step", step)) if value is not None]
    return "\n\n" + "\n".join(lines) if lines else ""


class Library:
    def __init__(self, root: Path, usage_path: Path | None = None):
        self.root = Path(root)
        self.package_dir = self.root / PACKAGE
        self.usage_path = usage_path or self.root.parent / f"{self.root.name}-usage.jsonl"

    # -- creating -----------------------------------------------------------

    @classmethod
    def create(cls, root: Path, seed: Path | None = None, *, usage_path: Path | None = None,
               run: str | None = None) -> "Library":
        """A new library at ``root``, holding copies of the scripts in ``seed``."""
        library = cls(root, usage_path)
        if library.root.exists() and any(library.root.iterdir()):
            raise FileExistsError(f"{library.root} already exists and isn't empty")
        library.package_dir.mkdir(parents=True, exist_ok=True)
        library._git("init", "-q")
        library._write(library.package_dir / "__init__.py",
                       '"""Scripts the agent has written. See gb_agent/library.py."""\n')
        for path in sorted(Path(seed).glob("*.py")) if seed else []:
            check_script(path.stem, path.read_text())
            library._write(library.package_dir / path.name, path.read_text())
        library._commit("Seed the library" + _trailers("seed", run, None))
        return library

    # -- reading ------------------------------------------------------------

    def path(self, name: str) -> Path:
        return self.package_dir / f"{check_name(name)}.py"

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def version(self, name: str) -> str:
        """Short hash of the last commit that touched ``name``."""
        if not self.exists(name):
            raise ScriptError(f"no script called {name!r}")
        return self._last_commit(f"{PACKAGE}/{name}.py")

    def read(self, name: str, version: str | None = None) -> str:
        """The source of ``name``, now or as of ``version``."""
        if version is None:
            if not self.exists(name):
                raise ScriptError(f"no script called {name!r}")
            return self.path(name).read_text()
        return self._show(f"{PACKAGE}/{check_name(name)}.py", name, version)

    def scripts(self) -> list[ScriptInfo]:
        infos = []
        for path in sorted(self.package_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            function = check_script(path.stem, path.read_text())
            infos.append(ScriptInfo(path.stem, self.version(path.stem),
                                    _signature(function), _summary(function)))
        return infos

    def history(self, name: str) -> list[Change]:
        """Every change to ``name``, newest first."""
        self.version(name)  # raises if there's no such script
        return self._changes(f"{PACKAGE}/{name}.py")

    # -- sub-agents ---------------------------------------------------------

    def subagent_path(self, name: str) -> Path:
        return self.root / SUBAGENTS / f"{check_name(name)}.json"

    def subagent_version(self, name: str) -> str:
        if not self.subagent_path(name).exists():
            raise ScriptError(f"no sub-agent called {name!r}")
        return self._last_commit(f"{SUBAGENTS}/{name}.json")

    def read_subagent(self, name: str, version: str | None = None) -> dict:
        if version is None:
            path = self.subagent_path(name)
            if not path.exists():
                raise ScriptError(f"no sub-agent called {name!r}")
            return json.loads(path.read_text())
        return json.loads(self._show(f"{SUBAGENTS}/{check_name(name)}.json", name, version))

    def subagents(self) -> list[dict]:
        """Every sub-agent spec, with its name and version."""
        folder = self.root / SUBAGENTS
        return [{**json.loads(path.read_text()), "version": self.subagent_version(path.stem)}
                for path in sorted(folder.glob("*.json"))] if folder.exists() else []

    def subagent_history(self, name: str) -> list[Change]:
        self.subagent_version(name)
        return self._changes(f"{SUBAGENTS}/{name}.json")

    def write_subagent(self, name: str, spec: dict, reason: str, *, agent: str | None = None,
                       run: str | None = None, step: int | None = None) -> tuple[str, bool]:
        """Create or replace a sub-agent spec; return its version and whether it changed.

        ``spec`` must already be validated (gb_agent.subagents.check_spec).
        """
        reason = " ".join(str(reason).split())[:200]
        if not reason:
            raise ScriptError("give a one-line reason for the change")
        path = self.subagent_path(name)
        text = json.dumps(spec, indent=2, sort_keys=True) + "\n"
        if path.exists() and path.read_text() == text:
            return self.subagent_version(name), False
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
        self._commit(reason + _trailers(agent, run, step))
        return self.subagent_version(name), True

    # -- snippets -----------------------------------------------------------

    def write_snippet(self, code: str, *, step: int, agent: str | None = None,
                      run: str | None = None) -> str:
        """Keep one-off ``code`` run at ``step``; return the version that holds it.

        Nothing checks it's a script: snippets run as they are, and are only kept so
        a run's history holds all the code the agent ran, not just its scripts.
        """
        if not isinstance(code, str) or len(code.encode()) > MAX_SCRIPT_BYTES:
            raise ScriptError(f"code must be text of at most {MAX_SCRIPT_BYTES} bytes")
        relpath = f"{SNIPPETS}/step{step:05d}.py"
        path = self.root / relpath
        path.parent.mkdir(exist_ok=True)
        path.write_text(code)
        self._commit(f"One-off code at step {step}" + _trailers(agent, run, step))
        return self._last_commit(relpath)

    # -- writing ------------------------------------------------------------

    def write(self, name: str, code: str, reason: str, *, agent: str | None = None,
              run: str | None = None, step: int | None = None) -> str:
        """Create or replace ``name``; return its new version.

        An unchanged script makes no commit and keeps its version.
        """
        check_script(name, code)
        reason = " ".join(str(reason).split())[:200]
        if not reason:
            raise ScriptError("give a one-line reason for the change")
        path = self.path(name)
        if path.exists() and path.read_text() == code:
            return self.version(name)
        self._write(path, code)
        self._commit(reason + _trailers(agent, run, step))
        return self.version(name)

    # -- usage --------------------------------------------------------------

    def record_use(self, name: str, version: str, *, ok: bool, frames: int,
                   error: str | None = None, kind: str = "script") -> None:
        entry = {"script": check_name(name), "version": version, "ok": ok,
                 "frames": frames, "error": error, "kind": kind}
        with self.usage_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def usage(self, kind: str = "script") -> dict[str, dict]:
        """Per script (or sub-agent): uses, failures and frames, overall and per version."""
        totals: dict[str, dict] = {}
        if not self.usage_path.exists():
            return totals
        for line in self.usage_path.read_text().splitlines():
            entry = json.loads(line)
            if entry.get("kind", "script") != kind:
                continue
            script = totals.setdefault(entry["script"], {"calls": 0, "failures": 0,
                                                         "frames": 0, "versions": {}})
            version = script["versions"].setdefault(entry["version"],
                                                    {"calls": 0, "failures": 0, "frames": 0})
            for bucket in (script, version):
                bucket["calls"] += 1
                bucket["failures"] += 0 if entry["ok"] else 1
                bucket["frames"] += entry["frames"]
        return totals

    # -- internals ----------------------------------------------------------

    def _write(self, path: Path, text: str) -> None:
        # The sandbox reads these as another user, so they must be world-readable.
        path.write_text(text)
        path.chmod(0o644)
        self.package_dir.chmod(0o755)

    def _commit(self, message: str) -> None:
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", message)

    def _last_commit(self, relpath: str) -> str:
        return self._git("log", "-1", "--format=%h", "--", relpath).stdout.strip()

    def _show(self, relpath: str, name: str, version: str) -> str:
        if not isinstance(version, str) or not VERSION_RE.match(version):
            raise ScriptError(f"bad version {version!r}")
        shown = self._git("show", f"{version}:{relpath}", check=False)
        if shown.returncode != 0:
            raise ScriptError(f"{name!r} has no version {version!r}")
        return shown.stdout

    def _changes(self, relpath: str) -> list[Change]:
        log = self._git("log", "--format=%h%x1f%cI%x1f%s", "--", relpath).stdout
        return [Change(*line.split("\x1f", 2)) for line in log.splitlines() if line]

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        if shutil.which("git") is None:
            raise RuntimeError("git is needed for the script library")
        return subprocess.run(
            ["git", *_GIT_CONFIG, "-C", str(self.root), *args],
            capture_output=True, text=True, check=check,
            env={**os.environ, **_GIT_ENV},
        )
