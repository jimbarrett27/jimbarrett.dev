"""Publishing a run for the live page, from a hand-built run directory."""

import json
import os
import time

import av
import pytest

from gb_agent.emulator import RecordingGame, boot, save_state
from gb_agent.library import Library
from gb_agent.publish import LocalDestination, RunPublisher, latest_run, main


class FakeRun:
    """A run directory written the way gb_agent.run.Run writes one."""

    def __init__(self, root, rom, start, name="20261023-120000-silver-fake"):
        self.dir = root / name
        (self.dir / "states").mkdir(parents=True)
        (self.dir / "states" / "start.state").write_bytes(start)
        self.rom, self.state, self.step, self.frame = rom, start, 0, 0
        self.library = Library.create(self.dir / "library")
        self.manifest(ended=False)

    def manifest(self, ended: bool):
        (self.dir / "manifest.json").write_text(json.dumps({
            "run": self.dir.name, "config": {"game": "silver", "model": "fake", "goal": "g",
                                             "frame_budget": 10_000},
            "started_at": "2026-10-23T12:00:00+00:00",
            "ended_at": "2026-10-23T13:00:00+00:00" if ended else None,
            "stop_reason": "frame_budget" if ended else None,
            "frame": self.frame, "steps": self.step, "llm_calls": self.step,
        }))

    def append(self, name, record):
        with (self.dir / name).open("a") as f:
            f.write(json.dumps(record) + "\n")

    def kept_step(self, frames: int, observation: dict | None = None):
        self.step += 1
        pyboy = boot(self.rom, self.state)
        game = RecordingGame(pyboy)
        game.tap("a", hold=2, after=frames - 2)
        game.end_step()
        for event in game.events:
            self.append("events.jsonl", {**event, "step": self.step, "agent": "main"})
        self.state = save_state(pyboy)
        pyboy.stop(save=False)
        (self.dir / "states" / f"step{self.step:05d}.state").write_bytes(self.state)
        used = game.frame
        self.append("steps.jsonl", {"step": self.step, "agent": "main", "kept": True,
                                    "script": "mash", "args": {"times": 1}, "frames": used,
                                    "start_frame": self.frame, "time": time.time(),
                                    "observation": observation})
        self.frame += used
        return used

    def unkept_step(self):
        self.step += 1
        self.append("steps.jsonl", {"step": self.step, "kept": False, "frames": 50})

    def llm(self, text, **call):
        self.append("agents.jsonl", {"time": time.time(), "agent": "main", "kind": "llm",
                                     "text": text, "reasoning": None, "step": self.step,
                                     "tool_calls": [call] if call else []})


@pytest.fixture
def run(tmp_path, test_rom, test_start):
    return FakeRun(tmp_path / "runs", test_rom, test_start)


@pytest.fixture
def dest(tmp_path):
    return LocalDestination(tmp_path / "bucket")


def read(dest, key):
    return json.loads((dest.root / key).read_text())


def publisher(run, dest, **kw):
    return RunPublisher(run.dir, dest, rom=run.rom, **kw)


def test_each_kept_step_becomes_a_clip_of_its_frames(run, dest):
    frames = run.kept_step(30)
    run.unkept_step()
    run.kept_step(20)
    pub = publisher(run, dest)

    assert pub.sync()

    live = read(dest, f"runs/{run.dir.name}/live.json")
    assert [c["step"] for c in live["clips"]] == [1, 3]
    assert live["clips"][0]["script"] == "mash" and live["clips"][0]["args"] == '{"times": 1}'
    clip = dest.root / live["clips"][0]["key"]
    with av.open(str(clip)) as container:
        stream = container.streams.video[0]
        assert (stream.width, stream.height) == (320, 288)
        assert sum(1 for _ in container.decode(stream)) == frames
    assert (run.dir / "clips" / "step00001.mp4").exists()  # kept at home too
    assert read(dest, "current.json") == {"run": run.dir.name, "live": True}


def test_new_steps_and_activity_are_picked_up_as_they_are_appended(run, dest):
    pub = publisher(run, dest)
    pub.sync()
    assert read(dest, f"runs/{run.dir.name}/live.json")["clips"] == []

    run.llm("Heading for the stairs.", name="run_script", args={"name": "walk"})
    run.kept_step(20)
    assert pub.sync()

    live = read(dest, f"runs/{run.dir.name}/live.json")
    assert [c["step"] for c in live["clips"]] == [1]
    assert live["activity"][-1]["text"] == "Heading for the stairs."
    assert live["activity"][-1]["tool_calls"][0]["name"] == "run_script"
    assert live["waiting_since"] is not None


