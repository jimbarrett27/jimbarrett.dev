# Plan: a Game Boy agent that builds its own scripts and sub-agents

Status: agreed 2026-10-21. Starts from scratch; nothing is carried over from the
deleted Pokemon branches.

## Goal

An LLM agent that plays a Game Boy game (Pokemon Silver first) through PyBoy, and
that builds up its own abstractions as it goes:

- **Scripts:** Python routines that bundle many inputs and small decisions into one
  call (`walk_to(x, y)`, `mash_through_text()`, `heal_at_pokecentre()`), so the agent
  decides *what* to do and the script handles *how*.
- **Sub-agents:** focused helpers the agent designs itself (a prompt, a set of tools
  and scripts, a model) and hands a single job to, so the main agent's small context
  isn't spent on detail.

The agent can watch what its scripts did, fix them, and keep improving them. Every
script and sub-agent keeps its full version history, and every input that reaches
the game is recorded, so whole runs can be replayed and inspected afterwards.

The point is to compare models: run the same experiment, with the same frame budget,
for several underlying LLMs and see how far each gets.

Ground rules:

1. **Agent-written code is untrusted.** It runs in a locked-down container, never on
   the host. Safety comes from OS-level isolation, not from restricting Python.
2. **The model sees everything, changes nothing directly.** Screenshots and full
   read access to the game's memory. Memory writes are forbidden; the game only
   changes through button presses and frames.
3. **The model can be swapped.** Nothing outside one config module knows which model
   is driving. Start with the local Qwen3-VL-2B and move up if it proves too weak.
4. **The game can be swapped.** Everything game-specific lives in one game profile.

## Architecture

```
host (gb_agent/)                              sandbox container (gb_agent/sandbox/)
┌──────────────────────────────────┐          ┌──────────────────────────────────┐
│ Main agent ──spawns──▶ sub-agents│  JSON    │ runner: load state → run script  │
│  (all share the same tools)      │ ───────▶ │   → save state, return trace     │
│ Run directory: library (git),    │ ◀─────── │ RecordingGame (wraps PyBoy)      │
│  states, event logs, frames      │          │  logs every input + frame tick   │
│ Game profile + model profile     │          │ ROM + library: read-only         │
└──────────────────────────────────┘          └──────────────────────────────────┘
```

Every tool that touches the game, including a single button press, goes through the
same container path, so there's exactly one place where inputs are recorded.

## Experiments, runs and steps

- An **experiment config** is: a game profile, a model profile, a frame budget, and
  limits on LLM calls, tokens and wall-clock time.
- Running a config produces one **run**, with its own directory and its own library.
- A **step** is one tool call that touches the game.

**Frame budget.** Only frames that reach the real game count. Test runs (below) are
free in frames, and LLM thinking doesn't spend frames either, because the game is
paused between steps. The call, token and time limits are what stop an agent that
only thinks or only tests. The run ends when any limit is hit and records which one.

For scale: 10,000 frames is about 2.8 minutes of game time at ~60 fps, roughly
enough to leave the house. Budgets should be easy to set much higher.

**Library per run.** Each run's library starts as a copy of the game profile's seed
library and grows only within that run, so every model starts from the same place.

**Progress.** The game profile lists raw values to read from memory (for Silver,
things like map ID, badges, Pokedex counts, party levels). They're logged after every
step. How to turn them into a score is decided later, after seeing some runs; since
the raw values are kept, any formula can be applied to old runs too.

**Comparing models.** `python -m gb_agent.compare` runs one config across several
model profiles and tabulates progress, frames, tokens, failures and blockers.

### One step = state in, state out

A step loads the current save state, runs one script (or one built-in action) in a
fresh container, saves the new state, and returns a trace. PyBoy loads a state in
milliseconds, so starting fresh each step is cheap. It also means:

- a crash, timeout or broken script loses nothing; the run stays at the last good
  state,
- every step is a checkpoint, so runs can be rewound, branched and replayed,
- a script can be **test-run**: run from the current state, look at the trace, and
  throw the result away instead of keeping it. That's how the agent tries a script
  before trusting it.

## Sandbox

