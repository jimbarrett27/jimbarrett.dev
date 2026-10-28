#!/usr/bin/env bash
# Deploy origin/main to the home server: move the deploy checkout, rebuild the
# triage UI that Caddy serves, and restart the services (including the gb_agent
# user unit, if installed). See deploy/README.md.
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

    sudo systemctl restart telegram-bot triage-backend
    # The Pokemon agent is a user unit: no sudo. A restart resumes its series from
    # the last kept step. Skipped if it isn't installed.
    if systemctl --user cat gb-agent.service >/dev/null 2>&1; then
        systemctl --user restart gb-agent
        systemctl --user --no-pager status gb-agent | grep -E '^●|Active:'
    fi

    systemctl --no-pager status telegram-bot triage-backend | grep -E '^●|Active:'
    git -C "$DEPLOY_DIR" log --oneline -1
}

main "$@"
