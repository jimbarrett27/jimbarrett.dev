# Devlog

Decisions and milestones for this repo, newest first. One `### entry` per decision or
milestone under a `## YYYY-MM-DD` date header — capture the *why*, not just the *what*.
Maintained via the `/devlog` skill. (Format mirrors `SignalAgents/RESEARCH_LOG.md`.)

## 2026-10-25

### gb_agent drops test runs and keeps all the agent's code; runs move to the 4 TB disk

Jim decided the agent should live with its actions: `test` is gone from `run_script`
and `run_code`, so every step that runs and verifies is kept and spends frames. The
test-streak note and the prompt's "try again with test=true" went with it
(`gb_agent/tools.py`, `run.py`, `agent.py`). Little is lost: across the last 15 runs,
0–4 calls per run were test runs. One-off code had the opposite problem. Gemma's long
runs made 128 and 172 `run_code` calls whose code existed only in the logs, so each
snippet is now committed to the run library's `snippets/stepNNNNN.py` before it runs,
and its version tags the step and its events. Snippets are never mounted or importable,
so they don't clutter `list_scripts`. Auto-saving was chosen over removing `run_code`,
which would have cost an extra call for every one-off. `press` and `wait` are
harness-written and aren't saved.

The default step timeout is now 300 s (it was 60 s). It only catches code that spins
without ticking, since the 600-frame cap stops everything else, and no step in any run
has ever hit it.

Runs, the ROM and start states now resolve through `gb_agent/paths.py`. Its
`GB_AGENT_DIR` takes precedence over `JIMBARRETT_DATA_DIR`, so the large, churning run
data can sit on `/mnt/storage` while the bots' SQLite stays on the NVMe. The 552 MB of
existing runs moved to `/mnt/storage/data/gb_agent`, and `~/.bashrc` exports the
variable. Until then the data had been landing inside the checkout, because interactive
shells never set a data dir. Giving the agent hints, such as its position, is next, but
the form it takes is still open for a longer discussion.

## 2026-10-22

### Six hour-long Gemma runs never leave the house; Haiku with notes reaches Route 29

With notes in place, Haiku 5.5 ran until the 4M-token cap (348 calls, ~36k frames,
45 minutes). It left the house, got Cyndaquil and Elm's errand to Mr. Pokémon, fought
battles in the grass, and reached the route west of New Bark Town. There it ran
out of tokens wandering below one-way ledges, looking for a way north. Its notes
were accurate throughout: controls, what blocked it, next steps. It wrote one `walk`
script, used it 212 times, and never defined a sub-agent.

