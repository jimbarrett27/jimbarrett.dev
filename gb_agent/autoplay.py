"""Keep the agent playing: what the ``gb-agent`` systemd user unit runs.

``python -m gb_agent.autoplay`` plays one *series*: a game started from the bedroom
and carried on through as many runs as it takes. Each start resumes the newest run
of the series from its last kept step, so a reboot, a crash or a deploy costs at
most the step in progress. The run itself is ``gb_agent.play`` in a child process;
this only decides what to start and hands it a clean shutdown.

``$GB_AGENT_DIR/autoplay.json`` says what to play, and is the on/off switch:

    {"model": "qwen3.6-35b-a3b-local", "start": null}

``start`` is the first run of the series; null starts a new game, and the run it
starts is written back as ``start``. Without the file nothing is played, and the
exit status (``NOT_CONFIGURED``) tells systemd not to keep retrying.

Runs have no budget: the limits are set far past anything a run will reach, and no
video is rendered at the end (a days-long run would take a long time to render).
"""

import json
import logging
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from gb_agent.models import get_profile
from gb_agent.paths import gb_agent_path

logger = logging.getLogger(__name__)

NOT_CONFIGURED = 3  # RestartPreventExitStatus in the unit
UNLIMITED = 10**12
MAX_CHAIN = 10_000  # resumes followed back to a series' start before giving up
RUN_ID_WAIT_S = 120  # for the child to print its run id


def config_path() -> Path:
    return gb_agent_path("autoplay.json")


def load_config(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def _manifest(run_dir: Path) -> dict | None:
    path = run_dir / "manifest.json"
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except json.JSONDecodeError:  # a run killed mid-write
        return None


def has_kept_step(run_dir: Path) -> bool:
    path = run_dir / "steps.jsonl"
    if not path.exists():
        return False
    for line in path.read_text().splitlines():
        try:
            if json.loads(line).get("kept"):
                return True
        except json.JSONDecodeError:  # a half-written last line
            continue
    return False


def in_series(run_dir: Path, start: str) -> bool:
    """Whether ``run_dir`` is ``start`` or was resumed, at any remove, from it."""
    root, run = run_dir.parent, run_dir.name
    for _ in range(MAX_CHAIN):
        if run == start:
            return True
        manifest = _manifest(root / run)
        run = ((manifest or {}).get("resumed_from") or {}).get("run")
        if run is None:
            return False
    return False


def series(root: Path, start: str) -> list[Path]:
    """Every run of the series, oldest first (run ids start with the time)."""
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and in_series(p, start))


def series_run(root: Path, start: str) -> Path | None:
    """The newest run of the series with a kept step to resume from."""
    return next((r for r in reversed(series(root, start)) if has_kept_step(r)), None)


def play_command(model: str, resume: str | None) -> list[str]:
    cmd = [sys.executable, "-m", "gb_agent.play", "--model", model,
           "--frames", str(UNLIMITED), "--max-calls", str(UNLIMITED),
           "--max-tokens", str(UNLIMITED), "--max-minutes", str(UNLIMITED),
           "--publish", "--no-notify"]
    return cmd + (["--resume", resume] if resume else [])


def wait_for_model(model: str, poll_s: float = 10) -> None:
    """Block until a local model's server answers; a paid model needs no wait."""
    profile = get_profile(model)
    if profile.provider != "local" or not profile.base_url:
        return
    health = profile.base_url.removesuffix("/v1") + "/health"
    waited = False
    while True:
        try:
            with urllib.request.urlopen(health, timeout=5) as response:
                if response.status == 200:
                    if waited:
                        logger.info("model server is up")
                    return
        except OSError:
            pass
        if not waited:
            logger.info("waiting for the model server at %s", health)
            waited = True
        time.sleep(poll_s)


def _run_id(out: Path, child: subprocess.Popen) -> str | None:
    """The run id ``play`` prints as its first line."""
    deadline = time.monotonic() + RUN_ID_WAIT_S
    while True:
        exited = child.poll() is not None  # before reading, so a last line isn't missed
        for line in out.read_text().splitlines():
            if line.startswith("run "):
                return line.split()[1]
        if exited or time.monotonic() > deadline:
            return None
        time.sleep(0.5)


def supervise(cmd: list[str], out: Path, on_run_id=None) -> int:
    """Run ``cmd`` to the end, output to ``out``; a SIGINT or SIGTERM is passed on as
    SIGINT, so ``play`` finishes its run and its publisher sends the end."""
    with out.open("a") as log:
        # Its own session: a Ctrl-C in a terminal reaches it once, through us.
        child = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, start_new_session=True)

    def stop(signum, _frame):
        logger.info("got %s: asking the run to finish", signal.Signals(signum).name)
        if child.poll() is None:
            child.send_signal(signal.SIGINT)

    previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        if on_run_id is not None and (run_id := _run_id(out, child)) is not None:
            on_run_id(run_id)
        return child.wait()
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    path = config_path()
    config = load_config(path)
    if config is None:
        logger.info("no %s: nothing to play", path)
        return NOT_CONFIGURED
    model = config["model"]
    wait_for_model(model)

    root = gb_agent_path("runs")
    start = config.get("start")
    resume = series_run(root, start) if start else None

    def record(run_id: str) -> None:
        config["start"] = run_id
        path.write_text(json.dumps(config, indent=2) + "\n")
        logger.info("new game: the series starts at %s", run_id)

    if resume is None:
        logger.info("starting a new game with %s", model)
    else:
        logger.info("resuming %s", resume.name)
    root.mkdir(parents=True, exist_ok=True)
    out = root / f"live-{datetime.now():%Y%m%d-%H%M%S}.out"
    code = supervise(play_command(model, resume.name if resume else None), out,
                     on_run_id=record if resume is None else None)
    logger.info("run ended with status %d", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
