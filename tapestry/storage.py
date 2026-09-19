"""GCS storage for the news tapestry: one JSON blob per daily panel plus a manifest.

The website (a separate, GCP-hosted repo) reads these public objects directly by
URL, so this layout *is* the website's contract:

    tapestry/index.json          -- manifest: geometry, the list of available
                                    dates, and any alternate renderings
    tapestry/panels/<date>.json  -- one day: model, prompt template, the three
                                    stories (title/summary/link), and the panel SVG
    tapestry/alt/<date>/<variant>.json
                                 -- same shape, but an *alternate* rendering of
                                    that day (a different model's take on the
                                    same stories), kept so a day can be redrawn
                                    without losing the previous artwork

Panels are stored per-day (a 1600x200 section), never as one growing stitched
image -- the website reassembles a window of panels client-side using the
geometry in the manifest. Objects are public-read, so no auth is needed to fetch
them from the browser.

``tapestry/panels/<date>.json`` is always the canonical tapestry: the site can
render the whole thing without ever touching ``alt/``. Alternates are listed in
the manifest under ``alternates`` (``{date: [variant, ...]}``) so the site can
offer a "show me the other model's version of this day" toggle by fetching
``alt/<date>/<variant>.json``; a manifest with no ``alternates`` key simply means
no day has one.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from google.cloud import storage

from tapestry.svg import OVERLAP, PANEL_HEIGHT, PANEL_WIDTH

logger = logging.getLogger(__name__)

PROJECT_ID = "personal-website-318015"
BUCKET_NAME = "personal-website-318015-tapestry"
INDEX_BLOB = "tapestry/index.json"
PANEL_BLOB = "tapestry/panels/{date}.json"
ALT_PANEL_BLOB = "tapestry/alt/{date}/{variant}.json"


def _bucket():
    return storage.Client(project=PROJECT_ID).bucket(BUCKET_NAME)


def read_index() -> dict | None:
    """Return the manifest, or ``None`` if the tapestry hasn't been seeded yet."""
    blob = _bucket().blob(INDEX_BLOB)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text())


def read_panel(date: str) -> dict:
    """Return the stored panel dict (stories + svg) for ``date`` (YYYY-MM-DD)."""
    blob = _bucket().blob(PANEL_BLOB.format(date=date))
    return json.loads(blob.download_as_text())


def model_variant(model: str) -> str:
    """Slugify a model id into an alternate's variant name.

    ``anthropic/claude-opus-4.7`` -> ``anthropic-claude-opus-4.7``.
    """
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")


def panel_variant(model: str | None, prompt_template: str | None) -> str:
    """Name the alternate slot for artwork drawn by ``model`` from ``prompt_template``.

    A rendering is identified by both: the same model draws very differently from
    a different prompt, which is exactly the case a redraw usually wants to keep
    the old artwork for. Keying on the model alone would make such a redraw
    archive over the very panel it was replacing, or (in ``backfill``) skip
    archiving altogether because the model looked unchanged.

    Deterministic, so re-archiving the same day+model+prompt rewrites the same
    object rather than piling up copies -- which is what keeps a re-run of
    ``backfill`` idempotent.
    """
    slug = model_variant(model or "unknown")
    fingerprint = hashlib.sha1((prompt_template or "").encode()).hexdigest()[:7]
    return f"{slug}-{fingerprint}"


def read_alt_panel(date: str, variant: str) -> dict:
    """Return an alternate rendering of ``date``, as named in the manifest."""
    blob = _bucket().blob(ALT_PANEL_BLOB.format(date=date, variant=variant))
    return json.loads(blob.download_as_text())


def archive_panel(date: str) -> str | None:
    """Copy the canonical panel for ``date`` into ``alt/``, keyed by its rendering.

    Call this before overwriting a day whose artwork is worth keeping. Returns
    the variant name written (see :func:`panel_variant`), or ``None`` if there's
    no canonical panel to archive. The alternate is registered in the manifest so
    the site can find it.
    """
    blob = _bucket().blob(PANEL_BLOB.format(date=date))
    if not blob.exists():
        return None

    panel = json.loads(blob.download_as_text())
    variant = panel_variant(panel.get("model"), panel.get("prompt_template"))
    alt = _bucket().blob(ALT_PANEL_BLOB.format(date=date, variant=variant))
    alt.upload_from_string(json.dumps(panel), content_type="application/json")
    _register_alt(date, variant)
    logger.info("Archived %s panel as alternate '%s'", date, variant)
    return variant


def write_panel(panel: dict) -> None:
    """Upload one day's panel JSON, keyed by its ``date``."""
    blob = _bucket().blob(PANEL_BLOB.format(date=panel["date"]))
    blob.upload_from_string(json.dumps(panel), content_type="application/json")
    logger.info("Uploaded tapestry panel for %s (%d bytes)", panel["date"], len(panel["svg"]))


def _write_index(index: dict) -> None:
    """Stamp and upload the manifest."""
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    blob = _bucket().blob(INDEX_BLOB)
    blob.upload_from_string(json.dumps(index), content_type="application/json")


def _load_index_for_update() -> dict:
    """Return the manifest to mutate, creating an empty one the first time."""
    return read_index() or {
        "geometry": {
            "panel_width": PANEL_WIDTH,
            "panel_height": PANEL_HEIGHT,
            "overlap": OVERLAP,
        },
        "dates": [],
    }


def update_index(date: str) -> None:
    """Append ``date`` to the manifest (creating it the first time)."""
    index = _load_index_for_update()
    if date not in index["dates"]:
        index["dates"].append(date)
    _write_index(index)
    logger.info("Updated tapestry manifest: %d panels", len(index["dates"]))


def _register_alt(date: str, variant: str) -> None:
    """Record that ``date`` has an alternate rendering named ``variant``."""
    index = _load_index_for_update()
    alternates = index.setdefault("alternates", {})
    variants = alternates.setdefault(date, [])
    if variant not in variants:
        variants.append(variant)
    _write_index(index)
