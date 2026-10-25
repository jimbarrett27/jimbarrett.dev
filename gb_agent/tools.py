"""The tools an agent plays with, as OpenAI-style function schemas plus a dispatcher.

Each tool returns text for the model and, for anything that touches the game,
screenshots. Every argument comes from a model and is checked here; a bad call
gets an error message back, never an exception, so a confused model can recover.
"""

import json
from dataclasses import dataclass, field

from gb_agent.emulator import BUTTONS
from gb_agent.library import ScriptError
from gb_agent.run import Run
from gb_agent.trace import Trace

MAX_TOOL_TEXT = 6_000
REPEAT_NOTE_AT = 3  # identical calls in a row before saying so
MAX_NOTES = 2_000


@dataclass
class ToolResult:
    text: str
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (caption, png)
    trace: Trace | None = None


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


TOOL_SCHEMAS = [
    _fn("run_script", "Run a script from your library against the game.", {
        "name": {"type": "string"},
        "args": {"type": "object", "description": "keyword arguments for the script"},
    }, ["name"]),
    _fn("run_code", "Run a one-off Python snippet with `game` in scope "
        "(and `from library.<name> import <name>` available).", {
        "code": {"type": "string"},
    }, ["code"]),
    _fn("write_script", "Create or replace a script in your library.", {
        "name": {"type": "string", "description": "lowercase_with_underscores"},
        "code": {"type": "string", "description":
                 "Python defining a function with the same name, taking `game` first, "
                 "with a docstring"},
        "reason": {"type": "string", "description": "one line: why this change"},
    }, ["name", "code", "reason"]),
    _fn("read_script", "Show a script's source, now or at an older version.", {
        "name": {"type": "string"},
        "version": {"type": "string"},
    }, ["name"]),
    _fn("list_scripts", "List your library's scripts with how often they're used and fail.",
        {}, []),
    _fn("script_history", "Show every change to a script, newest first.", {
        "name": {"type": "string"},
    }, ["name"]),
    _fn("press", "Press one button: hold it, release, then wait (like game.tap).", {
        "button": {"type": "string", "enum": list(BUTTONS)},
        "hold": {"type": "integer", "description": "frames to hold it, default 8"},
        "after": {"type": "integer", "description": "frames to wait after, default 16"},
    }, ["button"]),
    _fn("wait", "Let the game run without pressing anything.", {
        "frames": {"type": "integer", "description": "60 frames is about one second"},
    }, ["frames"]),
    _fn("screenshot", "See the current screen (doesn't advance the game).", {}, []),
    _fn("read_memory", "Read bytes of game memory (doesn't advance the game).", {
        "addr": {"type": "string", "description": "address, e.g. \"0xC000\""},
        "length": {"type": "integer", "description": "1-64, default 1"},
        "bank": {"type": "integer"},
    }, ["addr"]),
    _fn("watch_memory", "Add (or remove) memory to report before and after every step.", {
        "label": {"type": "string"},
        "addr": {"type": "string", "description": "address, e.g. \"0xC000\""},
        "length": {"type": "integer", "description": "1-64, default 1"},
        "remove": {"type": "boolean"},
    }, ["label"]),
    _fn("update_notes", "Replace your notes: facts you want to keep, such as where you are, "
        "what you've found out, which scripts work, what you're trying. They're shown to you "
        "word for word every time your context is cleared.", {
        "notes": {"type": "string", "description": "the whole new notes, at most 2000 characters"},
    }, ["notes"]),
    _fn("report_blocker", "Tell Jim (who set this up) that something seems impossible with "
        "your current tools. He reads these to fix the setup.", {
        "problem": {"type": "string"},
        "tried": {"type": "string"},
        "would_help": {"type": "string"},
    }, ["problem"]),
]

SUBAGENT_SCHEMAS = [
    _fn("define_subagent", "Create or update a sub-agent: a helper you design and give one "
        "job at a time, so long or fiddly work doesn't fill your own context.", {
        "name": {"type": "string", "description": "lowercase_with_underscores"},
        "purpose": {"type": "string", "description": "one line: what it's for"},
        "instructions": {"type": "string", "description":
                         "its instructions: how to do the job, what to watch for, when to stop"},
        "tools": {"type": "array", "items": {"type": "string"}, "description":
                  "which of your tools it gets (not the sub-agent tools)"},
        "scripts": {"type": "array", "items": {"type": "string"}, "description":
                    "library scripts it may run (empty: any)"},
        "model": {"type": "string", "description": "model profile; default: yours"},
        "reason": {"type": "string", "description": "one line: why this change"},
    }, ["name", "purpose", "instructions", "tools", "reason"]),
    _fn("run_subagent", "Give a sub-agent a job. It starts fresh, works until it calls "
        "finish or runs out of calls or frames, and you get its summary back.", {
        "name": {"type": "string"},
        "task": {"type": "string", "description": "the job, with anything it needs to know"},
        "max_calls": {"type": "integer", "description": "LLM calls it may use, default 15"},
        "max_frames": {"type": "integer", "description": "frames it may spend, default 3000"},
    }, ["name", "task"]),
    _fn("list_subagents", "List your sub-agents: purpose, tools, model, how often they finished.",
        {}, []),
]

