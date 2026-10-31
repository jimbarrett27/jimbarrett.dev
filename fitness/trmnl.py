"""Push the fitness and power panels to their TRMNL private plugins.

Each panel's markup lives in ``fitness/templates/<panel>_full.liquid`` and is
pasted into its plugin's markup editor; keep the files the source of truth,
because the editor is a preview surface and will happily drift from the repo.

The power plugin's webhook secret may not exist yet; as with the chess panel,
that skips the push with a warning rather than failing the run, so the job can
deploy before the plugin is set up.

Push one manually::

    uv run python -m fitness.trmnl                  # push live fitness metrics
    uv run python -m fitness.trmnl --panel power    # push the power curve
    uv run python -m fitness.trmnl --dry-run        # print the payload, send nothing
"""

import argparse
import logging

from google.api_core.exceptions import NotFound

from gcp_util.secrets import get_trmnl_fitness_webhook_url, get_trmnl_power_webhook_url
from util import trmnl

logger = logging.getLogger(__name__)


def push(metrics) -> bool:
    """Send the metrics to the fitness plugin."""
    return trmnl.push(get_trmnl_fitness_webhook_url(), metrics.as_merge_variables())


def push_power(panel) -> bool:
    """Send the power curve to its plugin, skipping if it isn't set up yet."""
    try:
        webhook = get_trmnl_power_webhook_url()
    except NotFound:
        logger.warning("no TRMNL_POWER_WEBHOOK_URL secret yet; skipping the power panel")
        return True
    return trmnl.push(webhook, panel.as_merge_variables())


def main() -> int:
    parser = argparse.ArgumentParser(description="Push a fitness panel to TRMNL.")
    parser.add_argument("--panel", choices=("fitness", "power"), default="fitness")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the payload without sending it")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.panel == "power":
        from fitness.power import collect
        send = push_power
    else:
        from fitness.metrics import collect
        send = push

    data = collect()
    if args.dry_run:
        print(trmnl.build_payload(data.as_merge_variables()))
        return 0
    return 0 if send(data) else 1


if __name__ == "__main__":
    raise SystemExit(main())