Run with Docker, which is already on the server. Each step's container gets:

- `--network none`
- `--read-only` root filesystem, plus a small `tmpfs` for scratch space
- a non-root user, `--cap-drop ALL`, `--security-opt no-new-privileges`
- `--memory`, `--cpus` and `--pids-limit` caps
- a hard wall-clock timeout, enforced by the host (kill the container)
- mounts: the ROM and the library read-only, plus a per-step input/output folder.
  Nothing else from the home directory.
- an empty environment: no API keys and no `.env`

Docker can run the same containers under gVisor (`--runtime runsc`) later for a
stronger wall; worth doing once the basics work.

Host-side limits: cap the size of output returned to the model, and cap the number
of frames one script may advance.

## Recording and replay

Scripts don't get the raw PyBoy object. They get a `RecordingGame` wrapper, and its
methods are the only supported way to drive the game:

- button press and release, frame advance (`tick`)
- screenshot, memory **reads** (there is no write method)
- each call that changes the game is logged as an event: frame number, event type,
  arguments, and the agent, step, script and script version that caused it

Replay feeds the logged events back in frame by frame from the run's starting state.

**Verifying the record.** Python in the container can always get past the wrapper if
it tries. Rather than try to prevent that, check it: after every step, the host
replays that step's events from its starting state and compares the result with the
state the script produced. A mismatch means something wasn't recorded, and the step
is flagged at once. This is also what enforces the no-memory-writes rule: a write
that bypasses the wrapper makes the replay disagree.