A batch of six one-hour Gemma 4 26B runs (`gb_agent/runs/batch-20261022.sh`, ~65
calls an hour each, no compactions) never got out of the house: two never left the
bedroom and the other four only reached downstairs. Its notes are now honest ("stuck
in the bedroom… need to find the stairs"), so they fixed false memories but not
navigation. Gemma writes small movement scripts and once defined a sub-agent, but
doesn't use them to search systematically. So far the gap between models is spatial
reasoning from the screen, not the harness.

### gb_agent notes: persistent, and part of the routine rather than optional

The overnight Gemma run (7.8 h, 23 compactions) kept losing track of where it was:
its compaction summaries said "in my bedroom" while it was downstairs, and it went
between the two floors about 50 times. `update_notes` gives the main agent up to
2,000 characters of its own notes (`notes.md` in the run). They're shown word for
word after every compaction, and sub-agents can't change them. Gemma then never
called the tool in a 2-hour run, so notes became part of the loop
(`gb_agent/agent.py`): every 15 calls the harness asks for a notes update, and
compaction shows the current notes and asks for a rewrite, which becomes the new
notes. A model that never calls the tool still keeps notes.

Gemma's profile (`gb_agent/models.py`) now uses the 64k context the server gives it
and compacts at 0.4 of it (~26k). llama.cpp's sliding-window checkpoints keep
appended prompts cheap without `--swa-full`, but generation slows as the context
grows (13.6 → 4.3 tok/s).

## 2026-10-21

### gb_agent sub-agents, a 600-frame step cap, and help for small models

Chunk 5 is done (`gb_agent/subagents.py`). `define_subagent` saves a spec to
`subagents/<name>.json` in the run's library, committed and versioned like a script:
instructions, a subset of the parent's tools, the scripts it may run, and a model.
`run_subagent` runs it on one task with a fresh context, its own call and frame
allowance, and a `finish(summary)` tool. Only the summary, a few numbers and the
final screen go back to the parent, which keeps the parent's context small. Sub-agents
never get the sub-agent tools, so nesting stops at one level.

Gemma's blind exploration loops spent up to 1,400 frames in a single step and ran
through the 10,000-frame budget in 19 calls, so kept steps now stop at 600 frames
(`--step-frames`). Gemma never used sub-agents unprompted, so the opening message now
suggests them for long jobs like exploring a room. Both small local models failed
because they couldn't tell whether an action had done anything, so every report now
says how much of the screen changed (a turn in Silver is 0.5% of pixels, a one-tile
walk 26%), and tool results add a note after 3 identical calls in a row.

### First gb_agent runs: small local models stall, Claude Haiku 5.5 reaches Elm's lab

Four runs on Silver from the bedroom start, 10,000-frame budget:

| Model | Calls | Result |
|---|---|---|
| Qwen3-VL-2B (local) | 80 | never moved; no scripts; notes claimed false progress |
| Qwen3-VL-2B, script-first prompt | 66 | wrote `walk_left` (no frames between presses), ran it 38× unchanged |
| Qwen3-VL-8B Q4_K_M (local) | 86 | fixed one script error, then resubmitted identical code 51× |
| Claude Haiku 5.5 (OpenRouter, ~$0.12) | 99 | bedroom → downstairs (Pokégear, clock) → town → Elm's lab |

Both local models were defeated by Silver's turn-before-walk mechanic (a short tap in a
new direction only turns you), which shows up as a few changed pixels. Haiku wrote
`walk(direction, frames)` holding the button, which sidesteps it, plus `mash_a`, and
its compaction notes were accurate. The harness held up: every step verified, a whole
run replays, and the frame budget, not the model, ended Haiku's run. Fixes made along
the way: a tool call is requested in every reply (the 2B narrated half its turns);
compaction keeps the tools bound so llama-server reuses its cached prefix (314 s →
75 s); "Nothing saved" for identical rewrites; `press` takes `game.tap`'s parameter
names; one screenshot per step; local models compact at half their window because CPU
generation slows as the context grows (8B: ~140 s a call at 12k tokens); and the
manifest is saved after every call. llama-server's `--cache-ram` (8 GiB of old prompts
by default) is now capped at 2 GiB.

### gb_agent runs end to end: agent loop, tools, budgets, `gb_agent.play`

Chunk 4 is done. `python -m gb_agent.play --model qwen3-vl-2b-local` runs an
experiment into `<data dir>/gb_agent/runs/<run id>/`. The loop (`gb_agent/agent.py`)
is its own, not `agents.Agent`: llama-server reuses work for an unchanged prompt
prefix, and prompt reading on this CPU measured 69 tokens/s (a full 16k context takes
~4 minutes), so the context is append-only and compacts into the model's own notes at
75% of the window rather than sliding. In the first live run, calls after the first
took 3–10 s because of it. 16k is a choice in `run-vision-server.sh`, not a model or
RAM limit; CPU prompt speed is what makes bigger contexts impractical here.

Found by the whole-run replay test: PyBoy queues button events until the next frame
and doesn't save the queue, so a step ending on an input lost it at the boundary while
per-step checks still passed. `RecordingGame.end_step()` now releases held buttons and
runs one more frame when inputs are waiting. OpenRouter profiles exist but
`gb_agent.play` refuses them without `--allow-paid` (Jim: no paid runs without asking).

### gb_agent hints are off: the agent gets no memory addresses

