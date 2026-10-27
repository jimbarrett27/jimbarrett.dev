"""Publish a run as it happens, for the live page on jimbarrett.dev.

``python -m gb_agent.publish`` follows the newest run (or ``--run <id>``) and pushes
what a viewer needs to a public GCS bucket, which the site polls. It only reads the
run directory, whose files are all appended to or rewritten whole, so it runs as its
own process: a publisher crash can't hurt a run, and old runs can be republished.

The bucket layout is the website's contract (``gb-agent.interface.ts``):

    current.json                    {run, live}: which run the page shows
    runs/<run>/live.json            status, the newest clips, recent activity and
                                    how often each script has run; small,
                                    rewritten whenever something changes
    runs/<run>/notes.json           {version, notes}
    runs/<run>/scripts.json         {version, scripts, subagents}
    runs/<run>/clips/stepNNNNN.mp4  one clip per kept step, at game speed; immutable
    runs/<run>/maps/<group>-<number>.json
                                    the whole of each map the run has been on, for
                                    the page's mini-map

``live.json`` carries ``notes_version`` and ``scripts_version`` so the page only
refetches those two when they change. Each clip in it has the game state at the end
of its step, read from the step's observation: ``pos`` (map and tile) on every clip,
and ``state`` (trainer, party, money, badges, Pokedex) only where it differs from the
clip before, and always on the first, so walking about doesn't repeat the party.

Only the newest ``--keep-minutes`` of game time stays in the bucket; every clip is
also kept in ``<run>/clips/`` at home, so the run directory remains the full record.
Tool results go out as the agent saw them, so the game-state description (map,
position, party) is public too; save states, events and the ROM never are.
"""

import argparse
import hashlib
import json
import logging
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from gb_agent.emulator import boot
from gb_agent.games import GAMES
from gb_agent.library import Library
from gb_agent.replay import FPS, render_video
from gb_agent.paths import gb_agent_path

logger = logging.getLogger(__name__)

PROJECT_ID = "personal-website-318015"
BUCKET_NAME = "personal-website-318015-gb-agent"

CLIP_SCALE = 2  # 320x288: with 4:2:0 chroma, every Game Boy pixel keeps its own colour
LIVE_CLIPS = 50  # clips listed in live.json
ACTIVITY = 10  # agent records listed in live.json
TEXT_CAP = 5_000  # characters of model text kept per record (a 1,024-token thought fits)
RESULT_CAP = 600  # characters of a tool's args or result kept per record
LIVE_AFTER = 10 * 60  # seconds without a manifest write before a run counts as stopped
EVENT_KEYS = ("frame", "type", "frames", "button")  # as Run.events() keeps them

NO_CACHE = "no-cache"
IMMUTABLE = "public, max-age=31536000, immutable"


class Destination(Protocol):
    name: str  # where it publishes to; the run keeps a record per destination

    def put(self, key: str, data: bytes, content_type: str, cache_control: str) -> None: ...
    def delete(self, key: str) -> None: ...


class LocalDestination:
    """A folder laid out like the bucket: for tests, and for working on the page."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.name = str(self.root.resolve())

    def put(self, key: str, data: bytes, content_type: str, cache_control: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


class GCSDestination:
    def __init__(self, bucket: str = BUCKET_NAME):
        from google.cloud import storage

        self.bucket = storage.Client(project=PROJECT_ID).bucket(bucket)
        self.name = f"gs://{bucket}"

    def put(self, key: str, data: bytes, content_type: str, cache_control: str) -> None:
        blob = self.bucket.blob(key)
        blob.cache_control = cache_control
        blob.upload_from_string(data, content_type=content_type)

    def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self.bucket.blob(key).delete()
        except NotFound:
            pass


class _Tail:
    """New complete lines of a JSONL file that's being appended to."""

    def __init__(self, path: Path):
        self.path = path
        self.offset = 0

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("rb") as f:
            f.seek(self.offset)
            chunk = f.read()
        end = chunk.rfind(b"\n") + 1  # leave a half-written last line for next time
        self.offset += end
        return [json.loads(line) for line in chunk[:end].splitlines() if line.strip()]


def _cap(text, limit: int) -> str | None:
    if text is None:
        return None
    text = text if isinstance(text, str) else json.dumps(text, default=str)
    return text if len(text) <= limit else text[:limit] + f"… [{len(text) - limit} more]"


