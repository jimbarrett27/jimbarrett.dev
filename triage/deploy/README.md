# Triage — deployment runbook

The triage app is reachable only on the tailnet, at
**https://triage.home.jimbarrett.dev**. It's served the same way as the other home
services: a host in the `*.home` block of Caddy (`~/docker/caddy/Caddyfile`), with
DNS-only `*.home` records pointing at the server's Tailscale IP.

```
browser (on tailnet) ──https──▶ Caddy :443 ─┬─ /api/*  ──▶ triage-backend  127.0.0.1:8077
                                            └─ else    ──▶ /srv/triage  (static UI, SPA fallback)
```

- **One origin.** The UI and the API share a host, so there's no CORS, no
  cross-origin cookie, and no `TRIAGE_ALLOWED_ORIGINS`.
- **No login.** Being on the tailnet is the access control. As defence in depth,
  the Caddy matcher also requires `remote_ip 100.64.0.0/10` (the Tailscale range).
  A request that reaches Caddy any other way, for example by a LAN IP with a forged
  `Host`, falls through to the wildcard's 404.
- The backend binds localhost, so Caddy is its only ingress.

> **History:** until October 2026 the UI was the `/triage` route of
> jimbarrett.dev on App Engine. It called `triage-api.jimbarrett.dev` cross-origin,
> through a Cloudflare Tunnel gated by Cloudflare Access. The backend's
> `TRIAGE_REQUIRE_CF_ACCESS` guard from that setup was removed in November 2026.

## Pieces

| Piece | Where |
|---|---|
| Backend unit | `/etc/systemd/system/triage-backend.service` (from `triage-backend.service.example`) |
| Backend env | `/etc/triage.env`. A tracked copy is `triage.env`; the template is `triage.env.example` |
| UI source | `website/projects/triage/`, a separate Angular app in the website workspace |
| UI build | `/home/jim/data/triage-web`, written by `deploy/deploy.sh` and bind-mounted into Caddy at `/srv/triage` |
| Caddy | `~/docker/caddy/Caddyfile` (`@triage` block) and `compose.yaml` (the volume) |
| Homepage tile | `~/docker/homepage/config/services.yaml`, "Research" group |

## Deploying

Run `deploy/deploy.sh` (see `deploy/README.md`). It moves the deploy checkout to
`origin/main`, rebuilds the UI into `/home/jim/data/triage-web` and restarts the
backend. Caddy needs no reload for a new UI build, because it serves straight from
the mount.

## First-time setup (already done; for rebuilding the box)

```bash
sudo cp triage/deploy/triage.env /etc/triage.env
sudo cp triage/deploy/triage-backend.service.example \
        /etc/systemd/system/triage-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now triage-backend
curl -s localhost:8077/healthz       # {"status":"ok"}
deploy/deploy.sh                     # builds the UI into /home/jim/data/triage-web
(cd ~/docker/caddy && docker compose up -d)   # recreate if the volume is new
```

## Verify

- `https://triage.home.jimbarrett.dev/` loads the queue.
- `https://triage.home.jimbarrett.dev/api/triage/queue` returns JSON.
- Off the tailnet: `curl -k --resolve triage.home.jimbarrett.dev:443:<LAN IP> https://triage.home.jimbarrett.dev/`
  returns `Unknown service` (404).

---

## Zotero credentials (build step 7)

`deep` decisions push the paper into your personal Zotero library. Both
credentials live in GCP Secret Manager (matching the Telegram bot's secrets), so
the backend fetches them at push time and nothing sensitive sits in the env file:

1. **API key** — create at <https://www.zotero.org/settings/security> →
   *Applications* (needs read/write to your personal library):
   ```bash
   printf %s 'PASTE_KEY' | gcloud secrets create ZOTERO_API_KEY \
     --project=personal-website-318015 --data-file=-
   # later rotations: gcloud secrets versions add ZOTERO_API_KEY --data-file=-
   ```
2. **User ID** — the numeric *userID* shown on that same settings page:
   ```bash
   printf %s 'NUMERIC_USER_ID' | gcloud secrets create ZOTERO_USER_ID \
     --project=personal-website-318015 --data-file=-
   ```

Enable pushing with `TRIAGE_ZOTERO_ENABLED=true` in `/etc/triage.env` (empty/false
disables it — dev default). A push failure is recorded on the row (`zotero_error`)
and never blocks the decision; the step-8 retry loop re-attempts. Idempotent via
the stored `zotero_key`.