While building chunk 3 (the script library and traces) I found Silver's map and
position addresses by watching memory while walking and taking the stairs (map group
`0xDA00`, number `0xDA01`, Y `0xDA02`, X `0xDA03`). Jim decided the agent doesn't get
them: they're `progress_values` in `gb_agent/games/silver.py`, read by the harness for
scoring and never shown, and traces only include memory the agent chose to watch. The
seed `hello_world` taps left and right and reads no memory. Handing over addresses
would test planning on top of known RAM; withholding them makes finding its own
position part of the task. A per-experiment hints switch can come later to compare.

Library design (`gb_agent/library.py`): one git repo per run, `library/<name>.py` per
script, imported in the sandbox as `library.<name>` so a script can't shadow a stdlib
module; versions are last-commit hashes; git runs with hooks off and a fixed identity
since the files are agent-written. Measured on the way: in Silver the first tap in a
new direction only turns the player, and holds over ~8 frames can start a second step.

### gb_agent recording and replay: every step is checked by replaying it on the host

Chunk 2 of `gb_agent/PLAN.md` is done. Scripts drive the game only through
`RecordingGame` (`gb_agent/emulator/`), which logs every press, release and frame
advance and has no memory writes. `gb_agent.steps.run_step` runs a script in the
sandbox from a save state and gets back the new state plus the events; the host then
replays the events from the starting state and requires a byte-identical state. A
script that reaches past `game` to press buttons or write memory gets its step marked
unverified. `gb_agent.replay.render_video` turns events into an MP4.

The replay check moved from "a second container" to the host: it runs no agent code,
only recorded inputs into a trusted ROM, so the only untrusted thing is the event list,
which `validate_events` checks first (a forged huge tick would otherwise hang the host).
The emulator package is copied into the image and the host and image pin the same
PyBoy/NumPy/Pillow, so the two agree exactly; a test asserts it.

Measured facts that shaped it: the rendered screen is stored in PyBoy save states, so
recording and replay share `apply_event` and every tick renders; a fresh boot stamps
wall-clock time into the clock state, so runs always start from a saved state (Silver's
is a power-on state, made once at `<data dir>/gb_agent/states/`); and PyBoy reads and
writes `.ram`/`.rtc` files next to a ROM given as a path, so ROMs go in as bytes. Tests
use `rtc3test.gb`, a public-domain MBC3 clock test ROM, so they don't need the Silver ROM.

### gb_agent sandbox: agent-written code runs in a throwaway, locked-down container

Chunk 1 of `gb_agent/PLAN.md` is done. `gb_agent.sandbox.run_in_sandbox` starts a fresh
container per call: no network, read-only root, a 64 MB noexec `/tmp`, uid 10001 with
every capability dropped and `no-new-privileges`, memory (no swap), CPU and process
caps, and a hard timeout that kills the container rather than just the CLI. Code and a
JSON payload go in on stdin and one marked result line comes back on stdout, so there
are no writable host mounts at all; read-only mounts (the ROM, later the library) are
opt-in. `tests/gb_agent/test_sandbox.py` tries each escape or abuse in turn and expects
a clean failure.

Three things learned the hard way. Docker's default log driver keeps everything a
container prints on disk, so runs use `--log-driver none`. The host must keep reading
container stdout even after its cap and throw the excess away: in the first version it
simply stopped reading, the pipe backed up, and `docker kill` hung indefinitely during
the stdout-flood test. And every housekeeping `docker` call now has a timeout, so a
wedged container can't hang the agent. Mounted files must be world-readable, since the
code doesn't run as Jim.

Found while planning chunk 2: PyBoy 2.7's real-time clock is compiled Cython reading
wall-clock time (`cimport time`), so it can't be faked from Python. The plan is
`rtc_lock_experimental(True)` from first boot, turned back on after every state load,
since the lock isn't saved in states. The cost is that Silver's time of day never moves.

## 2026-10-19

### Triage moves off Cloudflare onto the tailnet (triage.home.jimbarrett.dev)

