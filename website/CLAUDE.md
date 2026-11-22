# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in
`website/`. It is scoped to this directory — see the repo-root `CLAUDE.md` for the
Python side and for the triage/tapestry contracts that span both.

All paths and commands below are relative to `website/`.

## What this is

Personal website (jimbarrett.dev) — an Angular 21 single-page app deployed as static files to **Google App Engine**. Standalone-component architecture (no NgModules), all routes lazy-loaded. Most of the site is content-driven (home, publications, blog). The workspace also holds a second, separate application, `triage`, which is **not** part of jimbarrett.dev (see below).

## Commands

```bash
npm start              # ng serve website — dev server on :4200
npm run start:triage   # ng serve triage — the triage app on :4200, proxies /api → local backend
npm run build          # ng build website — runs the prebuild markdown step first, output to dist/website/browser
npm run build:triage   # ng build triage — output to dist/triage/browser
npm run watch          # dev build in watch mode
npm run lint           # ng lint (eslint) — CI gate, must be green before deploy
npx ng test            # unit tests (Karma); note: components are scaffolded with skipTests, so coverage is sparse
node build-scripts/process-markdown.js   # regenerate blog JSON without a full build
node build-scripts/process-puzzles.js    # regenerate puzzle JSON (AoC + Euler) without a full build
```

`build` is the production configuration by default (`defaultConfiguration: production` in angular.json), which applies bundle budgets and the environment file replacement. There is no separate lint config — eslint flat config lives in `eslint.config.js` (TS + Angular template rules; `app` selector prefix enforced).

### Node / nvm gotcha
Node is managed via **nvm**, so `npm`/`node`/`ng` are only on PATH inside an nvm-activated shell. If a command fails with "command not found", source nvm first (`. "$NVM_DIR/nvm.sh"`). This also bites systemd-style contexts that don't inherit the nvm PATH. If `node_modules` looks stale relative to `package.json`, run `npm install` before building.

## Content pipeline (blog)

Blog posts are **authored as markdown** in `content/blog/*.md(x)` with gray-matter frontmatter. They are **not** read at runtime. The `prebuild` npm hook runs `build-scripts/process-markdown.js`, which converts each post to `src/assets/blog/<slug>.json` (full HTML via `marked`, GFM on) plus an `index.json` summary sorted newest-first. The app fetches those JSON files at runtime via `core/services/blog.service.ts`.

Implication: **editing a `.md` file does nothing until the prebuild script runs.** `npm run build` runs it automatically; for `ng serve` you must re-run `node build-scripts/process-markdown.js` (or restart) to see content changes.

## Content pipeline (puzzles)

Advent of Code and Project Euler solutions are Python in the repo root (`../advent_of_code/yYYYY/day_NN.py`, `../project_euler/problem_NNN.py`). `prebuild` also runs `build-scripts/process-puzzles.js`, which writes `src/assets/puzzles/index.json` (years, days, stars; solved Euler problems) and one JSON per solution with its source. A part counts as solved when its function body is more than the template's `pass`. Euler problems above 100 are never exported: Project Euler only permits publishing the first hundred.

Unlike the blog JSON, this output is **gitignored**; it is wholly derived and rebuilt on every build. Same `ng serve` caveat: re-run the script to see changes.

## Routing & structure

- `src/app/app.routes.ts` — root routes, every entry lazy via `loadComponent`. Pages live under `src/app/pages/<name>/`. Shared chrome (header/footer) is in `src/app/shared/components/`; cross-cutting services in `src/app/core/services/`.
- `app.config.ts` wires `provideRouter` + `provideHttpClient` (standalone bootstrap, no AppModule).

## The triage app (`projects/triage/`)

A second application in this workspace, sharing `node_modules`, lint config and Angular version with the site but nothing else: its own `main.ts`, `index.html`, `styles.css` (a slice of the site's tokens and reset) and routes, with the queue at `/`. It reuses only the Comic Shanns font from `src/assets/fonts` and `public/favicon.ico`.

- **Not deployed to App Engine.** It is served on the tailnet at `https://triage.home.jimbarrett.dev` by the home server's Caddy, which serves the static build and proxies `/api/*` to the FastAPI backend on `127.0.0.1:8077`. Same origin, no CORS, no auth: Caddy only answers that host for Tailscale addresses.
- **Build/deploy:** `deploy/deploy.sh` at the repo root runs `ng build triage` in the deploy checkout and syncs `dist/triage/browser/` into `/home/jim/data/triage-web`, which Caddy bind-mounts. See `deploy/README.md`.
- **Dev:** `npm run start:triage`; the API base is the relative `/api/triage` and `proxy.conf.json` forwards `/api` to the local backend.
- Writes pass data as query params with an empty body; that's the shape the backend endpoints take. Keep reads of API fields defensive (optional chaining): backend and frontend deploy separately and can briefly skew.

## Deploy

Deployment is GCP **Cloud Build → App Engine** (`app.yaml` serves `dist/website/browser` statically with SPA fallback to `index.html`).
- `infrastructure/deploy.yml` — `npm ci` → `npm run build` → `gcloud app deploy`, triggered on merge to `main`.
- `infrastructure/pull_requests.yml` — `npm ci` → `npm run lint` → `npm run build` on PRs.

So: **push site changes to a branch, merge to main to trigger the deploy.** A change is only live on jimbarrett.dev after that build completes. (The triage app is not part of this pipeline.)
