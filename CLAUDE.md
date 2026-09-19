# CLAUDE.md

Personal monorepo: a Python automation/bot codebase at the root, plus the
`jimbarrett.dev` Angular site under `website/`.

## Python (root)

- Always use `uv` for running Python commands (e.g. `uv run python ...`, `uv run pytest ...`).
- One project, `pyproject.toml` at the root; every package below is a top-level import.
- Tests live in `tests/`, run with `uv run pytest`.

| Path | What it is |
|---|---|
| `telegram_bot/`, `swedish/`, `minecraft/`, `diary/`, `photos/`, `memes/`, `dnd/` | Telegram bot surfaces, one per bot |
| `triage/` | FastAPI backend for the paper-triage app — serves the `/triage` UI in `website/` |
| `tapestry/` | Daily news-tapestry generator; writes SVG panels to GCS, rendered by the tapestry page in `website/` |
| `content_screening/` | Paper discovery/screening pipeline feeding `triage/` |
| `llm/`, `agents/`, `gcp_util/`, `util/` | Shared helpers |

## Runtime data

The SQLite databases and state files the bots write (`content_screening.db`,
`flashcards.db`, `dnd.db`, `diary/entries/`, `memes/recent_templates.json`) are
**not** part of the checkout. Resolve their paths through `util.paths`
(`data_path`, `sqlite_url`) rather than relative to the cwd or `__file__`.

`JIMBARRETT_DATA_DIR` points that at a stable location; the server sets it so the
deploy clone stays disposable. Unset — dev and tests — everything resolves to the
repo root, exactly where these files have always lived. Alembic honours the same
variable via each `migrations/env.py`, so migrations and the app never disagree
about which file they mean.

## Website (`website/`)

Angular 21 SPA deployed to Google App Engine. See `website/CLAUDE.md` for the full
picture — content pipeline, routing, deploy. Node is managed via nvm, so npm/ng are
only on PATH in an nvm-activated shell.

## The cross-cutting bit

Two features span both halves of this repo, and their contracts are the thing most
likely to break:

- **triage** — `triage/schemas.py` (FastAPI response models) ↔ `website/src/app/triage/models/paper.model.ts`
- **tapestry** — the panel JSON written by `tapestry/storage.py` ↔ `website/src/app/core/models/tapestry.interface.ts`

They still **deploy independently** (backend: systemd + Cloudflare Tunnel on the home
server; frontend: Cloud Build → App Engine on merge to main), so the two sides can
briefly skew even though they now land in one commit. Keep frontend reads of API
fields defensive.

## Builds

Cloud Build triggers are path-filtered to `website/**`, and the build steps `dir:` into
`website/`. A change to the Python side does not deploy the site.