Triage now lives at `https://triage.home.jimbarrett.dev`, served the same way as the
other home services: Caddy's `*.home` block, behind DNS-only records that point at
the Tailscale IP. Caddy proxies `/api/*` to the backend on `127.0.0.1:8077` and serves
everything else from a static build, falling back to `index.html`. Every device that
uses triage is on the tailnet, so the Cloudflare Tunnel, Cloudflare Access and the
`triage-api.jimbarrett.dev` host have nothing left to do. The UI and the API now
share one origin, which also drops CORS, `withCredentials`, and the Access identity
guard (`TRIAGE_REQUIRE_CF_ACCESS=false`). The guard's code stays, switched off.

**A separate Angular app, not the whole site with a redirect.** The UI moved from
`website/src/app/triage/` into a second workspace project,
`website/projects/triage/`, built with `ng build triage`. The other option was to
serve the full site build at home and redirect `/` to `/triage`. That would have
put the blog and publications on the home host, and still left the public site with
a triage route. The feature's only ties to the site were `environment.triageApiBase`
and the colour tokens; the new app carries a small slice of `styles.css` instead.
The public `/triage` route is gone entirely, with no "moved" stub.

**Defence in depth in Caddy.** The app has no login, and Caddy listens on every
interface, not just Tailscale. So the `@triage` matcher requires
`remote_ip 100.64.0.0/10` as well as the host. A request on the LAN IP with a forged
`Host` falls through to the wildcard's 404; this was checked. The cost is that the
Homepage tile has no `siteMonitor`: the container can reach neither the
localhost-bound backend nor the gated host.

**`deploy/deploy.sh`** replaces the three manual commands. It fetches and checks out
a detached `origin/main`, runs `npm ci` and `ng build triage`, rsyncs into
`/home/jim/data/triage-web`, and restarts the services. The rsync updates files in
place because Caddy bind-mounts that directory, and replacing it would leave the
mount on a stale inode. The script's body sits inside `main()` so that the checkout
can safely rewrite the running file. The Cloudflare pieces (the DNS record, the
tunnel, the Access app and `cloudflared`) are retired once the new route has been
verified end to end.

## 2026-10-09

### Handwritten notes: photos on the voice notes bot → vision model → Obsidian

The voice notes bot now also takes photos of handwritten pages. A photo, an image
sent as a file (full resolution), or an album becomes one note in
`Handwritten Notes/<YYYY-MM-DD HHMM>.md`: frontmatter, the transcription, then the
page images embedded from `images/`, kept so a better model can re-run over them
later. Album pages arrive as separate updates sharing a `media_group_id`, so they're
buffered and flushed by a `job_queue.run_once` 2.5 s after the first. Failure
handling copies voice notes: transcript in the chat before the vault write.

**Cloud, unlike voice notes.** The server has no GPU, and CPU handwriting OCR is
either line-level only (TrOCR) or a multi-billion-parameter VLM at minutes per page
and worse accuracy, so pages go to a vision model on OpenRouter with the existing key.

**Model chosen by a bake-off on five real pages**, picked to be hard: an arrow
carrying text back to the previous page, a crossed-out paragraph, a contingency
table with formulas, a page photographed sideways with no EXIF rotation, and names
with diacritics. Claude Sonnet 5.5 won: 3–9 s and ~1.2¢ a page, and its mistakes
are single letters in names ("Harmark", "Loca"), which proofreading catches.
Gemini 3.5 Flash was runner-up (best on names, and in the album it even moved the
arrowed sentence to where the arrow points) but silently dropped words, varied
run to run, and took ~20 s at ~3¢. GPT-5.6 Sol, Qwen3-VL and both DeepSeek vision
models were out: they transcribed crossed-out text, got formulas wrong, or garbled
the sideways page (one invented $\frac{1}{4}\pi r^3$). After the first round the
prompt gained paragraph reflow, LaTeX for maths and `[?]` for doubtful names and
numbers; Sonnet uses `[?]` only sometimes. Not yet exercised live in the bot.
Files: `handwritten_notes/`, `llm/llm_util.py` (`get_vision_response`), `main.py`;
`voice_notes/` helpers made public for reuse.

### Voice notes: Whistle → Whisper large-v3-turbo, and retry the Telegram download

