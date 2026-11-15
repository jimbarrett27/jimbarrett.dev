"""Runtime configuration for the triage backend, sourced from the environment.

Kept deliberately small. Secrets (the Zotero API key) are not held here — they
are fetched from GCP Secret Manager at use time; only non-secret identifiers and
toggles live in this dataclass.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Only papers the screener scored strictly above this make it into the
    # triage queue. The screener sets non-relevant papers to 0.0, so the
    # default of 0.0 selects exactly the "surfaced" papers.
    min_relevance_score: float = 0.0

    # Bind address. In production Caddy on the same host proxies /api here, so
    # binding to localhost is fine.
    host: str = "127.0.0.1"
    port: int = 8077

    # How long after a decision the user may still undo it.
    undo_window_seconds: int = 30

    # --- Cloudflare Access (defence in depth) ---
    # When enabled, every /api/triage request must carry a
    # Cf-Access-Authenticated-User-Email header matching `allowed_email`.
    # Off by default. Production no longer uses it either: the app is now only
    # reachable over Tailscale, not through Cloudflare.
    require_cf_access: bool = False
    allowed_email: str = ""

    # Origins permitted by CORS. Empty (the production setting) disables it: Caddy
    # serves the UI and the API from the same origin.
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)

    # --- Obsidian ---
    # Filesystem path to the Obsidian vault root on jim-server (or a folder that
    # syncs into it). Empty disables stub writing.
    obsidian_vault: str = ""
    # Vault-relative folder stubs are written into.
    obsidian_inbox_subdir: str = "literature/inbox"

    # --- Zotero ---
    # Whether to push `deep` papers to Zotero. Both the user ID and the API key
    # are fetched from GCP Secret Manager (ZOTERO_USER_ID / ZOTERO_API_KEY) at
    # push time, so only this toggle lives here. Off by default (local/dev).
    zotero_enabled: bool = False

    # --- reMarkable (via Drive) ---
    # Whether kept papers are sent to the tablet: an open-access PDF with a
    # screening cover page, uploaded to reMarkable/Papers/To read in the photos
    # account's Drive (token from Secret Manager). Off by default (local/dev).
    drive_enabled: bool = False

    # --- Routing retry loop (step 8) ---
    # A background task re-attempts routing for papers whose Zotero/Obsidian
    # push failed. Off in tests/dev; the systemd service enables it.
    routing_retry_enabled: bool = True
    # How often the loop scans for due retries.
    routing_retry_interval_seconds: int = 60
    # Exponential backoff base: the n-th retry waits base * 2**(n-1) seconds,
    # capped at one hour (see retry.py). Give up after this many attempts.
    routing_retry_base_seconds: int = 60
    routing_max_attempts: int = 6


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def get_settings() -> Settings:
    """Build settings from environment variables (with sensible defaults)."""
    return Settings(
        min_relevance_score=float(
            os.environ.get("TRIAGE_MIN_RELEVANCE_SCORE", "0.0")
        ),
        host=os.environ.get("TRIAGE_HOST", "127.0.0.1"),
        port=int(os.environ.get("TRIAGE_PORT", "8077")),
        undo_window_seconds=int(os.environ.get("TRIAGE_UNDO_WINDOW_SECONDS", "30")),
        require_cf_access=os.environ.get("TRIAGE_REQUIRE_CF_ACCESS", "false").lower()
        in ("1", "true", "yes"),
        allowed_email=os.environ.get("TRIAGE_ALLOWED_EMAIL", ""),
        allowed_origins=_csv(os.environ.get("TRIAGE_ALLOWED_ORIGINS", "")),
        obsidian_vault=os.environ.get("TRIAGE_OBSIDIAN_VAULT", ""),
        obsidian_inbox_subdir=os.environ.get(
            "TRIAGE_OBSIDIAN_INBOX_SUBDIR", "literature/inbox"
        ),
        zotero_enabled=os.environ.get("TRIAGE_ZOTERO_ENABLED", "false").lower()
        in ("1", "true", "yes"),
        drive_enabled=os.environ.get("TRIAGE_DRIVE_ENABLED", "false").lower()
        in ("1", "true", "yes"),
        routing_retry_enabled=os.environ.get(
            "TRIAGE_ROUTING_RETRY_ENABLED", "true"
        ).lower()
        in ("1", "true", "yes"),
        routing_retry_interval_seconds=int(
            os.environ.get("TRIAGE_ROUTING_RETRY_INTERVAL_SECONDS", "60")
        ),
        routing_retry_base_seconds=int(
            os.environ.get("TRIAGE_ROUTING_RETRY_BASE_SECONDS", "60")
        ),
        routing_max_attempts=int(os.environ.get("TRIAGE_ROUTING_MAX_ATTEMPTS", "6")),
    )
