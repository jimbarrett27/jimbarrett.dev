# Deploying the Python side

The bots and the triage backend run on the home server under systemd. Each unit
runs `uv run` against a checkout, so **deploying is mostly moving that checkout**.
The one build step is the triage UI: a static Angular build that Caddy serves
(see `triage/deploy/README.md`).

## The two directories

| Path | Purpose |
|---|---|
| `/home/jim/deploy/jimbarrett.dev` | What the services run. Detached at `origin/main`. Not for editing. |
| `/home/jim/repos/jimbarrett.dev` | Ordinary working checkout on the server. Break it freely. |

They are separate clones rather than git worktrees on purpose: a worktree's
`.git` is a file pointing into the other repo, so a `git gc`, a move or an
interrupted operation in the dev checkout would reach into the tree a running
service is executing from. A clone is self-contained, and detached HEAD gives it
no branch to drift onto.

This split exists because it already went wrong once: production ran for two
months from a feature branch left checked out in the deploy directory, picked up
by a reboot rather than by any decision to deploy it.

## Deploying

```sh
/home/jim/repos/jimbarrett.dev/deploy/deploy.sh
```

[`deploy.sh`](deploy.sh) does four things:

1. Fetches and moves the deploy checkout to a detached `origin/main`.
2. Runs `npm ci` and `ng build triage` in its `website/`.
3. Syncs `dist/triage/browser/` into `/home/jim/data/triage-web`. It syncs in
   place rather than replacing the directory, because Caddy bind-mounts it.
4. Restarts `telegram-bot` and `triage-backend`. This asks for your sudo password.
   It also restarts the `gb-agent` user unit, if it's installed (no sudo; see below).

Then check it came up, and confirm which commit is live:

```sh
systemctl status telegram-bot triage-backend
git -C /home/jim/deploy/jimbarrett.dev log --oneline -1
journalctl -u telegram-bot -n 50 --no-pager
```

## Runtime data

Databases and state files live in `$JIMBARRETT_DATA_DIR` (`/home/jim/data` on the
server), set by each unit — **not** in the checkout. That is what makes the
deploy clone disposable. See `util/paths.py`.

Moving the data elsewhere is one variable: point `JIMBARRETT_DATA_DIR` at the new
location and restart. If you move it under `/mnt/storage`, add
`RequiresMountsFor=/mnt/storage` to the unit — that filesystem is mounted
`nofail`, and SQLite responds to a missing path by creating a new empty database
rather than failing, so the bot would come up healthy with no history.

## Scheduled jobs

Apart from the gb_agent oracle timer (below), there are no cron jobs or systemd
timers. Everything periodic is a
`job_queue.run_daily(...)` or `run_repeating(...)` registered in `main.py`, inside
the bot process. So
"did the job run?" is answered with `journalctl -u telegram-bot`, and a job that
isn't in the deployed commit simply never fires — silently, since nothing else
knows it should have.

## Voice notes and the Obsidian vault

The voice notes bot (`voice_notes/`) writes transcripts and their audio into
`$OBSIDIAN_VAULT_DIR/Voice Notes/`. On the server that is the vault
`obsidian-sync.service` keeps in sync (`/mnt/storage/data/obsidian`), so a note
reaches the other devices without the bot knowing anything about Obsidian Sync.
Because the vault is on the `nofail` mount, the unit carries
`RequiresMountsFor=/mnt/storage`.

Transcription runs locally with Whisper large-v3-turbo via `faster-whisper`
(CPU, int8). The weights are downloaded from Hugging Face the first time the bot
starts, then cached under `~/.cache/huggingface`. The model is loaded at startup
and stays resident: it adds about 1.6 GB to the bot process. Expect ~7 s for a
short note and about half real time for long ones (a 1-minute note ≈ 30 s).

## Handwritten notes

The same bot also takes photos of handwritten notes (`handwritten_notes/`). A single
photo, an image sent as a file, or an album of pages becomes one note in
`$OBSIDIAN_VAULT_DIR/Handwritten Notes/`, with the page images under `images/`.
Unlike voice notes, transcription is **not** local: the pages are sent to a vision
model on OpenRouter (`handwritten_notes.transcribe.MODEL`), using the existing
OpenRouter key, so no new secret is needed.

Flowcharts and plots sketched on a page are redrawn into the note (Mermaid and SVG,
`handwritten_notes/figures.py`), and previewed in the chat as PNGs. The flowchart
preview renders Mermaid in headless Chromium via Playwright, which needs a one-off
browser install for the `jim` user (it lands in `~/.cache/ms-playwright`, so it
survives re-cloning the deploy directory):

    uv run playwright install chromium-headless-shell

Without it, flowchart previews are skipped (logged) and everything else still works.

## Chess panel

`chess_panel/` pushes the ongoing chess.com Daily game between `jimjimjimmyjim`
and `naslundx` to **two** TRMNL private plugins, one on each of our accounts, each
with the board from its owner's side. The game comes from chess.com's public API,
so there is no chess.com credential; the only secrets are the two webhook URLs:

| Secret | Plugin |
|---|---|
| `TRMNL_CHESS_WEBHOOK_URL_JIMJIMJIMMYJIM` | mine |
| `TRMNL_CHESS_WEBHOOK_URL_NASLUNDX` | his |

Each plugin is a webhook-strategy private plugin with
`chess_panel/templates/chess_full.liquid` pasted in as its full-screen markup, and
optionally `chess_half_vertical.liquid` in its Half Vertical tab for mashups (same
data, so nothing else changes). A
player whose secret doesn't exist yet is skipped with a warning, so either panel
can go live first. To add one:

    printf '%s' "$WEBHOOK_URL" | gcloud secrets create TRMNL_CHESS_WEBHOOK_URL_NASLUNDX \
        --project=personal-website-318015 --replication-policy=automatic --data-file=-

The job pushes every 15 minutes from the bot process, like the other panels. Check
by hand with `uv run python -m chess_panel.trmnl --dry-run`.

## The Pokemon agent (gb_agent)

The agent plays around the clock under two **user** units. They're user units
because the model server it plays against, `llama-server`, is one, and they need no
sudo. Lingering is on, so they start at boot. Like the bot, they run from the
deploy clone.

| Unit | What it does |
|---|---|
| `gb-agent.service` | `python -m gb_agent.autoplay`: plays the series in `$GB_AGENT_DIR/autoplay.json`, resuming from the last kept step on every start |
| `gb-agent-oracle.timer` → `.service` | At 06:00 and 18:00 Stockholm time, `python -m gb_agent.oracle` writes a DeepSeek commentary to the bucket's `oracle.json` for the page |

Install from the `.example` files here into `~/.config/systemd/user/`, then:

```sh
systemctl --user daemon-reload
systemctl --user enable --now gb-agent gb-agent-oracle.timer
```

`autoplay.json` (in `/mnt/storage/data/gb_agent`) is the switch:
`{"model": "qwen3.6-35b-a3b-local", "start": null}`. A null `start` begins a new
game from the bedroom, and the first run's id is written back. Without the file,
the unit exits and stays stopped. To start over, set `start` back to null and
restart.

```sh
systemctl --user status gb-agent
journalctl --user -u gb-agent -n 50 --no-pager      # starts, resumes, stops
ls -t /mnt/storage/data/gb_agent/runs/live-*.out | head -1   # the run's own output
systemctl --user list-timers gb-agent-oracle.timer
systemctl --user start gb-agent-oracle               # a commentary now
```
