# Devlog

Decisions and milestones for this repo, newest first. One `### entry` per decision or
milestone under a `## YYYY-MM-DD` date header — capture the *why*, not just the *what*.
Maintained via the `/devlog` skill. (Format mirrors `SignalAgents/RESEARCH_LOG.md`.)

## 2026-10-09

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
