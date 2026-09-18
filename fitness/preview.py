"""Render the fitness panel locally. See :mod:`util.panel_preview`.

    uv run --extra dev python -m fitness.preview
"""

import argparse
import json
import logging
from pathlib import Path

from util import panel_preview, trmnl

TEMPLATE = Path(__file__).parent / "templates" / "fitness_full.liquid"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("panel-preview/fitness"))
    parser.add_argument("--json", type=Path, help="also write the webhook payload here")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from fitness.metrics import collect

    merge_variables = collect().as_merge_variables()
    payload = trmnl.build_payload(merge_variables)
    if args.json:
        args.json.write_text(payload)
    panel_preview.preview(TEMPLATE, merge_variables, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
