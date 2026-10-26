"""One run of an experiment: its directory, budget, and every step taken.

An ``ExperimentConfig`` names a game, a model and a goal, with a frame budget and
limits on LLM calls, tokens and time. A ``Run`` carries it out and records it:

    <runs root>/<run id>/
      manifest.json      config, profiles, start/end, why it ended, final frame
      events.jsonl       every input and frame tick, tagged with step/agent/script/version
      steps.jsonl        every step: what ran, kept or not, frames, the trace text
      progress.jsonl     the game profile's progress values after every kept step
                         (steps.jsonl also has the game's described state, if it has one)
      agents.jsonl       every LLM call and tool result
      blockers.jsonl     report_blocker calls
      frames/            screenshots per step
      states/            start state, then the state after each kept step
      library/           the run's script library and snippets (its own git repo)
      script_usage.jsonl
      run.mp4            if rendered

A run can also pick up where an earlier one stopped (``ResumePoint``): it starts
from one of that run's kept steps, with its notes and library as they were then,
and carries on its frame and step numbers. It's still a new run directory; its
manifest names the run it came from, and its video starts at the resumed step.

Every step that ran and verified is kept and spends the frame budget; there are no
test runs. A step whose record didn't verify is never kept. The agent's one-off
code is committed to the library's ``snippets/`` before it runs, so the library
holds every piece of code the agent ran.
"""

import json
import logging
import re
import shutil
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from gb_agent.blockers import BlockerReporter, telegram
from gb_agent.emulator import boot, save_state
from gb_agent.games import GAMES, GameProfile
from gb_agent.library import Library
from gb_agent.models import get_profile
from gb_agent.notes import clean_notes
from gb_agent.scripts import run_code, run_script
from gb_agent.steps import StepLimits, StepOutcome, validate_watch
from gb_agent.trace import Trace
from gb_agent.paths import gb_agent_path

logger = logging.getLogger(__name__)


STEP_FRAMES = 600


@dataclass(frozen=True)
class ExperimentConfig:
    game: str
    model: str
    goal: str
    frame_budget: int = 10_000
    max_llm_calls: int = 300
    max_tokens: int = 5_000_000
    max_minutes: float = 240
    # 600 frames (10 s of game time) per kept step: one blind loop shouldn't be able
    # to spend a big share of the budget (Gemma's loops spent up to 1,400).
    step: StepLimits = field(default_factory=lambda: StepLimits(max_frames=STEP_FRAMES))
    notify: bool = True
    allow_paid: bool = False  # may sub-agents use paid (OpenRouter) models?
    # Describe the game state at the top of every report, if the game profile can.
    state_report: bool = True


def new_run_id(config: ExperimentConfig) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{config.game}-{config.model}"