FINISH_SCHEMA = _fn("finish", "End your job and report back to the agent that started you.", {
    "summary": {"type": "string", "description":
                "what you did, what happened, what you learned, what's left"},
}, ["summary"])

TOOL_NAMES = [schema["function"]["name"] for schema in TOOL_SCHEMAS]  # the main agent's base set
_SCHEMAS = {schema["function"]["name"]: schema
            for schema in [*TOOL_SCHEMAS, *SUBAGENT_SCHEMAS, FINISH_SCHEMA]}


class ToolError(ValueError):
    pass


def _int(args: dict, key: str, default: int | None, lo: int, hi: int) -> int:
    value = args.get(key, default)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        value = int(value)
    if type(value) is not int or not lo <= value <= hi:
        raise ToolError(f"{key} must be a whole number from {lo} to {hi}")
    return value


def _addr(args: dict, key: str = "addr") -> int:
    value = args.get(key)
    try:
        addr = int(value, 0) if isinstance(value, str) else value
    except ValueError:
        addr = None
    if type(addr) is not int or not 0 <= addr <= 0xFFFF:
        raise ToolError(f'{key} must be an address from 0x0000 to 0xFFFF, like "0xC000"')
    return addr


def _str(args: dict, key: str, required: bool = True) -> str:
    value = args.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise ToolError(f"{key} must be a non-empty string")
    return value


def _bool(args: dict, key: str) -> bool:
    value = args.get(key, False)
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)




