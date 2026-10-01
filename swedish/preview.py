"""Render the Swedish word panel locally. See :mod:`util.panel_preview`.

    uv run --extra dev python -m swedish.preview            # the word that's up now
    uv run --extra dev python -m swedish.preview --slot 3   # a specific one of today's

Generates and stores today's words if they don't exist yet, exactly as a push would.
"""

import argparse
import logging
from pathlib import Path

from util import panel_preview, trmnl

TEMPLATE = Path(__file__).parent / "templates" / "swedish_full.liquid"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("panel-preview/swedish"))
    parser.add_argument("--slot", type=int, help="which of today's words (default: by hour)")
    parser.add_argument("--json", type=Path, help="also write the webhook payload here")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from swedish.daily_words import current_merge_variables

    merge_variables = current_merge_variables(slot=args.slot)
    payload = trmnl.build_payload(merge_variables)
    if args.json:
        args.json.write_text(payload)
    panel_preview.preview(TEMPLATE, merge_variables, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