def _activity(record: dict) -> dict | None:
    """A trimmed agents.jsonl record for the page, or None if it's not shown."""
    base = {"time": record.get("time"), "agent": record.get("agent"),
            "kind": record.get("kind"), "step": record.get("step")}
    kind = record.get("kind")
    if kind == "llm":
        return {**base, "text": _cap(record.get("text") or None, TEXT_CAP),
                "reasoning": _cap(record.get("reasoning") or None, TEXT_CAP),
                "tool_calls": [{"name": c.get("name"), "args": _cap(c.get("args"), RESULT_CAP)}
                               for c in record.get("tool_calls") or []]}
    if kind == "tool":
        return {**base, "tool": record.get("tool"), "args": _cap(record.get("args"), RESULT_CAP),
                "result": _cap(record.get("result"), RESULT_CAP)}
    if kind == "compaction":
        return base
    return None


def _pos(obs: dict | None) -> dict | None:
    """Where the player is, for the mini-map."""
    if not obs or "map" not in obs:
        return None
    player = obs.get("player") or {}
    return {"map": f"{obs['map']['group']}-{obs['map']['number']}", "x": player.get("x"),
            "y": player.get("y"), "facing": player.get("facing")}


def _game_state(obs: dict | None) -> dict | None:
    """The part of an observation the page shows next to the video."""
    if not obs:
        return None
    return {"map_name": (obs.get("map") or {}).get("name"), "trainer": obs.get("trainer"),
            "party": obs.get("party"), "money": obs.get("money"), "badges": obs.get("badges"),
            "dex": obs.get("dex")}


def _listed(clips: list[dict]) -> list[dict]:
    """Clips for live.json, each ``state`` dropped where it repeats the one before."""
    listed, shown = [], None
    for clip in clips:
        state = clip.get("state")
        if state is not None and state == shown:
            clip = {k: v for k, v in clip.items() if k != "state"}
        shown = state if state is not None else shown
        listed.append(clip)
    return listed


