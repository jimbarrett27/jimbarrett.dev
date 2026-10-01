"""Push the Swedish word-of-the-day panel to its TRMNL private plugin.

The panel's markup lives in ``swedish/templates/swedish_full.liquid`` and is
pasted into the plugin's markup editor; keep the file the source of truth.

Push one manually::

    uv run python -m swedish.trmnl                # push the word that's up now
    uv run python -m swedish.trmnl --slot 2       # push a specific word of today's
    uv run python -m swedish.trmnl --dry-run      # print the payload, send nothing

Either form generates and stores today's words if they don't exist yet.
"""

import argparse
import logging

from gcp_util.secrets import get_trmnl_swedish_webhook_url
from util import trmnl

logger = logging.getLogger(__name__)


def push(merge_variables: dict) -> bool:
    """Send one word's variables to the Swedish plugin."""
    return trmnl.push(get_trmnl_swedish_webhook_url(), merge_variables)


def main() -> int:
    parser = argparse.ArgumentParser(description="Push the Swedish word panel to TRMNL.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the payload without sending it")
    parser.add_argument("--slot", type=int, help="which of today's words (default: by hour)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from swedish.daily_words import current_merge_variables

    merge_variables = current_merge_variables(slot=args.slot)
    if args.dry_run:
        print(trmnl.build_payload(merge_variables))
        return 0
    return 0 if push(merge_variables) else 1


if __name__ == "__main__":
    raise SystemExit(main())