def _jsonl(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


@dataclass(frozen=True)
class ResumePoint:
    """A kept step of an earlier run, to start a new run from.

    The notes and library come with what the agent did after the step and before the
    next one: it was looking at the step's state when it did that.
    """
    run_dir: Path
    step: int
    frame: int
    notes: str
    journal: dict | None  # the harness's journal as of the step, if the run kept one

    @classmethod
    def find(cls, run_dir: Path, step: int | None = None) -> "ResumePoint":
        """Kept step ``step`` of the run at ``run_dir``, or its last kept step."""
        run_dir = Path(run_dir)
        kept, journals = {}, {}
        for line in (run_dir / "steps.jsonl").read_text().splitlines():
            record = json.loads(line)
            if record["kept"]:
                kept[record["step"]] = record["end_frame"]
                journals[record["step"]] = record.get("journal")
        if not kept:
            raise ValueError(f"{run_dir.name} has no kept steps to resume from")
        step = max(kept) if step is None else step
        if step not in kept:
            near = sorted(kept, key=lambda s: abs(s - step))[:3]
            raise ValueError(f"step {step} of {run_dir.name} wasn't kept; nearest kept: "
                             + ", ".join(map(str, sorted(near))))
        notes = ""
        agents = run_dir / "agents.jsonl"
        for line in agents.read_text().splitlines() if agents.exists() else []:
            record = json.loads(line)
            if record.get("kind") == "notes" and record.get("agent", "main") == "main" \
                    and record.get("step", 0) <= step:
                notes = record["notes"]
        return cls(run_dir, step, kept[step], clean_notes(notes), journals[step])

    @property
    def state(self) -> bytes:
        return (self.run_dir / "states" / f"step{self.step:05d}.state").read_bytes()


def rebuild_journal(run_dir: Path, step: int, remember) -> dict:
    """The journal as of ``step``, folded from the run's kept steps (and those of any
    run it was resumed from), for runs from before steps.jsonl kept it. Their text is
    only what the reports showed ("Text during this step"), so it's rougher."""
    run_dir = Path(run_dir)
    journal: dict = {}
    before = None
    manifest = run_dir / "manifest.json"
    parent = json.loads(manifest.read_text()).get("resumed_from") if manifest.exists() else None
    if parent:
        journal = rebuild_journal(run_dir.parent / parent["run"], parent["step"], remember)
    for line in (run_dir / "steps.jsonl").read_text().splitlines():
        record = json.loads(line)
        if record["step"] > step:
            break
        if not record["kept"] or not record.get("observation"):
            continue
        text = record.get("text")
        if text is None:
            shown = re.search(r"^Text during this step: (.*)$", record["trace"], re.M)
            text = [shown.group(1)] if shown else []
        remember(journal, before, record["observation"], text)
        before = record["observation"]
    return journal


def _resume_library(point: ResumePoint, root: Path, usage_path: Path, run: str) -> Library:
    """A copy of the earlier run's library, with its files as they were at the step."""
    shutil.copytree(point.run_dir / "library", root)
    library = Library(root, usage_path)
    log = library._git("log", "--format=%H %(trailers:key=Step,valueonly,separator=)").stdout
    later = [line.split() for line in log.splitlines()]
    # Newest first: skip the commits made after the step; the next one is the target.
    target = next(c[0] for c in later if len(c) == 1 or int(c[1]) <= point.step)
    library._git("read-tree", "-u", "--reset", target)
    library._commit(f"Resume from {point.run_dir.name} at step {point.step}\n\nRun: {run}")
    # Usage stats: the earlier run's script runs up to the step (one per script step).
    scripts_run = sum(1 for line in (point.run_dir / "steps.jsonl").read_text().splitlines()
                      if (r := json.loads(line))["step"] <= point.step and r["script"])
    old = point.run_dir / "script_usage.jsonl"
    entries = old.read_text().splitlines() if old.exists() else []
    kept = [e for e in entries if json.loads(e).get("kind", "script") == "script"][:scripts_run]
    usage_path.write_text("".join(e + "\n" for e in kept))
    return library


class Run:
    def __init__(self, config: ExperimentConfig, *, root: Path | None = None,
                 run_id: str | None = None, game: GameProfile | None = None,
                 image: str | None = None, notify=None, resume: ResumePoint | None = None):
        self.config = config
        self.game = game or GAMES[config.game]
        self.model = get_profile(config.model)
        self.id = run_id or new_run_id(config)
        self.dir = Path(root or gb_agent_path("runs")) / self.id
        self.image = image
        self.dir.mkdir(parents=True, exist_ok=False)
        for sub in ("frames", "states"):
            (self.dir / sub).mkdir()

        self.resumed_from = resume
        if resume is None:
            self.library = Library.create(self.dir / "library", self.game.seed_library,
                                          usage_path=self.dir / "script_usage.jsonl",
                                          run=self.id)
        else:
            self.library = _resume_library(resume, self.dir / "library",
                                           self.dir / "script_usage.jsonl", self.id)
        self.blockers = BlockerReporter(
            self.dir / "blockers.jsonl", self.id,
            notify=(notify or telegram) if config.notify else None,
        )
        self.rom = self.game.rom_bytes()
        self.state = self.game.load_start_state() if resume is None else resume.state
        (self.dir / "states" / "start.state").write_bytes(self.state)
        self.frame = 0 if resume is None else resume.frame
        self.start_frame = self.frame  # the budget counts this run's frames only
        self.step = 0 if resume is None else resume.step
        self.kept_steps = 0
        self.watch: dict[str, tuple[int, int, int | None]] = {}
        self.notes = ""  # the main agent's own notes (update_notes), kept across compactions
        self.journal: dict = {}  # the harness's own record for the agent (GameProfile.remember)
        if resume is not None and self.game.remember is not None:
            self.journal = resume.journal if resume.journal is not None else \
                rebuild_journal(resume.run_dir, resume.step, self.game.remember)
        if resume is not None and resume.notes:
            self.set_notes(resume.notes, agent="main")
        self.llm_calls = 0
        self.tokens = 0
        self.started = time.monotonic()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.stop_reason: str | None = None
        self.observation: dict | None = None  # the game state after the last kept step
        self._after_kept()
        self.save_manifest()

    # -- budget -------------------------------------------------------------

    @property
    def frames_left(self) -> int:
        return max(0, self.config.frame_budget - (self.frame - self.start_frame))

    @property
    def minutes(self) -> float:
        return (time.monotonic() - self.started) / 60

    def limit_reached(self) -> str | None:
        """Which limit has run out, if any."""
        c = self.config
        if self.frames_left == 0:
            return "frame_budget"
        if self.llm_calls >= c.max_llm_calls:
            return "max_llm_calls"
        if self.tokens >= c.max_tokens:
            return "max_tokens"
        if self.minutes >= c.max_minutes:
            return "max_minutes"
        return None

    def budget_line(self) -> str:
        c = self.config
        return (f"[frame {self.frame}; {self.frames_left} of {c.frame_budget} frames left; "
                f"LLM calls {self.llm_calls}/{c.max_llm_calls}]")

    # -- steps --------------------------------------------------------------

    def _limits(self, max_frames: int | None = None) -> StepLimits:
        """Step limits; a step can't pass the budget (or ``max_frames``, if given)."""
        step = self.config.step
        cap = self.frames_left if max_frames is None else min(self.frames_left, max_frames)
        return replace(step, max_frames=min(step.max_frames, cap))

    def run_script(self, name: str, args: dict | None, *, agent: str = "main",
                   max_frames: int | None = None) -> Trace:
        self.step += 1
        outcome, trace, version = run_script(
            self.library, name, args, rom_path=self.game.rom, state=self.state,
            start_frame=self.frame, watch=self.watch, limits=self._limits(max_frames),
            image=self.image, read_text=self._read_text)
        self._finish_step(outcome, trace, agent=agent, script=name, version=version, args=args)
        return trace

    def run_code(self, code: str, *, agent: str = "main", title: str | None = None,
                 max_frames: int | None = None, snippet: bool = False) -> Trace:
        """Run one-off code; ``snippet``: it's the agent's, so keep it in the library."""
        self.step += 1
        version = (self.library.write_snippet(code, step=self.step, agent=agent, run=self.id)
                   if snippet else None)
        outcome, trace = run_code(self.library, code, rom_path=self.game.rom, state=self.state,
                                  start_frame=self.frame, watch=self.watch,
                                  limits=self._limits(max_frames), image=self.image,
                                  read_text=self._read_text)
        if title:
            trace.title = title
        self._finish_step(outcome, trace, agent=agent, version=version, code=code)
        return trace

    def _finish_step(self, outcome: StepOutcome, trace: Trace, *, agent: str,
                     script: str | None = None, version: str | None = None,
                     args: dict | None = None, code: str | None = None) -> None:
        kept = outcome.usable
        step = self.step
        text = outcome.text.lines if outcome.text is not None else []
        if not kept:
            trace.title += " [not kept]"

        for i, (caption, png) in enumerate(trace.images):
            (self.dir / "frames" / f"step{step:05d}-{i}.png").write_bytes(png)

        if kept:
            tags = {"step": step, "agent": agent, "script": script, "version": version}
            with (self.dir / "events.jsonl").open("a") as f:
                for event in outcome.events:
                    f.write(json.dumps({**event, **tags}) + "\n")
            self.state = outcome.state
            self.frame = outcome.end_frame
            self.kept_steps += 1
            (self.dir / "states" / f"step{step:05d}.state").write_bytes(self.state)
            before = self.observation
            self._after_kept()
            if self.reports_state and self.observation is not None:
                pressed = [e["button"] for e in outcome.events if e["type"] == "press"]
                trace.state = self.game.describe(before, self.observation, pressed)
                if self.game.remember is not None:
                    self.game.remember(self.journal, before, self.observation, text)

        logger.info("step %d %s: %s, frames %d→%d, %s", step, trace.title, outcome.sandbox.status,
                    outcome.start_frame, outcome.end_frame, "kept" if kept else "not kept")
        _jsonl(self.dir / "steps.jsonl", {
            "step": step, "agent": agent, "kept": kept,
            "script": script, "version": version, "args": args, "code": code,
            "status": outcome.sandbox.status, "verified": outcome.verified,
            "start_frame": outcome.start_frame, "end_frame": outcome.end_frame,
            "frames": outcome.frames_used, "problem": outcome.problem,
            "observation": self.observation if kept and self.reports_state else None,
            "text": text,
            "journal": self.journal if kept and self.game.remember is not None else None,
            "trace": trace.to_text(budget=20_000), "time": time.time(),
        })

    # -- looking without advancing ------------------------------------------

    @property
    def reports_state(self) -> bool:
        return self.config.state_report and self.game.observe is not None

    @property
    def _read_text(self):
        return self.game.read_text if self.config.state_report else None

    def journal_text(self) -> str:
        """The harness's journal as shown to the agent, or ""."""
        if self.game.recall is None or not self.reports_state:
            return ""
        return self.game.recall(self.journal)

    def state_text(self) -> str:
        """The game's state as the agent sees it at the top of a report, or ""."""
        if not self.reports_state or self.observation is None:
            return ""
        return self.game.describe(None, self.observation, [])

    def screenshot_png(self) -> bytes:
        from gb_agent.emulator import RecordingGame

        pyboy = boot(self.rom, self.state)
        try:
            return RecordingGame(pyboy).screenshot_png()
        finally:
            pyboy.stop(save=False)

    def read_memory(self, addr: int, length: int = 1, bank: int | None = None) -> list[int]:
        if problem := validate_watch({"read": (addr, length, bank)}):
            raise ValueError(problem.replace("watch 'read': ", ""))
        pyboy = boot(self.rom, self.state)
        try:
            if bank is None:
                return [pyboy.memory[a] for a in range(addr, addr + length)]
            return [pyboy.memory[bank, a] for a in range(addr, addr + length)]
        finally:
            pyboy.stop(save=False)

    def set_watch(self, label: str, addr: int, length: int = 1, bank: int | None = None) -> None:
        watch = {**self.watch, label: (addr, length, bank)}
        if problem := validate_watch(watch):
            raise ValueError(problem)
        self.watch = watch

    # -- records ------------------------------------------------------------

    def _after_kept(self) -> None:
        """Read the new state once: progress values for scoring, and the game state
        the agent is told about. A failed observation costs the report, not the run."""
        if not self.game.progress_values and not self.reports_state:
            return
        pyboy = boot(self.rom, self.state)
        try:
            values = {}
            for label, ref in self.game.progress_values.items():
                read = (lambda a: pyboy.memory[a]) if ref.bank is None \
                    else (lambda a, b=ref.bank: pyboy.memory[b, a])
                bytes_ = [read(a) for a in range(ref.addr, ref.addr + ref.length)]
                values[label] = bytes_[0] if ref.length == 1 else bytes_
            if self.reports_state:
                try:
                    self.observation = self.game.observe(pyboy)
                except Exception:
                    logger.exception("step %d: couldn't read the game state", self.step)
                    self.observation = None
        finally:
            pyboy.stop(save=False)
        if values:
            _jsonl(self.dir / "progress.jsonl", {"step": self.step, "frame": self.frame,
                                                 "values": values})

    def set_notes(self, notes: str, agent: str) -> None:
        self.notes = notes
        (self.dir / "notes.md").write_text(notes + "\n")
        self.log_agent({"agent": agent, "kind": "notes", "notes": notes, "step": self.step})

    def log_agent(self, record: dict) -> None:
        _jsonl(self.dir / "agents.jsonl", {"time": time.time(), **record})

    def report_blocker(self, problem: str, tried: str, would_help: str, agent: str) -> str:
        return self.blockers.report(problem, tried, would_help, agent=agent,
                                    step=self.step, frame=self.frame)

    def save_manifest(self) -> None:
        manifest = {
            "run": self.id,
            "config": asdict(self.config),
            "game": {"name": self.game.name, "rom": str(self.game.rom),
                     "setup_inputs": len(self.game.setup)},
            "resumed_from": None if self.resumed_from is None else {
                "run": self.resumed_from.run_dir.name, "step": self.resumed_from.step,
                "frame": self.resumed_from.frame},
            "model": asdict(self.model),
            "started_at": self.started_at,
            "ended_at": datetime.now(timezone.utc).isoformat() if self.stop_reason else None,
            "stop_reason": self.stop_reason,
            "frame": self.frame,
            "steps": self.step,
            "kept_steps": self.kept_steps,
            "llm_calls": self.llm_calls,
            "tokens": self.tokens,
            "minutes": round(self.minutes, 2),
        }
        (self.dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    def finish(self, stop_reason: str, *, video: bool = False) -> None:
        self.stop_reason = stop_reason
        self.save_manifest()
        (self.dir / "states" / "final.state").write_bytes(self.state)
        if video:
            self.render_video()

    def events(self) -> list[dict]:
        path = self.dir / "events.jsonl"
        if not path.exists():
            return []
        keys = ("frame", "type", "frames", "button")
        return [{k: v for k, v in json.loads(line).items() if k in keys and v is not None}
                for line in path.read_text().splitlines()]

    def render_video(self) -> Path:
        from gb_agent.replay import render_video

        out = self.dir / "run.mp4"
        render_video(self.rom, (self.dir / "states" / "start.state").read_bytes(),
                     self.events(), out)
        return out

    def final_state_replays(self) -> bool:
        """Does replaying the whole event log reproduce the run's final state?"""
        pyboy = boot(self.rom, (self.dir / "states" / "start.state").read_bytes())
        try:
            from gb_agent.emulator import apply_events

            apply_events(pyboy, self.events())
            return save_state(pyboy) == self.state
        finally:
            pyboy.stop(save=False)
