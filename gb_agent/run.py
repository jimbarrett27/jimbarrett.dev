"""One run of an experiment: its directory, budget, and every step taken.

An ``ExperimentConfig`` names a game, a model and a goal, with a frame budget and
limits on LLM calls, tokens and time. A ``Run`` carries it out and records it:

    <runs root>/<run id>/
      manifest.json      config, profiles, start/end, why it ended, final frame
      events.jsonl       every input and frame tick, tagged with step/agent/script/version
      steps.jsonl        every step: what ran, kept or not, frames, the trace text
      progress.jsonl     the game profile's progress values after every kept step
      agents.jsonl       every LLM call and tool result
      blockers.jsonl     report_blocker calls
      frames/            screenshots per step
      states/            start state, then the state after each kept step
      library/           the run's script library and snippets (its own git repo)
      script_usage.jsonl
      run.mp4            if rendered

Every step that ran and verified is kept and spends the frame budget; there are no
test runs. A step whose record didn't verify is never kept. The agent's one-off
code is committed to the library's ``snippets/`` before it runs, so the library
holds every piece of code the agent ran.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from gb_agent.blockers import BlockerReporter, telegram
from gb_agent.emulator import boot, save_state
from gb_agent.games import GAMES, GameProfile
from gb_agent.library import Library
from gb_agent.models import get_profile
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


def new_run_id(config: ExperimentConfig) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{config.game}-{config.model}"


def _jsonl(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


class Run:
    def __init__(self, config: ExperimentConfig, *, root: Path | None = None,
                 run_id: str | None = None, game: GameProfile | None = None,
                 image: str | None = None, notify=None):
        self.config = config
        self.game = game or GAMES[config.game]
        self.model = get_profile(config.model)
        self.id = run_id or new_run_id(config)
        self.dir = Path(root or gb_agent_path("runs")) / self.id
        self.image = image
        self.dir.mkdir(parents=True, exist_ok=False)
        for sub in ("frames", "states"):
            (self.dir / sub).mkdir()

        self.library = Library.create(self.dir / "library", self.game.seed_library,
                                      usage_path=self.dir / "script_usage.jsonl", run=self.id)
        self.blockers = BlockerReporter(
            self.dir / "blockers.jsonl", self.id,
            notify=(notify or telegram) if config.notify else None,
        )
        self.rom = self.game.rom_bytes()
        self.state = self.game.load_start_state()
        (self.dir / "states" / "start.state").write_bytes(self.state)
        self.frame = 0
        self.step = 0
        self.kept_steps = 0
        self.watch: dict[str, tuple[int, int, int | None]] = {}
        self.notes = ""  # the main agent's own notes (update_notes), kept across compactions
        self.llm_calls = 0
        self.tokens = 0
        self.started = time.monotonic()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.stop_reason: str | None = None
        self._log_progress()
        self.save_manifest()

    # -- budget -------------------------------------------------------------

    @property
    def frames_left(self) -> int:
        return max(0, self.config.frame_budget - self.frame)

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
            image=self.image)
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
                                  limits=self._limits(max_frames), image=self.image)
        if title:
            trace.title = title
        self._finish_step(outcome, trace, agent=agent, version=version, code=code)
        return trace

    def _finish_step(self, outcome: StepOutcome, trace: Trace, *, agent: str,
                     script: str | None = None, version: str | None = None,
                     args: dict | None = None, code: str | None = None) -> None:
        kept = outcome.usable
        step = self.step
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
            self._log_progress()

        logger.info("step %d %s: %s, frames %d→%d, %s", step, trace.title, outcome.sandbox.status,
                    outcome.start_frame, outcome.end_frame, "kept" if kept else "not kept")
        _jsonl(self.dir / "steps.jsonl", {
            "step": step, "agent": agent, "kept": kept,
            "script": script, "version": version, "args": args, "code": code,
            "status": outcome.sandbox.status, "verified": outcome.verified,
            "start_frame": outcome.start_frame, "end_frame": outcome.end_frame,
            "frames": outcome.frames_used, "problem": outcome.problem,
            "trace": trace.to_text(budget=20_000), "time": time.time(),
        })

    # -- looking without advancing ------------------------------------------

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

    def _log_progress(self) -> None:
        if not self.game.progress_values:
            return
        pyboy = boot(self.rom, self.state)
        try:
            values = {}
            for label, ref in self.game.progress_values.items():
                read = (lambda a: pyboy.memory[a]) if ref.bank is None \
                    else (lambda a, b=ref.bank: pyboy.memory[b, a])
                bytes_ = [read(a) for a in range(ref.addr, ref.addr + ref.length)]
                values[label] = bytes_[0] if ref.length == 1 else bytes_
        finally:
            pyboy.stop(save=False)
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