def _version(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _json(data) -> bytes:
    return json.dumps(data, separators=(",", ":"), default=str).encode()


class RunPublisher:
    """Keeps one run's files in ``dest`` up to date; call ``sync()`` repeatedly."""

    def __init__(self, run_dir: Path, dest: Destination, *, keep_minutes: float = 240,
                 rom: bytes | None = None, map_layout=None):
        self.dir = Path(run_dir)
        self.id = self.dir.name
        self.dest = dest
        self.keep_frames = int(keep_minutes * 60 * FPS)
        self.prefix = f"runs/{self.id}"
        manifest = self._manifest()
        game = GAMES[manifest["config"]["game"]]
        self.rom = rom if rom is not None else game.rom_bytes()
        self.map_layout = map_layout or game.map_layout
        self.library = Library(self.dir / "library")
        (self.dir / "clips").mkdir(exist_ok=True)

        self._steps = _Tail(self.dir / "steps.jsonl")
        self._events = _Tail(self.dir / "events.jsonl")
        self._agents = _Tail(self.dir / "agents.jsonl")
        self._usage = _Tail(self.dir / "script_usage.jsonl")
        self.script_uses: Counter[str] = Counter()
        self._todo: deque[dict] = deque()  # kept steps read but not published yet
        self._pending: dict[int, list[dict]] = {}  # events of steps not rendered yet
        self._state = self.dir / "states" / "start.state"  # start of the next kept step
        self.clips: list[dict] = []  # every kept step's clip, oldest first
        self.activity: deque[dict] = deque(maxlen=ACTIVITY)
        self.waiting_since: float | None = None

        self._record_path = self.dir / "published.json"
        self._records = (json.loads(self._record_path.read_text())
                         if self._record_path.exists() else {})
        record = self._records.get(dest.name, {})
        self._uploaded: set[int] = set(record.get("uploaded", []))
        self._deleted: set[int] = set(record.get("deleted", []))
        self._sent: dict[str, str] = {}  # key -> version of the last upload this session
        self._scripts_version: str | None = None
        self._maps: set[str] = set()  # maps uploaded this session

    # -- reading the run ----------------------------------------------------

    def _manifest(self) -> dict:
        return json.loads((self.dir / "manifest.json").read_text())

    def _read_steps(self) -> None:
        self._todo.extend(s for s in self._steps.read() if s.get("kept"))
        # A kept step's events are written before its steps.jsonl line, so reading
        # events second always covers every step just read.
        for event in self._events.read():
            self._pending.setdefault(event["step"], []).append(
                {k: v for k, v in event.items() if k in EVENT_KEYS and v is not None})

    def _clip_key(self, step: int) -> str:
        return f"{self.prefix}/clips/step{step:05d}.mp4"

    def _add_clip(self, step: dict) -> bool:
        """Render (if needed) and upload one kept step's clip; True if uploaded.

        Safe to call again for the same step after a failure: nothing is
        consumed until the upload has gone through.
        """
        n = step["step"]
        if not step.get("frames"):  # a step that only looked (read memory, say): nothing to watch
            self._pending.pop(n, None)
            self._state = self.dir / "states" / f"step{n:05d}.state"
            return False
        local = self.dir / "clips" / f"step{n:05d}.mp4"
        if not local.exists():
            tmp = local.with_suffix(".tmp.mp4")
            render_video(self.rom, self._state.read_bytes(), self._pending.get(n, []), tmp,
                         scale=CLIP_SCALE)
            tmp.rename(local)
        uploaded = n not in self._uploaded and n not in self._deleted
        if uploaded:
            self.dest.put(self._clip_key(n), local.read_bytes(), "video/mp4", IMMUTABLE)
            self._uploaded.add(n)
        self._pending.pop(n, None)
        self._state = self.dir / "states" / f"step{n:05d}.state"
        obs = step.get("observation")
        self.clips.append({"step": n, "key": self._clip_key(n), "frames": step.get("frames"),
                           "start_frame": step.get("start_frame"), "agent": step.get("agent"),
                           "script": step.get("script"),
                           "args": _cap(step.get("args"), RESULT_CAP) if step.get("args") else None,
                           "time": step.get("time"), "pos": _pos(obs), "state": _game_state(obs)})
        self._add_map(obs, self._state)
        return uploaded

    def _add_map(self, obs: dict | None, state: Path) -> None:
        """Upload the layout of the map a step ended on, the first time it's seen.

        The observation's grid says whether the map buffer held the map (it doesn't
        in a battle); if it didn't, the map waits for a later step.
        """
        pos = _pos(obs)
        if self.map_layout is None or pos is None or pos["map"] in self._maps \
                or obs.get("grid") is None:
            return
        try:
            pyboy = boot(self.rom, state.read_bytes())
            try:
                layout = self.map_layout(pyboy)
            finally:
                pyboy.stop(save=False)
        except Exception:
            logger.exception("couldn't read map %s", pos["map"])
            return
        if layout is None:
            return
        self.dest.put(f"{self.prefix}/maps/{pos['map']}.json", _json(layout),
                      "application/json", NO_CACHE)
        self._maps.add(pos["map"])

    def _prune(self) -> None:
        """Delete clips that fall outside the newest ``keep_frames`` of game time."""
        total = 0
        for clip in reversed(self.clips):
            total += clip["frames"] or 0
            n = clip["step"]
            if total > self.keep_frames and n in self._uploaded:
                self.dest.delete(clip["key"])
                self._uploaded.discard(n)
                self._deleted.add(n)

    def _scripts(self) -> dict:
        scripts = []
        for info in self.library.scripts():
            history = self.library.history(info.name)
            scripts.append({"name": info.name, "version": info.version,
                            "signature": info.signature, "summary": info.summary,
                            "code": self.library.read(info.name),
                            "changes": len(history),
                            "reason": history[0].reason if history else None,
                            "changed_at": history[0].date if history else None})
        subagents = [{k: spec.get(k) for k in
                      ("name", "version", "instructions", "tools", "scripts", "model")}
                     for spec in self.library.subagents()]
        return {"scripts": scripts, "subagents": subagents}

    # -- publishing ---------------------------------------------------------

    def _put_json(self, key: str, data: dict, version: str) -> bool:
        if self._sent.get(key) == version:
            return False
        self.dest.put(key, _json(data), "application/json", NO_CACHE)
        self._sent[key] = version
        return True

    def live(self, manifest: dict | None = None) -> bool:
        """Is the run still going? Not ended, and its manifest written recently."""
        manifest = manifest or self._manifest()
        age = time.time() - (self.dir / "manifest.json").stat().st_mtime
        return manifest.get("ended_at") is None and age < LIVE_AFTER

    def sync(self) -> bool:
        """Publish anything new; True if something was uploaded."""
        changed = False
        self._read_steps()
        while self._todo:
            changed |= self._add_clip(self._todo[0])
            self._todo.popleft()
        if changed:
            self._prune()
            self._records[self.dest.name] = {"uploaded": sorted(self._uploaded),
                                             "deleted": sorted(self._deleted)}
            self._record_path.write_text(json.dumps(self._records))

        for record in self._agents.read():
            self.waiting_since = record.get("time", self.waiting_since)
            if shown := _activity(record):
                self.activity.append(shown)

        for use in self._usage.read():
            if use.get("kind", "script") == "script":
                self.script_uses[use["script"]] += 1

        notes_path = self.dir / "notes.md"
        notes = notes_path.read_text().strip() if notes_path.exists() else ""
        notes_version = _version(notes)
        changed |= self._put_json(f"{self.prefix}/notes.json",
                                  {"version": notes_version, "notes": notes}, notes_version)

        head = self.library._git("rev-parse", "HEAD").stdout.strip()
        if self._sent.get("library") != head:
            scripts = self._scripts()
            scripts_version = _version(scripts)
            changed |= self._put_json(f"{self.prefix}/scripts.json",
                                      {"version": scripts_version, **scripts}, scripts_version)
            self._sent["library"] = head
            self._scripts_version = scripts_version

        manifest = self._manifest()
        live = self.live(manifest)
        published = [c for c in self.clips if c["step"] in self._uploaded][-LIVE_CLIPS:]
        status = {
            "run": self.id, "game": manifest["config"]["game"],
            "model": manifest["config"]["model"], "goal": manifest["config"].get("goal"),
            "live": live, "started_at": manifest.get("started_at"),
            "ended_at": manifest.get("ended_at"), "stop_reason": manifest.get("stop_reason"),
            "frame": manifest.get("frame"), "frame_budget": manifest["config"].get("frame_budget"),
            "steps": manifest.get("steps"), "kept_steps": manifest.get("kept_steps"),
            "llm_calls": manifest.get("llm_calls"), "minutes": manifest.get("minutes"),
            "fps": FPS, "clips": _listed(published),
            "activity": list(self.activity), "waiting_since": self.waiting_since,
            "script_uses": dict(self.script_uses),
            "notes_version": notes_version, "scripts_version": self._scripts_version,
        }
        version = _version(status)
        updated_at = datetime.fromtimestamp(
            (self.dir / "manifest.json").stat().st_mtime, timezone.utc).isoformat()
        changed |= self._put_json(f"{self.prefix}/live.json", {**status, "updated_at": updated_at},
                                  version)
        # Only rewritten when the run or its liveness changes; the page also checks
        # live.json's updated_at, in case this publisher stops while a run is live.
        changed |= self._put_json("current.json", {"run": self.id, "live": live},
                                  _version(self.id, live))
        return changed


def latest_run(root: Path) -> Path | None:
    """The newest run directory (run ids start with a UTC timestamp)."""
    runs = sorted(p for p in root.iterdir() if (p / "manifest.json").exists()) \
        if root.exists() else []
    return runs[-1] if runs else None


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m gb_agent.publish", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", default="latest",
                   help="a run id, or 'latest' to follow the newest run as new ones start")
    p.add_argument("--dest", default=f"gs://{BUCKET_NAME}",
                   help="gs://<bucket>, or a local folder laid out like the bucket")
    p.add_argument("--keep-minutes", type=float, default=240,
                   help="minutes of game time to keep in the bucket")
    p.add_argument("--interval", type=float, default=2, help="seconds between checks")
    p.add_argument("--once", action="store_true", help="publish what's there now, then stop")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dest = (GCSDestination(args.dest.removeprefix("gs://")) if args.dest.startswith("gs://")
            else LocalDestination(Path(args.dest)))
    root = Path(gb_agent_path("runs"))
    follow = args.run == "latest"
    publisher: RunPublisher | None = None
    try:
        while True:
            run_dir = latest_run(root) if follow else root / args.run
            if run_dir is not None and (publisher is None or publisher.dir != run_dir):
                if publisher is not None:
                    publisher.sync()  # the old run's last state
                logger.info("publishing %s", run_dir.name)
                publisher = RunPublisher(run_dir, dest, keep_minutes=args.keep_minutes)
            if publisher is not None:
                # Checked before syncing, so the sync below always carries the end
                # state: checking after could see an end the sync just missed.
                ended = not follow and not publisher.live()
                try:
                    if publisher.sync():
                        logger.info("published %s: %d clips", publisher.id, len(publisher.clips))
                except Exception:  # keep following; the next pass retries from the same place
                    logger.exception("publishing %s failed", publisher.id)
                if args.once or ended:
                    return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
