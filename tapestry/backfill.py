"""One-off: regenerate stored tapestry panels' artwork with the current model/prompt.

Re-runs the generator over panels already in GCS, reusing each day's stored
stories so only the *artwork* changes (same news, new rendering). Panels are
regenerated oldest-first and each one is given the freshly regenerated previous
panel as its ``previous_svg``, so the seams actually join across the run.

``--since`` regenerates only the tail of the tapestry, which is the usual case:
the first regenerated day is seeded with the *stored* SVG of the last day being
kept, so the new run stitches onto the existing panels at that seam instead of
starting from a blank slate.

Overwrites the canonical panels in place, but first copies the artwork it's
replacing into ``alt/`` (see :mod:`tapestry.storage`), so a model experiment can
always be looked at again -- or reverted -- afterwards. Safe to re-run. Needs the
same GCP + LLM credentials as the daily job:

    uv run python -m tapestry.backfill --since 2026-07-14
"""

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from tapestry import storage
from tapestry.generator import DEFAULT_MODEL, PROMPT_TEMPLATE, generate_panel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main(model: str = DEFAULT_MODEL, since: str | None = None, archive: bool = True) -> None:
    """Regenerate stored panels' artwork with ``model``, reusing each day's stories.

    ``since`` (YYYY-MM-DD) limits the run to panels on or after that date; by
    default every stored panel is regenerated.

    Unless ``archive`` is false, each panel being replaced is first copied into
    ``alt/`` (keyed by the model *and* prompt that drew it) so the artwork it's
    overwriting stays viewable. A panel already drawn by this same model and
    prompt isn't archived -- there'd be nothing to distinguish the copy from its
    replacement -- which also makes re-running a backfill idempotent.
    """
    index = storage.read_index()
    if not index or not index["dates"]:
        print("No panels to backfill")
        return

    dates = sorted(index["dates"])  # oldest first: the order the seams join in
    targets = [d for d in dates if since is None or d >= since]
    if not targets:
        print(f"No panels on or after {since}; nothing to backfill")
        return

    # Seed from the last panel we're keeping so the first regenerated day joins
    # the existing tapestry at that seam. None => regenerating from the very top.
    kept = [d for d in dates if d < targets[0]]
    previous_svg = previous_plan = None
    if kept:
        seed = storage.read_panel(kept[-1])
        previous_svg, previous_plan = seed["svg"], seed.get("plan")
        print(f"Seeding from kept panel {kept[-1]}")

    prompt_template = Path(PROMPT_TEMPLATE).read_text()
    target_variant = storage.panel_variant(model, prompt_template)

    for date in targets:
        existing = storage.read_panel(date)
        stories = existing["stories"]
        existing_variant = storage.panel_variant(
            existing.get("model"), existing.get("prompt_template")
        )

        if archive and existing_variant != target_variant:
            variant = storage.archive_panel(date)
            print(f"Archived {date}'s existing panel as alt '{variant}'")

        panel = generate_panel(
            stories,
            previous_svg=previous_svg,
            model=model,
            day=date,
            previous_plan=previous_plan,
        )
        storage.write_panel({
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "plan": panel.plan,
            "prompt_template": prompt_template,
            "stories": stories,
            "svg": panel.svg,
        })
        previous_svg, previous_plan = panel.svg, panel.plan
        print(f"Regenerated panel for {date} with {model}")

    print(f"Backfill complete: {len(targets)} panel(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since", help="only regenerate panels on or after this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"model to draw with (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--no-archive",
        dest="archive",
        action="store_false",
        help="overwrite panels without keeping the replaced artwork as an alternate",
    )
    args = parser.parse_args()
    main(model=args.model, since=args.since, archive=args.archive)
