"""Running library scripts and one-off code against the game.

Both go through ``steps.run_step`` with the library mounted, so one-off code can
import library scripts too, and both come back as a ``StepOutcome`` plus the
``Trace`` the agent is shown. Neither commits anything: the caller decides
whether a step's state is kept (one that didn't verify never is).
"""

import json
from collections.abc import Callable
from pathlib import Path

from pyboy import PyBoy

from gb_agent.library import Library, ScriptError, check_name
from gb_agent.steps import StepLimits, StepOutcome, run_step
from gb_agent.trace import Trace, build_trace

MAX_ARGS_BYTES = 4_000


def call_code(name: str, args: dict) -> str:
    """Code that calls library script ``name`` with keyword ``args``."""
    check_name(name)
    encoded = json.dumps(args)
    return (
        "import json\n"
        f"from library.{name} import {name} as _script\n"
        f"result = _script(game, **json.loads({json.dumps(encoded)}))\n"
    )


def _describe_call(name: str, args: dict, version: str) -> str:
    shown = ", ".join(f"{key}={value!r}" for key, value in args.items())
    return f"{name}({shown}) @ {version}"


def run_script(
    library: Library,
    name: str,
    args: dict | None,
    *,
    rom_path: Path,
    state: bytes,
    start_frame: int = 0,
    watch: dict | None = None,
    limits: StepLimits = StepLimits(),
    image: str | None = None,
    read_text: Callable[[PyBoy], list[list[str]]] | None = None,
) -> tuple[StepOutcome, Trace, str]:
    """Run library script ``name``; return the outcome, its trace, and the version run."""
    args = args or {}
    if not isinstance(args, dict) or not all(isinstance(k, str) for k in args):
        raise ScriptError("args must be a dict of keyword arguments")
    try:
        if len(json.dumps(args)) > MAX_ARGS_BYTES:
            raise ScriptError(f"args are limited to {MAX_ARGS_BYTES} bytes of JSON")
    except TypeError:
        raise ScriptError("args must be JSON: numbers, strings, lists, dicts") from None
    version = library.version(name)  # raises if there's no such script

    outcome = run_step(rom_path, state, call_code(name, args), start_frame=start_frame,
                       limits=limits, library_dir=library.package_dir, watch=watch,
                       image=image, read_text=read_text)
    library.record_use(name, version, ok=outcome.usable and outcome.sandbox.status == "ok",
                       frames=outcome.frames_used,
                       error=(outcome.sandbox.error or {}).get("type") or outcome.problem or None)
    return outcome, build_trace(outcome, _describe_call(name, args, version)), version


def run_code(
    library: Library,
    code: str,
    *,
    rom_path: Path,
    state: bytes,
    start_frame: int = 0,
    watch: dict | None = None,
    limits: StepLimits = StepLimits(),
    image: str | None = None,
    read_text: Callable[[PyBoy], list[list[str]]] | None = None,
) -> tuple[StepOutcome, Trace]:
    """Run one-off ``code``, with ``game`` and the library available."""
    outcome = run_step(rom_path, state, code, start_frame=start_frame, limits=limits,
                       library_dir=library.package_dir, watch=watch, image=image,
                       read_text=read_text)
    return outcome, build_trace(outcome, "one-off code")