First real use: three notes, deliberately using "verisimilitude". Two came back as
"very similar to …" and the third "timed out". The logs showed the timeout wasn't
transcription at all — `get_file` hit python-telegram-bot's 5 s default read timeout
and the model never ran. The download now gets 30 s per call and three attempts with
backoff on `NetworkError`, and a failed download says so instead of "Transcription
failed".

**Model choice from the saved recordings, not benchmarks.** The vault keeps each
note's audio, so both notes were re-run through Whistle and five Whisper sizes. In a
sentence, everything from small.en up got the word; spoken alone, only large-v3-turbo
did. Whistle got it only with keyword biasing, which needs the word in advance. Turbo
costs ~7 s for a short note and ~0.5× real time beyond that — thread count and beam
size barely move it — and 1.6 GB resident, so it loads at startup. Whisper splits long
audio itself, so the hand-rolled 30 s chunking is gone. The VAD filter stays (silence
transcribes to nothing), but with `speech_pad_ms=1000`: the default padding clipped a
lone "verisimilitude" to "Verisimilar-tude". Note frontmatter now records
`model: whisper-large-v3-turbo`.

### Voice notes bot: Telegram voice note → local transcript → Obsidian

MVP of a voice-capture loop. A new bot (`TELEGRAM_VOICE_NOTES_BOT_KEY`) takes voice
notes or audio files, transcribes them on the server, replies with the transcript and
writes `Voice Notes/<YYYY-MM-DD HHMM>.md` (frontmatter + audio embed + transcript) plus
the original audio under `Voice Notes/audio/` into the vault. `obsidian-sync.service`
already syncs `/mnt/storage/data/obsidian`, so the bot only writes files. Keeping the
audio is deliberate: the planned LLM step can re-run over the source later.

**Cactus Whistle, not Whisper.** 17 MB, CPU-only, Apache-2.0. Its benchmarks are all
Apple M4 and the PyPI package is a pure-Python wrapper that downloads a native engine
from Hugging Face, so Linux x86_64 was spiked first: it works, 11 s of speech in
~0.8 s. Its hard limit is 30 s per pass. The library's `stream()` handles any length
but re-decodes a sliding window, so it ran at ~0.7× real time (32 s for 47 s); cutting
at the quietest 100 ms in the last 5 s before each 30 s boundary and transcribing the
pieces did 57 s in 3.9 s with nothing lost or doubled at the seams. The cost is slightly
lighter punctuation across a seam. Telemetry is anonymous counts but off anyway
(`NEEDLE_TELEMETRY=0`).

**Nothing gets lost.** The transcript is sent before the vault write, so a failed save
still leaves it in the chat. Files are written via hidden temp + rename so `ob sync`
never picks up half a note. The unit now has `RequiresMountsFor=/mnt/storage`, since
the vault sits on the `nofail` mount. Files: `voice_notes/audio.py`,
`voice_notes/transcribe.py`, `voice_notes/vault.py`, `voice_notes/voice_notes_bot.py`,
`main.py`, `gcp_util/secrets.py`, `deploy/telegram-bot.service.example`.

## 2026-10-01

### Swedish word-of-the-day panel on TRMNL, drawn from the flashcard deck

A third TRMNL panel, replacing the official Swedish word-of-the-day app, whose words
were too simple. Four words a day from `flashcards.db`, rotated hourly: word huge,
translation, then a Swedish example sentence with its English beneath. Same shape as
the fitness panel — data webhook, Liquid template in the repo, alert-once job on the
notify bot.

**Selection leans hard, then lets the LLM judge interest.** The deck is mostly the
seeded word lists, so a uniform draw would surface "en katt" as often as "en klippa".
Cards are weighted by FSRS difficulty squared (unreviewed ones at the deck's mean, ~5,
so they still appear), 16 are sampled without replacement, and one LLM call picks the
four most interesting and writes the glosses. Difficulty knows what *this* learner
struggles with but not what's dull; the LLM covers the second half. Anything shown in
the last 60 days is excluded.

