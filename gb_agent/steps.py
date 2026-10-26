"""One step: run a script against the game in the sandbox, then check the record.

A step starts from a save state, runs the script in a fresh container with
``game`` (a ``RecordingGame``) in scope, and comes back with the new state and
every input the script made. The host then replays those inputs from the
starting state on its own emulator and compares the result with the state the
sandbox produced. They match unless something changed the game without being
recorded -- a script reaching past ``RecordingGame`` to press buttons or write
memory -- and then the step is marked unverified.

Replaying runs no agent code, only recorded inputs into a trusted ROM, so it's
safe to do on the host. The inputs themselves come out of the sandbox, though,
so they're validated before they're replayed. The replay also reads the game's
text boxes as it goes (``read_text``), so the report can say what was said even
when the conversation is over by the end of the step.
"""

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pyboy import PyBoy

from gb_agent.emulator import BUTTONS, apply_event, apply_events, boot, save_state
from gb_agent.sandbox import SandboxLimits, SandboxResult, run_in_sandbox
from gb_agent.text_log import TextLog

HARNESS = "gb_agent.emulator.harness"
ROM_IN_SANDBOX = "/rom/game.gb"
LIBRARY_IMPORT_ROOT = "/opt/library"  # scripts import each other as `library.<name>`
MAX_WATCHES = 32
MAX_WATCH_LENGTH = 64


@dataclass(frozen=True)
class StepLimits:
    max_frames: int = 36_000  # ten minutes of game time
    max_events: int = 200_000
    keyframe_every: int = 120  # frames between keyframe screenshots
    max_keyframes: int = 6
    text_every: int = 4  # frames between reads of the text boxes during the replay
    sandbox: SandboxLimits = SandboxLimits()


@dataclass
class StepOutcome:
    sandbox: SandboxResult
    start_frame: int
    end_frame: int
    state: bytes | None  # None: the step produced nothing usable; keep the old state
    events: list[dict] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    screenshot_png: bytes | None = None  # after the step
    before_png: bytes | None = None
    keyframes: list[tuple[int, bytes]] = field(default_factory=list)  # (frame, png)
    watch_before: dict[str, list[int]] = field(default_factory=dict)
    watch_after: dict[str, list[int]] = field(default_factory=dict)
    verified: bool = False  # replaying the events reproduced the state exactly
    text: TextLog | None = None  # text seen during the replay, if it was read
    problem: str = ""  # why there's no state, or why it isn't verified

    @property
    def usable(self) -> bool:
        return self.state is not None and self.verified

    @property
    def frames_used(self) -> int:
        return self.end_frame - self.start_frame


def validate_events(events, start_frame: int, end_frame: int, limits: StepLimits) -> str:
    """Why ``events`` can't be replayed safely, or "" if they can."""
    if not isinstance(events, list):
        return "events is not a list"
    if len(events) > limits.max_events:
        return f"{len(events)} events, over the limit of {limits.max_events}"
    frame = start_frame
    for i, event in enumerate(events):
        if not isinstance(event, dict) or event.get("frame") != frame:
            return f"event {i} is malformed or out of order: {event!r}"
        kind = event.get("type")
        if kind == "tick":
            frames = event.get("frames")
            if type(frames) is not int or frames < 1:
                return f"event {i} has a bad frame count: {event!r}"
            frame += frames
            # +1: a step that ends with an input runs one more frame (end_step)
            if frame - start_frame > limits.max_frames + 1:
                return f"events advance more than the limit of {limits.max_frames} frames"
        elif kind in ("press", "release"):
            if event.get("button") not in BUTTONS:
                return f"event {i} has an unknown button: {event!r}"
        else:
            return f"event {i} has an unknown type: {event!r}"
        if set(event) - {"frame", "type", "frames", "button"}:
            return f"event {i} has unexpected fields: {event!r}"
    if frame != end_frame:
        return f"events end at frame {frame}, but the step reported {end_frame}"
    return ""


def validate_watch(watch: dict) -> str:
    """Why a watch list is unusable, or "" if it's fine.

    ``watch`` maps labels to ``(addr, length, bank)``; bank may be None.
    """
    if not isinstance(watch, dict) or len(watch) > MAX_WATCHES:
        return f"watch must be a dict of at most {MAX_WATCHES} entries"
    for label, ref in watch.items():
        if not isinstance(label, str) or not 0 < len(label) <= 40:
            return f"bad watch label {label!r}"
        try:
            addr, length, bank = ref
        except (TypeError, ValueError):
            return f"watch {label!r} must be (addr, length, bank)"
        if type(addr) is not int or not 0 <= addr <= 0xFFFF:
            return f"watch {label!r}: addr must be 0x0000-0xFFFF"
        if type(length) is not int or not 1 <= length <= MAX_WATCH_LENGTH \
                or addr + length > 0x10000:
            return f"watch {label!r}: length must be 1-{MAX_WATCH_LENGTH} and stay in range"
        if bank is not None and (type(bank) is not int or not 0 <= bank <= 0x1FF):
            return f"watch {label!r}: bad bank"
    return ""