def test_nothing_is_uploaded_when_nothing_changed(run, dest):
    run.kept_step(20)
    pub = publisher(run, dest)
    assert pub.sync()
    assert not pub.sync()


def test_a_restarted_publisher_does_not_upload_clips_again(run, dest):
    run.kept_step(20)
    publisher(run, dest).sync()
    clip = dest.root / "runs" / run.dir.name / "clips" / "step00001.mp4"
    clip.unlink()

    publisher(run, dest).sync()

    assert not clip.exists()
    assert [c["step"] for c in read(dest, f"runs/{run.dir.name}/live.json")["clips"]] == [1]


def test_old_clips_leave_the_bucket_but_stay_at_home(run, dest):
    for _ in range(3):
        run.kept_step(60)
    publisher(run, dest, keep_minutes=2.5 / 60).sync()  # 150 frames: the newest two steps

    clips = dest.root / "runs" / run.dir.name / "clips"
    assert sorted(p.name for p in clips.iterdir()) == ["step00002.mp4", "step00003.mp4"]
    assert [c["step"] for c in read(dest, f"runs/{run.dir.name}/live.json")["clips"]] == [2, 3]
    assert (run.dir / "clips" / "step00001.mp4").exists()


def test_steps_that_only_look_have_no_clip(run, dest):
    run.step += 1
    run.append("steps.jsonl", {"step": run.step, "kept": True, "frames": 0})
    (run.dir / "states" / f"step{run.step:05d}.state").write_bytes(run.state)
    run.kept_step(20)
    publisher(run, dest).sync()
    assert [c["step"] for c in read(dest, f"runs/{run.dir.name}/live.json")["clips"]] == [2]


def _obs(map_number=1, x=3, hp=20, grid=True):
    return {"map": {"group": 24, "number": map_number, "name": f"Map {map_number}"},
            "player": {"x": x, "y": 4, "facing": "left", "walking": False},
            "trainer": {"name": "SILVER", "rival": "???"}, "money": 3000, "badges": 0,
            "dex": {"caught": 1, "seen": 2}, "battle": None, "text": [],
            "party": [{"species": "Cyndaquil", "dex": 155, "nickname": "CYNDAQUIL",
                       "level": 6, "hp": hp, "max_hp": 21, "status": "", "moves": []}],
            "grid": {"left": 0, "top": 0, "rows": []} if grid else None}


def test_clips_carry_the_game_state_only_where_it_changes(run, dest):
    run.kept_step(20, _obs(x=3))
    run.kept_step(20, _obs(x=4))  # walked: same state, new position
    run.kept_step(20, _obs(x=4, hp=12))  # hurt
    publisher(run, dest).sync()

    clips = read(dest, f"runs/{run.dir.name}/live.json")["clips"]
    assert [c["pos"] for c in clips] == [{"map": "24-1", "x": x, "y": 4, "facing": "left"}
                                          for x in (3, 4, 4)]
    assert clips[0]["state"]["trainer"] == {"name": "SILVER", "rival": "???"}
    assert clips[0]["state"]["map_name"] == "Map 1"
    assert "state" not in clips[1]
    assert clips[2]["state"]["party"][0]["hp"] == 12
    assert "grid" not in clips[0]["state"] and "text" not in clips[0]["state"]


def test_the_oldest_listed_clip_always_has_the_state(run, dest):
    for _ in range(3):
        run.kept_step(60, _obs())
    publisher(run, dest, keep_minutes=2.5 / 60).sync()  # the first clip leaves the bucket

    clips = read(dest, f"runs/{run.dir.name}/live.json")["clips"]
    assert [c["step"] for c in clips] == [2, 3]
    assert clips[0]["state"]["party"][0]["species"] == "Cyndaquil"


def test_steps_without_an_observation_have_no_state(run, dest):
    run.kept_step(20)
    publisher(run, dest).sync()
    clip = read(dest, f"runs/{run.dir.name}/live.json")["clips"][0]
    assert clip["pos"] is None and clip["state"] is None


