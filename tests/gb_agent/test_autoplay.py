"""Keeping a series going: which run to resume, and handing the run a clean stop."""

import json
import os
import signal
import sys
import threading

from gb_agent import autoplay
from gb_agent.autoplay import play_command, series_run, supervise


def make_run(root, run_id, *, kept=True, resumed_from=None):
    run = root / run_id
    run.mkdir(parents=True)
    manifest = {"run": run_id, "resumed_from": {"run": resumed_from, "step": 1} if resumed_from
                else None}
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "steps.jsonl").write_text(json.dumps({"step": 1, "kept": kept}) + "\n")
    return run


def test_the_newest_run_of_the_series_with_a_kept_step_is_resumed(tmp_path):
    make_run(tmp_path, "20261028-060000-a")
    make_run(tmp_path, "20261028-070000-b", resumed_from="20261028-060000-a")
    make_run(tmp_path, "20261028-080000-c", resumed_from="20261028-070000-b")
    make_run(tmp_path, "20261028-090000-d", kept=False, resumed_from="20261028-080000-c")
    make_run(tmp_path, "20261028-100000-other")  # a different game, started by hand
    (tmp_path / "live-20261028-060000.out").write_text("")

    assert series_run(tmp_path, "20261028-060000-a").name == "20261028-080000-c"


def test_a_series_with_nothing_kept_has_nothing_to_resume(tmp_path):
    make_run(tmp_path, "20261028-060000-a", kept=False)
    assert series_run(tmp_path, "20261028-060000-a") is None
    assert series_run(tmp_path / "missing", "x") is None


def test_runs_go_on_without_limits_or_a_video():
    fresh = play_command("qwen3.6-35b-a3b-local", None)
    assert "--resume" not in fresh and "--video" not in fresh
    assert fresh[fresh.index("--max-minutes") + 1] == str(autoplay.UNLIMITED)
    assert {"--publish", "--no-notify"} <= set(fresh)
    resumed = play_command("qwen3.6-35b-a3b-local", "20261028-080000-c")
    assert resumed[-2:] == ["--resume", "20261028-080000-c"]


CHILD = """
import sys, time
print("run 20261028-060000-new", flush=True)
try:
    time.sleep(30)
except KeyboardInterrupt:
    print("finished cleanly", flush=True)
    sys.exit(7)
"""


def test_a_stop_reaches_the_run_as_ctrl_c_and_is_waited_for(tmp_path):
    out = tmp_path / "live.out"
    seen = []

    def got_id(run_id):
        seen.append(run_id)
        threading.Timer(0.5, os.kill, (os.getpid(), signal.SIGTERM)).start()

    code = supervise([sys.executable, "-c", CHILD], out, on_run_id=got_id)

    assert seen == ["20261028-060000-new"]
    assert code == 7 and "finished cleanly" in out.read_text()
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL  # handlers put back


def test_nothing_is_played_without_a_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GB_AGENT_DIR", str(tmp_path))
    assert autoplay.main() == autoplay.NOT_CONFIGURED


def test_a_new_game_records_where_the_series_starts(tmp_path, monkeypatch):
    monkeypatch.setenv("GB_AGENT_DIR", str(tmp_path))
    (tmp_path / "autoplay.json").write_text(json.dumps({"model": "qwen3.6-35b-a3b-local",
                                                        "start": None}))
    monkeypatch.setattr(autoplay, "wait_for_model", lambda model: None)
    started = []

    def fake_play(model, resume):
        started.append(resume)
        return [sys.executable, "-c", "print('run 20261028-060000-new', flush=True)"]

    monkeypatch.setattr(autoplay, "play_command", fake_play)
    assert autoplay.main() == 0
    assert started == [None]
    assert json.loads((tmp_path / "autoplay.json").read_text())["start"] == "20261028-060000-new"

    make_run(tmp_path / "runs", "20261028-060000-new")
    assert autoplay.main() == 0
    assert started == [None, "20261028-060000-new"]