def _decode_keyframes(raw) -> list[tuple[int, bytes]]:
    if not isinstance(raw, list):
        raise ValueError("keyframes is not a list")
    return [(int(frame), base64.b64decode(png, validate=True)) for frame, png in raw]


def _memory_values(raw) -> dict[str, list[int]]:
    if not isinstance(raw, dict) or not all(
        isinstance(v, list) and all(type(b) is int for b in v) for v in raw.values()
    ):
        raise ValueError("watched memory is malformed")
    return {str(k): v for k, v in raw.items()}


def replay(rom: bytes, start_state: bytes, events: list[dict], *,
           look: Callable[[PyBoy], None] | None = None, every: int = 4) -> bytes:
    """The state reached by applying ``events`` from ``start_state``.

    ``look``, if given, is called at the start and every ``every`` frames after.
    """
    pyboy = boot(rom, start_state)
    try:
        if look is None:
            apply_events(pyboy, events)
        else:
            look(pyboy)
            for event in events:
                if event["type"] != "tick":
                    apply_event(pyboy, event)
                    continue
                left = event["frames"]
                while left:
                    frames = min(every, left)
                    apply_event(pyboy, {"type": "tick", "frames": frames})
                    left -= frames
                    look(pyboy)
        return save_state(pyboy)
    finally:
        pyboy.stop(save=False)


def run_step(
    rom_path: Path,
    state: bytes,
    code: str,
    *,
    start_frame: int = 0,
    limits: StepLimits = StepLimits(),
    library_dir: Path | None = None,
    watch: dict | None = None,
    image: str | None = None,
    read_text: Callable[[PyBoy], list[list[str]]] | None = None,
) -> StepOutcome:
    """Run ``code`` against the game at ``state`` in the sandbox, and check it.

    ``library_dir`` is the library's package directory, mounted read-only so
    the code can ``import library.<script>``. ``watch`` is memory to read
    before and after (see ``validate_watch``); it raises ValueError if invalid.
    ``read_text`` reads the text boxes on screen; given it, the replay collects
    the text that went by into ``outcome.text``.
    """
    watch = watch or {}
    if problem := validate_watch(watch):
        raise ValueError(problem)
    mounts = {Path(rom_path): ROM_IN_SANDBOX}
    if library_dir is not None:
        mounts[Path(library_dir)] = f"{LIBRARY_IMPORT_ROOT}/library"
    payload = {
        "rom": ROM_IN_SANDBOX,
        "state": base64.b64encode(state).decode(),
        "start_frame": start_frame,
        "max_frames": limits.max_frames,
        "max_events": limits.max_events,
        "watch": {label: list(ref) for label, ref in watch.items()},
        "keyframe_every": limits.keyframe_every,
        "max_keyframes": limits.max_keyframes,
    }
    result = run_in_sandbox(
        code, payload,
        limits=limits.sandbox,
        read_only_mounts=mounts,
        harness=HARNESS,
        sys_path=[LIBRARY_IMPORT_ROOT] if library_dir is not None else None,
        image=image,
    )
    outcome = StepOutcome(sandbox=result, start_frame=start_frame,
                          end_frame=start_frame, state=None)
    h = result.harness
    if h is None:
        if result.harness_error:
            outcome.problem = f"harness failed: {result.harness_error['message']}"
        else:
            outcome.problem = f"no result from the sandbox ({result.status}: {result.detail})"
        return outcome

    try:
        new_state = base64.b64decode(h["state"], validate=True)
        end_frame = h["end_frame"]
        screenshot = base64.b64decode(h["screenshot"], validate=True)
        before = base64.b64decode(h["before_screenshot"], validate=True)
        keyframes = _decode_keyframes(h["keyframes"])
        watch_before = _memory_values(h["watch_before"])
        watch_after = _memory_values(h["watch_after"])
    except (KeyError, TypeError, ValueError) as e:
        outcome.problem = f"malformed step result: {e}"
        return outcome
    if type(end_frame) is not int:
        outcome.problem = "malformed step result: end_frame is not an int"
        return outcome
    if problem := validate_events(h.get("events"), start_frame, end_frame, limits):
        outcome.problem = f"events rejected: {problem}"
        return outcome

    outcome.end_frame = end_frame
    outcome.state = new_state
    outcome.events = h["events"]
    outcome.notes = h.get("notes") or []
    outcome.screenshot_png = screenshot
    outcome.before_png = before
    outcome.keyframes = keyframes
    outcome.watch_before = watch_before
    outcome.watch_after = watch_after
    look = None
    if read_text is not None:
        outcome.text = TextLog()
        look = lambda pyboy: outcome.text.add(read_text(pyboy))  # noqa: E731
    outcome.verified = replay(Path(rom_path).read_bytes(), state, outcome.events,
                              look=look, every=limits.text_every) == new_state
    if not outcome.verified:
        outcome.problem = ("replaying the recorded inputs didn't reproduce the step's state: "
                           "something changed the game without going through `game`")
    return outcome
