# Devlog

Decisions and milestones for this repo, newest first. One `### entry` per decision or
milestone under a `## YYYY-MM-DD` date header — capture the *why*, not just the *what*.
Maintained via the `/devlog` skill. (Format mirrors `SignalAgents/RESEARCH_LOG.md`.)

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