class Tools:
    """Dispatches tool calls for one agent on one run.

    The main agent gets every tool (with the sub-agent tools when ``host`` is
    given). A sub-agent gets ``allowed`` (always including ``finish``), may be
    limited to some ``scripts``, and can only keep ``frame_allowance`` frames.
    """

    def __init__(self, run: Run, agent: str = "main", trace_budget: int = 2_500, *,
                 allowed: tuple[str, ...] | None = None, scripts: tuple[str, ...] | None = None,
                 frame_allowance: int | None = None, host=None):
        self.run = run
        self.agent = agent
        self.trace_budget = trace_budget
        if allowed is None:
            subagent_tools = [s["function"]["name"] for s in SUBAGENT_SCHEMAS]
            allowed = (*TOOL_NAMES, *(subagent_tools if host is not None else []))
        self.allowed = tuple(name for name in _SCHEMAS if name in allowed)
        self.scripts = scripts
        self.frame_allowance = frame_allowance
        self.frames_kept = 0
        self.host = host
        self.finished: str | None = None  # set by the finish tool
        self._last_call: str | None = None
        self._repeats = 0

    def schemas(self) -> list[dict]:
        return [_SCHEMAS[name] for name in self.allowed]

    def frames_left(self) -> int:
        if self.frame_allowance is None:
            return self.run.frames_left
        return max(0, min(self.run.frames_left, self.frame_allowance - self.frames_kept))

    def _cap(self) -> int | None:
        return None if self.frame_allowance is None else self.frames_left()

    def call(self, name: str, args) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(f"Error: arguments for {name} must be a JSON object.")
        method = getattr(self, f"_{name}", None) if name in self.allowed else None
        if method is None:
            return ToolResult(f"Error: you don't have a tool called {name!r}. "
                              f"Your tools: {', '.join(self.allowed)}.")
        frame = self.run.frame
        try:
            result = method(args)
        except (ToolError, ScriptError) as e:
            result = ToolResult(f"Error: {e}")
        if name != "run_subagent":  # a sub-agent's frames count against its own allowance
            self.frames_kept += self.run.frame - frame
        if len(result.text) > MAX_TOOL_TEXT:
            result.text = result.text[:MAX_TOOL_TEXT] + "\n…[cut]"
        result.text += self._notes(name, args)
        return result

    def _notes(self, name: str, args: dict) -> str:
        """Plain-spoken nudges when the agent seems stuck in a loop."""
        notes = []
        call = f"{name} {json.dumps(args, sort_keys=True, default=str)}"
        self._repeats = self._repeats + 1 if call == self._last_call else 1
        self._last_call = call
        if self._repeats >= REPEAT_NOTE_AT:
            notes.append(f"You've made this exact call {self._repeats} times in a row. "
                         "If it isn't doing what you want, try something different.")
        return "".join(f"\nNote: {note}" for note in notes)

    def _game_step_allowed(self) -> None:
        if self.frames_left() == 0:
            raise ToolError("the frame budget is used up")

    def _budget(self) -> str:
        line = self.run.budget_line()
        if self.frame_allowance is not None:
            line += f" [your allowance: {self.frames_left()} frames left]"
        return line

    def _trace_result(self, trace: Trace) -> ToolResult:
        return ToolResult(f"{trace.to_text(self.trace_budget)}\n{self._budget()}",
                          trace.images, trace)

    # -- game ---------------------------------------------------------------

    def _run_script(self, args: dict) -> ToolResult:
        self._game_step_allowed()
        script_args = args.get("args") or {}
        if isinstance(script_args, str):
            try:
                script_args = json.loads(script_args)
            except json.JSONDecodeError:
                raise ToolError("args must be a JSON object of keyword arguments") from None
        name = _str(args, "name")
        if self.scripts is not None and name not in self.scripts:
            raise ToolError(f"you may only run these scripts: {', '.join(self.scripts)}")
        trace = self.run.run_script(name, script_args, agent=self.agent, max_frames=self._cap())
        return self._trace_result(trace)

    def _run_code(self, args: dict) -> ToolResult:
        self._game_step_allowed()
        trace = self.run.run_code(_str(args, "code"), agent=self.agent, max_frames=self._cap(),
                                  snippet=True)
        return self._trace_result(trace)

    def _press(self, args: dict) -> ToolResult:
        self._game_step_allowed()
        button = args.get("button")
        if button not in BUTTONS:
            raise ToolError(f"button must be one of {', '.join(BUTTONS)}")
        # hold_frames/wait_frames: the names this tool used before matching game.tap
        args = {"hold": args.get("hold_frames", 8), "after": args.get("wait_frames", 16), **args}
        hold = _int(args, "hold", 8, 1, 600)
        wait = _int(args, "after", 16, 0, 600)
        code = (f"game.press({button!r})\ngame.tick({hold})\ngame.release({button!r})\n"
                + (f"game.tick({wait})\n" if wait else ""))
        trace = self.run.run_code(code, agent=self.agent, title=f"press({button})",
                                  max_frames=self._cap())
        return self._trace_result(trace)

    def _wait(self, args: dict) -> ToolResult:
        self._game_step_allowed()
        frames = _int(args, "frames", None, 1, 3_600)
        limit = min(self.frames_left(), self.run.config.step.max_frames)
        shortened = frames > limit
        frames = min(frames, limit)
        trace = self.run.run_code(f"game.tick({frames})", agent=self.agent,
                                  title=f"wait({frames})", max_frames=self._cap())
        result = self._trace_result(trace)
        if shortened:
            result.text = (f"(Shortened to {frames} frames: the most one step may use, or "
                           "what's left of the budget.)\n" + result.text)
        return result

    def _screenshot(self, args: dict) -> ToolResult:
        return ToolResult(f"The screen at frame {self.run.frame}.",
                          [(f"screen (frame {self.run.frame})", self.run.screenshot_png())])

    def _read_memory(self, args: dict) -> ToolResult:
        addr = _addr(args)
        length = _int(args, "length", 1, 1, 64)
        bank = args.get("bank")
        if bank is not None:
            bank = _int(args, "bank", None, 0, 0x1FF)
        try:
            values = self.run.read_memory(addr, length, bank)
        except ValueError as e:
            raise ToolError(str(e)) from None
        dump = " ".join(f"{v:02x}" for v in values)
        return ToolResult(f"memory at 0x{addr:04X} ({length} bytes): {dump}")

    def _watch_memory(self, args: dict) -> ToolResult:
        label = _str(args, "label")
        if _bool(args, "remove"):
            self.run.watch.pop(label, None)
            return ToolResult(f"Stopped watching {label!r}. Watching: {self._watching()}")
        addr = _addr(args)
        length = _int(args, "length", 1, 1, 64)
        try:
            self.run.set_watch(label, addr, length)
        except ValueError as e:
            raise ToolError(str(e)) from None
        return ToolResult(f"Watching {label!r} at 0x{addr:04X}. Watching: {self._watching()}")

    def _watching(self) -> str:
        return ", ".join(f"{label} (0x{a:04X}, {n})" for label, (a, n, _) in
                         self.run.watch.items()) or "nothing"

    # -- library ------------------------------------------------------------

    def _write_script(self, args: dict) -> ToolResult:
        name = _str(args, "name")
        code = _str(args, "code")
        library = self.run.library
        if library.exists(name) and library.read(name) == code:
            return ToolResult(f"Nothing saved: that's identical to the current {name} "
                              f"(version {library.version(name)}). Change the code to fix it.")
        version = self.run.library.write(name, code, _str(args, "reason"),
                                         agent=self.agent, run=self.run.id, step=self.run.step)
        return ToolResult(f"Saved {name} as version {version}. "
                          f"Run it with run_script(name={name!r}, args={{...}}).")

    def _read_script(self, args: dict) -> ToolResult:
        name = _str(args, "name")
        version = args.get("version") or None
        source = self.run.library.read(name, version)
        current = self.run.library.version(name)
        return ToolResult(f"# {name} @ {version or current}\n{source}")

    def _list_scripts(self, args: dict) -> ToolResult:
        scripts = self.run.library.scripts()
        if not scripts:
            return ToolResult("Your library is empty.")
        usage = self.run.library.usage()
        lines = []
        for info in scripts:
            use = usage.get(info.name, {})
            stats = (f"{use['calls']} runs, {use['failures']} failed"
                     if use else "never run")
            lines.append(f"- {info.signature} @ {info.version}: {info.summary} ({stats})")
        return ToolResult("\n".join(lines))

    def _script_history(self, args: dict) -> ToolResult:
        name = _str(args, "name")
        return ToolResult("\n".join(f"{c.version} {c.date[:16]} {c.reason}"
                                    for c in self.run.library.history(name)))

    def _update_notes(self, args: dict) -> ToolResult:
        notes = _str(args, "notes").strip()
        if len(notes) > MAX_NOTES:
            raise ToolError(f"notes are limited to {MAX_NOTES} characters (these are "
                            f"{len(notes)}); keep what matters most")
        self.run.set_notes(notes, agent=self.agent)
        return ToolResult(f"Notes saved ({len(notes)} characters). You'll see them again, "
                          "word for word, whenever your context is cleared.")

    # -- sub-agents ---------------------------------------------------------

    def _define_subagent(self, args: dict) -> ToolResult:
        from gb_agent.subagents import check_spec

        spec = check_spec(args, parent_tools=list(self.allowed), allow_paid=self.host.allow_paid,
                          parent_model=self.host.parent_profile)
        version, changed = self.run.library.write_subagent(
            spec.name, spec.to_json(), _str(args, "reason"),
            agent=self.agent, run=self.run.id, step=self.run.step)
        if not changed:
            return ToolResult(f"Nothing saved: that's identical to the current {spec.name} "
                              f"(version {version}).")
        return ToolResult(f"Saved sub-agent {spec.name} as version {version}. Give it a job "
                          f"with run_subagent(name={spec.name!r}, task=...).")

    def _run_subagent(self, args: dict) -> ToolResult:
        from gb_agent.subagents import DEFAULT_CALLS, DEFAULT_FRAMES, MAX_CALLS

        name = _str(args, "name")
        task = _str(args, "task")[:2_000]
        max_calls = _int(args, "max_calls", DEFAULT_CALLS, 1, MAX_CALLS)
        max_frames = _int(args, "max_frames", min(DEFAULT_FRAMES, self.frames_left()), 0,
                          max(0, self.frames_left()))
        result = self.host.run_subagent(name, task, max_calls=max_calls,
                                        max_frames=max_frames, parent=self.agent)
        text = (f"Sub-agent {result.agent} ({name} @ {result.version}) ended: {result.reason}. "
                f"It used {result.calls} LLM calls and {result.frames} frames "
                f"({result.kept_steps} steps kept).\nIts summary: {result.summary}\n"
                f"{self._budget()}")
        return ToolResult(text, [(f"the screen now (frame {self.run.frame})",
                                  result.screen_png)])

    def _list_subagents(self, args: dict) -> ToolResult:
        specs = self.run.library.subagents()
        if not specs:
            return ToolResult("You have no sub-agents yet. Make one with define_subagent.")
        usage = self.run.library.usage(kind="subagent")
        lines = []
        for spec in specs:
            use = usage.get(spec["name"])
            stats = (f"{use['calls']} jobs, {use['calls'] - use['failures']} finished"
                     if use else "never run")
            lines.append(f"- {spec['name']} @ {spec['version']}: {spec['purpose']} "
                         f"(tools: {', '.join(spec['tools'])}; model: {spec['model']}; {stats})")
        return ToolResult("\n".join(lines))

    def _finish(self, args: dict) -> ToolResult:
        self.finished = _str(args, "summary")
        return ToolResult("Finished. Your summary goes back to the agent that started you.")

    # -- people -------------------------------------------------------------

    def _report_blocker(self, args: dict) -> ToolResult:
        return ToolResult(self.run.report_blocker(
            _str(args, "problem"), _str(args, "tried", False),
            _str(args, "would_help", False), self.agent))
