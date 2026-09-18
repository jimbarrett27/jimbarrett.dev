"""Push the fitness panel to its TRMNL private plugin.

The panel's markup lives in ``fitness/templates/fitness_full.liquid`` and is
pasted into the plugin's markup editor; keep the file the source of truth,
because the editor is a preview surface and will happily drift from the repo.

Push one manually::

    uv run python -m fitness.trmnl            # push live metrics
    uv run python -m fitness.trmnl --dry-run  # print the payload, send nothing
"""

import argparse
import logging

from gcp_util.secrets import get_trmnl_fitness_webhook_url
from util import trmnl

logger = logging.getLogger(__name__)


def push(metrics) -> bool:
    """Send the metrics to the fitness plugin."""
    return trmnl.push(get_trmnl_fitness_webhook_url(), metrics.as_merge_variables())


def main() -> int:
    parser = argparse.ArgumentParser(description="Push the fitness panel to TRMNL.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the payload without sending it")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from fitness.metrics import collect

    metrics = collect()
    if args.dry_run:
        print(trmnl.build_payload(metrics.as_merge_variables()))
        return 0
    return 0 if push(metrics) else 1


if __name__ == "__main__":
    raise SystemExit(main())