def test_each_map_is_published_once_when_it_can_be_read(run, dest):
    calls = []

    def layout(pyboy):
        calls.append(1)
        return None if len(calls) == 1 else {"width": 2, "height": 1, "rows": [".."]}

    run.kept_step(20, _obs(map_number=1, grid=False))  # in a battle: not tried
    run.kept_step(20, _obs(map_number=1))  # tried, but the buffer isn't the map yet
    run.kept_step(20, _obs(map_number=1))
    run.kept_step(20, _obs(map_number=1))  # already there
    run.kept_step(20, _obs(map_number=2))
    publisher(run, dest, map_layout=layout).sync()

    maps = dest.root / "runs" / run.dir.name / "maps"
    assert sorted(p.name for p in maps.iterdir()) == ["24-1.json", "24-2.json"]
    assert read(dest, f"runs/{run.dir.name}/maps/24-1.json")["rows"] == [".."]
    assert len(calls) == 3


def test_notes_and_scripts_are_published_with_versions(run, dest):
    (run.dir / "notes.md").write_text("In the bedroom.\n")
    run.library.write("mash", 'def mash(game):\n    """Press A."""\n    game.tap("a")\n',
                      "Text boxes need A")
    pub = publisher(run, dest)
    pub.sync()

    prefix = f"runs/{run.dir.name}"
    live, notes, scripts = (read(dest, f"{prefix}/{n}.json") for n in ("live", "notes", "scripts"))
    assert notes["notes"] == "In the bedroom."
    assert live["notes_version"] == notes["version"]
    assert live["scripts_version"] == scripts["version"]
    mash = next(s for s in scripts["scripts"] if s["name"] == "mash")
    assert mash["reason"] == "Text boxes need A" and "game.tap" in mash["code"]
    assert live["script_uses"] == {}

    for _ in range(2):
        run.append("script_usage.jsonl", {"script": "mash", "version": "v", "ok": True,
                                          "frames": 10, "kind": "script"})
    run.append("script_usage.jsonl", {"script": "helper", "version": "v", "ok": True,
                                      "frames": 0, "kind": "subagent"})

    (run.dir / "notes.md").write_text("Downstairs now.\n")
    pub.sync()
    live = read(dest, f"{prefix}/live.json")
    assert live["notes_version"] != notes["version"]
    assert live["script_uses"] == {"mash": 2}


def test_long_tool_output_is_trimmed(run, dest):
    run.append("agents.jsonl", {"time": 1.0, "agent": "main", "kind": "tool", "tool": "x",
                                "args": {}, "result": "y" * 5000, "step": 0})
    publisher(run, dest).sync()
    result = read(dest, f"runs/{run.dir.name}/live.json")["activity"][-1]["result"]
    assert len(result) < 700 and result.endswith("more]")


def test_a_run_is_not_live_once_ended_or_silent(run, dest):
    pub = publisher(run, dest)
    assert pub.live()
    old = time.time() - 3600
    os.utime(run.dir / "manifest.json", (old, old))
    assert not pub.live()
    run.manifest(ended=True)
    assert not pub.live()
    pub.sync()
    assert read(dest, "current.json")["live"] is False


def test_publishing_a_run_carries_its_end_even_when_it_ends_mid_sync(
        tmp_path, test_rom, test_start, monkeypatch):
    from dataclasses import replace

    from gb_agent.games import GAMES

    monkeypatch.setenv("GB_AGENT_DIR", str(tmp_path / "gb_agent"))
    rom = tmp_path / "test.gb"
    rom.write_bytes(test_rom)  # main() loads the run's ROM through its game profile
    monkeypatch.setitem(GAMES, "silver", replace(GAMES["silver"], rom=rom))
    run = FakeRun(tmp_path / "gb_agent" / "runs", test_rom, test_start)
    sync = RunPublisher.sync

    def sync_then_end(self):  # the run writes its end just after a sync read the manifest
        changed = sync(self)
        run.manifest(ended=True)
        return changed

    monkeypatch.setattr(RunPublisher, "sync", sync_then_end)
    bucket = tmp_path / "bucket"
    assert main(["--run", run.dir.name, "--dest", str(bucket), "--interval", "0"]) == 0
    live = read(LocalDestination(bucket), f"runs/{run.dir.name}/live.json")
    assert live["live"] is False and live["stop_reason"] == "frame_budget"


def test_latest_run_is_the_newest_with_a_manifest(tmp_path):
    root = tmp_path / "runs"
    for name in ("20261020-000000-a", "20261022-000000-b"):
        (root / name).mkdir(parents=True)
        (root / name / "manifest.json").write_text("{}")
    (root / "20261023-000000-starting").mkdir()
    assert latest_run(root).name == "20261022-000000-b"