The replay runs on the host, not in a second container: it runs no agent code, only
recorded inputs into a trusted ROM. The events do come out of the sandbox, so they're
validated first (known types and buttons, frames in order, within the step's limits).
Host and image pin the same PyBoy, NumPy and Pillow versions.

What makes this exact (measured, PyBoy 2.7): the rendered screen is part of the save
state, so recording and replay share one function that turns an event into PyBoy
calls, and every tick renders. A fresh boot stamps the wall-clock time into the
clock's state, so runs always start from a saved state, never from a boot.

### The real-time clock

Pokemon Silver reads a real-time clock. In PyBoy 2.7 the clock is compiled Cython
that reads wall-clock time directly (`pyboy/core/cartridge/rtc.py`, which does
`cimport time`), so it can't be faked from Python. PyBoy does have a built-in lock:
`pyboy.rtc_lock_experimental(True)` makes the clock report its starting moment
forever.

- The lock is on from power-on, so the clock always reads zero. Silver keeps its own
  offset from the clock (set when starting a new game), so in-game time is frozen at
  whatever time is chosen then, identically in every run.
- The lock itself isn't stored in save states, so it's turned on after every load.
- Whether a cartridge has a clock is read from its header, not configured.
- A test proves two runs from the same state with the same inputs give identical
  states.
- Cost: the in-game time of day never moves. If day/night ever matters, a
  frame-driven clock would need a patched PyBoy build. Not needed now.

## Game profile

Everything game-specific sits behind one profile:

```python
@dataclass
class GameProfile:
    name: str
    rom: Path
    power_on_state: Path               # the cartridge just switched on, kept
    start_state: Path                  # where every run starts: power-on + setup
    setup: tuple[str, ...]             # inputs from power-on to the start
    progress_values: dict[str, MemRef] # raw values logged every step for scoring
    seed_library: Path                 # scripts copied into a new run's library
    notes: str                         # game facts given to the agent
```

Silver is the only profile at first (`gb_agent/games/silver.py`). The sandbox,
recording, scripts, sub-agents, model profiles and run loop only know about buttons,
frames, screens and memory, so adding another game means writing a profile and a
start state, with no harness changes.

**Hints are off (decided 2026-10-21).** The agent gets no memory addresses: the
profile's `progress_values` are read by the harness for scoring and never shown, and
traces only include memory the agent has chosen to watch. So finding its own position
in RAM is part of the task. A per-experiment hints switch (pre-watched addresses, an
example script that reads them) can be added later to compare the two.

**Superseded 2026-10-25: the game state is described in every report.** No model
ever found its position in RAM (`watch_memory` was used once across all runs), so
the profile now describes the game after each kept step: map, position, on-screen
text, people, exits, a grid of the screen, party, bag and battle, read with
addresses from the pret/pokegold disassembly (`games/silver_state.py`). The agent
still navigates on its own (no provided `walk_to`); `--no-state-report` gives the
old screenshots-only behaviour for comparison. Design doc: "gb_agent state harness:
design" (claude.ai artifact).

**Game-agnostic helpers are fine (decided 2026-10-21).** Small local models couldn't
tell whether an action did anything (Silver's first tap in a new direction only turns
the player: 0.5% of pixels). So every report says how much of the screen changed, in
plain words, and tool results add a note after 3 identical calls in a row or 4 test
runs in a row. None of this knows anything about the game.

## Scripts

A script is a Python file in the library exposing one function, with typed arguments
and a docstring:

```python
def walk_to(game, x: int, y: int, max_steps: int = 50) -> dict:
    """Walk to tile (x, y) on the current map. Returns where it ended up."""
```

Scripts can import other library scripts, so higher-level ones are built from
lower-level ones. They report back with `print`, their return value, and
`game.note(...)` for labelled observations that show up in the trace.

**Seed library.** Silver's seed library holds one example, `hello_world.py`: tap
left three times, then right three times, noting each tap. It shows the agent what a
script looks like (typed function, docstring, `game.note()`, return value). With
hints off it reads no memory and doesn't say what the taps do; the screenshots in its
trace show that. (Measured: the first tap in a new direction only turns the player,
so it turns, walks two tiles, turns back and walks two.)

### Observing what a script did

Every run of a script returns a **trace**, sized to fit the model's context:

- outcome: returned value, or the error and traceback
- before and after screenshots, plus a few keyframes for longer runs
- frames used and a summary of inputs (for example "Down ×12, A ×3")
- changes to memory the agent has chosen to watch (nothing by default, since
  hints are off)
- the script's prints and notes, cut down to fit

The full detail is in the run directory if the agent asks for more, but isn't pushed
into context by default.

### Changing a script

Editing a script makes a new version; old versions are never lost. The agent gives a
one-line reason for every change, the way a commit message works. A typical loop:
write → test-run → read the trace → edit → test-run again → run it for real.

## Sub-agents

The main agent can design a sub-agent and give it a job:

```python
@dataclass
class SubAgentSpec:
    name: str
    purpose: str            # one line, shown in listings
    instructions: str       # written by the parent agent
    tools: list[str]        # a subset of the parent's tools
    scripts: list[str]      # library scripts it may call
    model: str              # a model profile name; defaults to the parent's
```

As built (2026-10-21, `gb_agent/subagents.py`): specs are `subagents/<name>.json` in the
run's library repo, versioned like scripts. A sub-agent's system prompt is the harness's
own description of `game` and the tools, plus the parent's instructions; it always gets
a `finish(summary)` tool. Its model must be the parent's (the local server runs one
model at a time) or, if the run was started with `--allow-paid`, a paid profile.
`run_subagent` takes `max_calls` (default 15, at most 50) and `max_frames` (default
3,000), and the result tells the parent why it ended (`finished`, `max_calls`,
`max_frames`, or a run limit), its summary, and its calls and frames. Events and logs
are tagged `<name>#<n>`, and sub-agent jobs are counted per spec version.

- **Running one:** `run_subagent(name, task)` starts the sub-agent with a fresh
  context and the given task, and returns its final summary plus a trace of what it
  did in the game. Only the summary goes into the parent's context.
- **Keeping them:** specs are saved to the library and versioned like scripts, so a
  good one can be reused and a bad one revised.
