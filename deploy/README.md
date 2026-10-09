# Deploying the Python side

The bots and the triage backend run on the home server under systemd. There is
no build step and no artefact: each unit runs `uv run` against a checkout, so
**deploying is moving that checkout**.

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
git -C /home/jim/deploy/jimbarrett.dev fetch origin
git -C /home/jim/deploy/jimbarrett.dev checkout --detach origin/main
sudo systemctl restart telegram-bot triage-backend
```

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

There are no cron jobs or systemd timers. Everything periodic is a
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
