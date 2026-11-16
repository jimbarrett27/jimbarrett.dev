#!/usr/bin/env bash
# Deploy origin/main to the home server: move the deploy checkout, rebuild the
# triage UI that Caddy serves, and restart the services. See deploy/README.md.
#
# Everything lives in main(), so bash has parsed the whole script before the
# checkout below rewrites this file underneath it.
set -euo pipefail

DEPLOY_DIR=/home/jim/deploy/jimbarrett.dev
# Static triage UI, bind-mounted read-only into the Caddy container. Synced in
# place rather than replaced, so the mount keeps pointing at the live files.
TRIAGE_WEB_DIR=/home/jim/data/triage-web

main() {
    git -C "$DEPLOY_DIR" fetch origin
    git -C "$DEPLOY_DIR" checkout --detach origin/main

    # nvm is a shell function, not a binary, so it has to be sourced here.
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # shellcheck source=/dev/null
    . "$NVM_DIR/nvm.sh"
    (
        cd "$DEPLOY_DIR/website"
        npm ci --no-audit --no-fund
        npx ng build triage
    )
    mkdir -p "$TRIAGE_WEB_DIR"
    rsync -a --delete-after --delay-updates \
        "$DEPLOY_DIR/website/dist/triage/browser/" "$TRIAGE_WEB_DIR/"

    # Bring the screening DB schema up to date before anything restarts against it:
    # the new code's ORM expects the new columns. A no-op when already at head. One
    # rolling backup, taken only when there is something to apply.
    (
        cd "$DEPLOY_DIR/content_screening"
        export JIMBARRETT_DATA_DIR=/home/jim/data
        current=$(uv run alembic current 2>/dev/null | awk '{print $1}')
        head=$(uv run alembic heads 2>/dev/null | awk '{print $1}')
        if [ "$current" != "$head" ]; then
            cp "$JIMBARRETT_DATA_DIR/content_screening.db" \
                "$JIMBARRETT_DATA_DIR/content_screening.db.pre-migration"
            echo "Migrating content_screening.db: ${current:-none} -> $head"
            uv run alembic upgrade head
        fi
    )

    sudo systemctl restart telegram-bot triage-backend

    systemctl --no-pager status telegram-bot triage-backend | grep -E '^●|Active:'
    git -C "$DEPLOY_DIR" log --oneline -1
}

main "$@"
