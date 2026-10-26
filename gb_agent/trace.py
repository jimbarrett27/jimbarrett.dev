"""What the agent is shown after a script runs.

A trace is a short text report plus a few images (the screen before, some
keyframes, the screen after). The text is cut to a character budget, so it fits
a small model's context; the full detail stays in the run directory.

After a kept step the game profile's description of the game state (``state``)
goes near the top, outside the budget: it's what the agent most needs, and it's
already short. So does the text that went by during the step, when some of it
is gone by the end: a conversation mashed through leaves nothing on screen to
compare. Memory only appears if the agent asked to watch it.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from gb_agent.steps import StepOutcome


@dataclass
class Trace:
    title: str  # what ran, e.g. "walk_to(x=3, y=4) @ 1a2b3c4"
    status: str  # ok, error, timeout, oom, crashed
    usable: bool  # the step produced a verified state
    start_frame: int
    end_frame: int
    value: Any = None
    error: dict | None = None
    stdout: str = ""
    stdout_bytes: int = 0
    stderr: str = ""
    notes: list[dict] = field(default_factory=list)
    inputs: str = ""
    memory: list[tuple[str, list[int], list[int]]] = field(default_factory=list)
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (caption, png)
    screen_change: float | None = None  # share of pixels that differ, before vs after
    problem: str = ""
    state: str = ""  # the game profile's description of the state after the step
    text: str = ""  # text that went by during the step, if some isn't on screen any more

    @property
    def frames(self) -> int:
        return self.end_frame - self.start_frame

    def to_text(self, budget: int = 3_000) -> str:
        head = [f"{self.title}: {self.status}"
                + ("" if self.usable else " (nothing kept)"),
                f"frames {self.start_frame}→{self.end_frame} ({self.frames} used)"]
        if self.problem:
            head.append(f"problem: {self.problem}")
        if self.usable and self.status == "ok" and self.frames == 0:
            head.append("nothing happened: no frames ran and no buttons were pressed "
                        "(is the script a stub, or did it return early?)")
        if self.inputs:
            head.append(f"inputs: {self.inputs}")
        if self.state:
            head.append(self.state)
            budget += len(self.state) + 1
        if self.text:
            head.append(f"Text during this step: {_short(self.text, 600)}")
        if self.screen_change is not None:
            head.append(f"screen: {describe_change(self.screen_change)}")
        if self.value is not None:
            head.append(f"returned: {_short(repr(self.value), 400)}")
        if self.memory:
            head.append("watched memory:")
            for label, before, after in self.memory:
                change = (f"{_hex(after)} (unchanged)" if before == after
                          else f"{_hex(before)} → {_hex(after)}")
                head.append(f"  {label}: {change}")
        if self.images:
            head.append("images: " + ", ".join(caption for caption, _ in self.images))

        sections = []
        if self.error:
            sections.append(("error", f"{self.error['type']}: {self.error['message']}\n"
                                      f"{self.error.get('traceback', '')}"))
        if self.notes:
            sections.append(("notes", "\n".join(
                f"[frame {n['frame']}] {n['label']}"
                + ("" if n.get("value") is None else f": {_short(repr(n['value']), 200)}")
                for n in self.notes)))
        if self.stdout:
            cut = f" (first {len(self.stdout)} of {self.stdout_bytes} bytes)" \
                if self.stdout_bytes > len(self.stdout) else ""
            sections.append((f"printed{cut}", self.stdout))
        if self.stderr.strip():
            sections.append(("stderr", self.stderr))

        text = "\n".join(head)
        remaining = budget - len(text)
        for i, (name, body) in enumerate(sections):
            share = max(0, remaining // (len(sections) - i)) - len(name) - 4
            block = f"\n{name}:\n{_short(body.rstrip(), share, keep_end=name == 'error')}"
            text += block
            remaining -= len(block)
        return text[:budget]


def _hex(values: list[int]) -> str:
    return " ".join(f"{v:02x}" for v in values)


def _short(text: str, limit: int, keep_end: bool = False) -> str:
    """Cut ``text`` to ``limit`` chars, keeping the start and end (or just the end)."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    marker = " …[cut]… "
    if keep_end:
        return marker.strip() + " " + text[-(limit - len(marker)):]
    half = (limit - len(marker)) // 2
    return text[:half] + marker + text[-half:] if half > 0 else text[:limit]


def screen_change(before_png: bytes, after_png: bytes) -> float:
    """The share of pixels that differ between two screenshots, 0 to 1."""
    import io

    from PIL import Image, ImageChops

    before = Image.open(io.BytesIO(before_png)).convert("RGB")
    after = Image.open(io.BytesIO(after_png)).convert("RGB")
    if before.size != after.size:
        return 1.0
    diff = ImageChops.difference(before, after).convert("L").point(lambda v: 255 if v else 0)
    return diff.histogram()[255] / (diff.width * diff.height)


def describe_change(share: float) -> str:
    """Plain words for a screen change, so a small model doesn't have to judge."""
    if share == 0:
        return "unchanged (identical before and after)"
    percent = share * 100
    amount = f"{percent:.1f}%" if percent < 1 else f"{percent:.0f}%"
    size = "a tiny part" if share < 0.02 else "part" if share < 0.3 else "most"
    return f"{size} of the screen changed ({amount} of pixels)"


def summarize_inputs(events: list[dict]) -> str:
    """e.g. "left ×3, right ×3 (held ~16 frames)"."""
    presses = [e["button"] for e in events if e["type"] == "press"]
    if not presses:
        return "no buttons pressed"
    counts = Counter(presses)
    order = list(dict.fromkeys(presses))
    held, pressed_at = [], {}
    for event in events:
        if event["type"] == "press":
            pressed_at[event["button"]] = event["frame"]
        elif event["type"] == "release" and event["button"] in pressed_at:
            held.append(event["frame"] - pressed_at.pop(event["button"]))
    text = ", ".join(f"{button} ×{counts[button]}" for button in order)
    if held:
        text += f" (held ~{round(sum(held) / len(held))} frames)"
    if pressed_at:
        text += f"; still held: {', '.join(sorted(pressed_at))}"
    return text


def build_trace(outcome: StepOutcome, title: str) -> Trace:
    result = outcome.sandbox
    trace = Trace(
        title=title,
        status=result.status,
        usable=outcome.usable,
        start_frame=outcome.start_frame,
        end_frame=outcome.end_frame,
        value=result.value,
        error=result.error,
        stdout=result.stdout,
        stdout_bytes=result.stdout_bytes,
        stderr=result.stderr,
        notes=outcome.notes,
        problem=outcome.problem or result.detail,
    )
    if outcome.state is None:
        return trace
    trace.inputs = summarize_inputs(outcome.events)
    if outcome.text is not None and outcome.text.gone_by:
        trace.text = outcome.text.text()
    trace.memory = [(label, outcome.watch_before.get(label, []), after)
                    for label, after in outcome.watch_after.items()]
    if outcome.before_png and outcome.screenshot_png:
        trace.screen_change = screen_change(outcome.before_png, outcome.screenshot_png)
    if outcome.before_png:
        trace.images.append((f"before (frame {outcome.start_frame})", outcome.before_png))
    trace.images += [(f"frame {frame}", png) for frame, png in outcome.keyframes]
    if outcome.screenshot_png:
        trace.images.append((f"after (frame {outcome.end_frame})", outcome.screenshot_png))
    return trace