**Generated once, then only read.** Words land in a new `daily_words` table keyed
`(date, slot)`; the first push of a Stockholm day generates, every later one is a
lookup. The slot is `hour % 4`, so rotation needs no state and survives restarts. The
production `flashcards.db` turned out never to have been alembic-stamped (`upgrade
head` tries to recreate `flashcards`), so migration `002` exists for completeness but
it's `init_db()`'s `create_all` at bot startup that actually creates the table. The
PNG preview is unverified: the server has no Chrome. Files: `swedish/daily_words.py`,
`swedish/daily.py`, `swedish/trmnl.py`, `swedish/preview.py`,
`swedish/templates/swedish_full.liquid`, `swedish/prompts/daily_words.jinja2`,
`swedish/orm_models.py`, `swedish/database.py`, `gcp_util/secrets.py`, `main.py`.

## 2026-09-18

### Fitness panel on TRMNL, and the meme panel rebuilt on the data webhook

Added a second TRMNL panel — CTL/ATL/form from intervals.icu, pushed at 09:00 and
21:00 — and in doing so rebuilt the meme panel from the 11th on a different
strategy. Both now go through `util/trmnl.py`, and both have their layout in a
Liquid template that TRMNL renders.

**Why the meme panel changed strategy.** The image webhook is passthrough: we
hand over a finished PNG, so everything on the panel has to be baked into it. The
fitness panel wanted live text — big numerals, a headline — rendered at native
resolution rather than dithered along with a photograph, which means TRMNL's own
renderer, which means the *data* webhook. Once the meme panel followed, it could
carry the source HN headline as real text beside the picture, which is what earns
back the white space a square meme leaves on a 5:3 screen.

**The cost, and it is the one the 11th leaned away from.** A data webhook carries
2KB, so the picture can no longer travel with the payload: it is dithered, pushed
to a public-read GCS object (`personal-website-318015-trmnl`, dated names to
defeat caching), and only its URL is sent. That is the public-object shape the
11th's entry set aside as "the right shape for anything the *website* computes;
this isn't that". Reintroducing it buys live text and adaptive layout; it costs a
publicly readable meme a day. Worth it here, but it *is* the trade that was
previously declined, not a free upgrade.

**Layout follows aspect ratio.** Five of the six meme templates are wide. Fitting
those beside a headline column scaled them to ~56%, and since a meme's caption is
burned into the picture, the caption became unreadable. Wide memes now fill the
panel with a one-line footer; square ones keep the column. Everything lands at
84-97%, with a test holding the floor at 80%.

**Two things only a render would have told us.** The fitness panel's y-axis was
inherited pinned at 100 from its design mockup, which draws a CTL in the teens as
a flat line along the floor — it is chosen from the data now. And TRMNL rejects
bit-depth-1 PNGs with "Unsupported image format" despite listing PNG as
supported, so the dither is stored at 8 bits: identical pixels, bigger file.

**How the old plugin died.** The 11th's image plugin was deleted during this work
on the assumption it was a stale leftover — the meme panel had landed on `main`
while the branch in hand predated it, so a grep found nothing and `main` was
never checked. Both earlier `TRMNL_MEME_WEBHOOK_URL` versions now 404. Nothing
was lost beyond the plugin itself, but the lesson is cheap: check `main`, not the
working branch, before concluding a feature does not exist.

Files: `fitness/` (new), `memes/eink.py`, `memes/storage.py`, `memes/trmnl.py`
(rewritten), `util/trmnl.py`, `util/panel_preview.py`, `main.py`. The meme job
also moves from weekdays to daily, since a weekday-only job left Friday's meme on
the wall all weekend.

## 2026-09-11

### Daily meme lands on the TRMNL e-ink panel (push, not poll)

Bought a TRMNL — an 800x480 1-bit e-ink display — and the daily HN meme was the
obvious first thing to put on it. `send_daily_hn_meme` now POSTs the same PNG it
sends to Telegram at TRMNL's Image Webhook plugin, inside its own try/except: the
panel is a bonus surface, and a failed push must not read as a failed meme.