- **Limits:**
  - a sub-agent can't be given a tool its parent doesn't have,
  - nesting depth is capped (start at 1: sub-agents can't create their own),
  - each sub-agent run has its own step and token budget, inside the run's limits.
- **No new risk:** sub-agents use the same sandboxed tools, so they can't reach
  anything the main agent can't.

## Reporting blockers

`report_blocker(problem, tried, would_help)` lets the agent, or any sub-agent, say a
goal seems impossible with its current tools, whether or not that's true. It's how
problems with the setup get noticed.

- Logged as a run event, so it appears in the replay at the right moment, and in the
  run's `blockers.jsonl`.
- Sends Jim a Telegram message through the existing `send_notification.notify`,
  from the host, never from the sandbox. Duplicates are merged and messages are
  rate-limited per run.
- The run keeps going; the tool just returns an acknowledgement.

## Agent tools

| Tool | What it does |
|---|---|
| `run_script(name, args, test)` | Runs a library script. Returns the trace. |
| `run_code(code, test)` | Runs a one-off snippet, for exploring before writing a script. |
| `write_script(name, code, reason)` | Creates or updates a script (a new version). |
| `read_script(name, version)` | Current or past source. |
| `list_scripts()` | Names, docstrings, how often each is used and how often it fails. |
| `script_history(name)` | Every change to a script, newest first. |
| `press(button, hold_frames, wait_frames)` | Direct play, through the same recorded path. |
| `wait(frames)` | Let the game run; shortened to what's left of the budget. |
| `screenshot()` / `read_memory(addr, length)` | Look without advancing. |
| `watch_memory(label, addr, length, remove)` | Add or remove memory in the watch list used in traces. |
| `define_subagent(spec, reason)` | Creates or updates a sub-agent. |
| `run_subagent(name, task)` | Hands a job to a sub-agent and returns its summary. |
| `list_subagents()` | Names, purposes, usage. |
| `report_blocker(problem, tried, would_help)` | Tells Jim something seems impossible. |

Bounds on the agent side: the run's limits (frames, LLM calls, tokens, minutes) are
checked before every model call, and three replies in a row without a tool call end
the run. (Telling a model to stop wasn't enough last time; hard limits were.)

### The agent loop (`gb_agent/agent.py`)

Written on LangChain's chat-model interface rather than with `agents.Agent`, which
keeps every message and returns tool results as text only. A small local model needs
control over its context:

- **Append-only.** llama-server reuses the work for an unchanged prompt prefix, so
  appending costs only new tokens; dropping old messages forces the whole prompt to be
  re-read (measured: 69 tokens/s, so a full 16k context takes about 4 minutes).
- **Compaction.** At 75% of the profile's context window the model writes notes for
  itself, and the context restarts from the system prompt, the goal, those notes and
  the current screen. Scripts survive regardless.
- **Screenshots** follow the tool results as a user message, only for the latest step
  (before and after), doubled in size. A profile without vision gets descriptions from
  a describer profile instead.

### Step boundaries

PyBoy queues button events until the next frame, and the queue isn't in save states
(which buttons are held is). So every step ends with `RecordingGame.end_step()`:
buttons still held are released, and if inputs are waiting one more frame runs. Both
are recorded. Without it, per-step checks pass but replaying a whole run diverges.

### Paid models

OpenRouter profiles are defined in `gb_agent/models.py`, but `gb_agent.play` refuses
them without `--allow-paid`. Tests use a scripted fake model.

## The run directory

Each run writes everything to one directory, under
`util.paths.data_path("gb_agent", "runs")`:

```
<run id>/
  manifest.json      # config, game and model profiles, start/end, which limit ended it
  events.jsonl       # every input and frame tick, tagged with step/agent/script version
  steps.jsonl        # every tool call: agent, args, trace, frame range, tokens
  progress.jsonl     # the profile's progress values after every step
  agents.jsonl       # agent and sub-agent turns: messages, reasoning, summaries
  blockers.jsonl
  frames/            # keyframe PNGs per step
  states/            # save state after each kept step
  library/           # the run's library, a git repo
  run.mp4            # rendered by the replay tool
```

**Inspecting the library.** Every script or sub-agent change is a commit in
`library/`, with the agent's reason as the message and agent, run and step in a
trailer. `git log`, `diff` and `blame` show how a script evolved and which step wrote
each line; the event log points at script versions, so a replay shows which version
of `walk_to` was running at any moment. Usage stats (calls, failures, frames) are
joined to versions, so you can see whether an edit helped.

**Watching.** A video from the replay tool to start with. The directory above is
designed as a watcher page's data source, so if things go well the page is just a
reader over these files, served on the tailnet behind Caddy like triage.

## Swappable model

The harness only ever sees a LangChain `BaseChatModel` plus a small **model profile**:

```python
@dataclass
class ModelProfile:
    name: str               # label used in logs and run metadata
    provider: str           # "local" (llama-server) or "openrouter"
    model: str              # model id at that provider
    base_url: str | None    # for local, e.g. http://127.0.0.1:8080/v1
    context_window: int     # tokens; drives how much history and trace is kept
    vision: bool            # can it take screenshots as images?
```

- Profiles live in one module (`gb_agent/models.py`), keyed by name, and the run
  command takes `--model <profile>`. Adding a model means adding a profile.
- OpenRouter profiles build their model through the existing `agents.config.get_llm`.
  Local ones point at llama-server's OpenAI-compatible API. Use `ChatDeepSeek`
  rather than `ChatOpenAI` for local reasoning models, since `ChatOpenAI` drops
  `reasoning_content`.
- `context_window` decides how much history is kept and how big traces are.
  The 2B currently runs with 16k, which fills quickly.
- If `vision` is false, screenshots reach the model as a text description from a
  separate vision profile. That lets a strong text-only coder be paired with a small
  local vision model.
- Sub-agents name their own profile, so a cheap model can handle simple jobs while a
  stronger one does the planning, or the other way round.
- Every run and sub-agent run records its profile, so models can be compared.

---

## Build order

Each chunk ends with passing tests (`uv run pytest tests/gb_agent`).

### Chunk 1: sandbox and its limits (done 2026-10-21)

- `gb_agent/sandbox/Dockerfile` (Python plus PyBoy, nothing else) and a host-side
  `run_in_sandbox(code, inputs) -> result` with every limit above.
- Tests that try to escape, each of which must fail cleanly: open a network
  connection, write outside the scratch space, read the home directory, read env
  vars, fork-bomb, allocate too much memory, loop forever, print endlessly.

### Chunk 2: recording, replay, clock, game profile (done 2026-10-21)

- `GameProfile` and the Silver profile, and creating Silver's start state with the
  clock locked from first boot. Silver starts in the bedroom after new-game setup:
  power-on plus a recorded list of setup inputs (`gb_agent/games/silver.py`).
- The determinism test: two runs from the same state with the same inputs give
  identical states.
- Read-only `RecordingGame`, the event log format, and the step runner (state in,
  state out). `run_step` never commits anything itself, so a test run is just a
  step whose result the caller throws away; the run loop (chunk 4) decides.
- The replay check after every step, with tests that bypass the wrapper and that
  write memory directly, both expected to be flagged.
- A replay tool that rebuilds a run and renders it to video.

### Chunk 3: scripts, library and traces (done 2026-10-21)

- The library git repo, script versions and commit messages, seeded from the game
  profile (including `hello_world.py`).
- Traces: screenshots, keyframes, input summary, watched-memory changes, notes,
  sized by a context budget.
- Script imports between library scripts, and usage stats per version.

### Chunk 4: the agent and experiments (done 2026-10-21)

- `ModelProfile`, the profiles module, and building a chat model from a profile.
- The tools above (except sub-agents), including `report_blocker`, and the agent
  loop (its own, not `agents.Agent`; see above).
- Experiment configs, the run loop with every limit, and the run directory.
- `python -m gb_agent.play --game silver --model <profile> --frames N --goal "..."`.

### Chunk 5: sub-agents (done 2026-10-21)

- `SubAgentSpec`, `define_subagent`, `run_subagent`, `list_subagents`.
- Tool-subset and depth checks, per-run budgets, sub-agent traces.

### Chunk 6: scripting tasks and comparison

A small set of tasks with checkable answers, run against any model profile, for
example:

- read the player's money and print it,
- close an open text box,
- write a `walk_to` script and use it to go from the bedroom to the stairs,
- fix a deliberately broken script given to it in the library.

Then `python -m gb_agent.compare`, to run one experiment config across several model
profiles. This is how the 2B gets a fair trial, and how models are compared.