**Why push and not a polling plugin.** TRMNL's other private-plugin strategies
have *them* fetch a URL from *us*, which would mean exposing an endpoint. The
natural host would be the triage FastAPI backend, but it sits behind Cloudflare
Access, which TRMNL's poller can't authenticate against without a service token
and a bypass policy — and it would make the home server's uptime a dependency of
a screen on the wall. A webhook push from the job that already runs adds no
inbound surface at all. (A polling plugin over a public GCS object, tapestry
style, stays the right shape for anything the *website* computes; this isn't
that.)

**Why we dither locally.** The image webhook is passthrough storage — no
server-side fitting or dithering — so `memes/trmnl.py` does the whole conversion:
greyscale, autocontrast, contain-fit onto a white 800x480 canvas, then PIL's
Floyd-Steinberg. Autocontrast is the non-obvious part: e-ink has no midtones to
spend, and without stretching the range first a dithered photo turns into uniform
grey noise. Letterboxed rather than cropped, because the panel is much wider than
a meme template and a crop usually eats the punchline. A real render comes out
~40KB, far inside the 5MB / 12-uploads-an-hour limits.

The webhook URL is the only credential TRMNL has, so it lives in Secret Manager
as `TRMNL_MEME_WEBHOOK_URL` alongside the bot tokens; `TRMNL_MEME_WEBHOOK_URL` in
the environment overrides it, for pointing a local run at a throwaway plugin.
Files: `memes/trmnl.py` (new, plus a `python -m memes.trmnl --preview` CLI),
`memes/daily_hn_meme.py`, `gcp_util/secrets.py`, `tests/memes/test_trmnl.py`.

## 2026-06-08

### Triage decision + status cleanup (collapse keep-decisions, split auto_rejected)

Three changes after some days of real triage use, driven mainly by wanting clean,
separable labels for a future supervised relevance model. Full spec:
`triage/SPEC-decision-status-cleanup.md`. Built chunk-by-chunk through the
worker/reviewer ensemble.

**Why.** (1) In practice there was no real difference between the `deep` and
`filed` keep-decisions, so the depth choice was just friction producing noisy
labels. (2) The Obsidian stubs gave no signal for which kept papers had actually
been read. (3) "pending" was badly overloaded — 1051 of 1088 "pending" rows were
LLM-screened-out (score 0) papers that never appear in the queue, conflated with
the 37 genuinely awaiting a human decision. Those 1051 are *weak/LLM* negatives;
the 204 `dismissed` are *human* negatives — they must be separate label classes.

**What.** `status` vocabulary is now `pending | kept | dismissed | auto_rejected`
(legacy `deep`/`filed` migrated to `kept`; still rendered if any survive).
- Decision collapsed to `kept` (→ Zotero **and** Obsidian) + `dismissed`.
  `Decision` literal, routing sets, and the Zotero tag (`triage/kept`) updated.
- Obsidian stubs now write to `<inbox>/unread/`; a sibling `read/` folder is
  moved into manually by the user — the app never touches it.
- Screener now inserts non-relevant papers as `auto_rejected` at ingest (not
  `pending`); `get_decided_papers` (History) excludes `pending`+`auto_rejected`.
  `suggested_depth` left untouched — it's a feature, not a label.
- Frontend: single **Keep** button (keys `d`/`f`), depth-hint badge removed.

**Data migration (Alembic rev 004, applied to live DB after backup).** Result
exactly as expected: `kept` 23, `dismissed` 204, `auto_rejected` 1051,
`pending` 37. Downgrade is intentionally lossy (can't recover deep vs filed).

**Zotero backfill (`triage/backfill.py`, one-off).** Pushed the 15 keyless `kept`
papers (12 ex-`filed` that had been Obsidian-only + 3 ex-`deep` whose earlier
push had failed with a transient `'itemType' not provided`). All 23 `kept` papers
now have both a `zotero_key` and an `obsidian_path`; zero failures.

NOTE: requires restarting **both** `telegram_bot` (scanner ingest change) and
`triage-backend` (triage API), plus an Angular rebuild + App Engine redeploy.
The ~23 pre-existing Obsidian stubs keep their old `triage/deep|filed` frontmatter
in the `Papers/` root (cosmetic; the DB — the training data — is clean).
