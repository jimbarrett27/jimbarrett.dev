"""Scheduler hook for pushing the fitness panel to TRMNL.

The panel is refreshed on a short fixed interval rather than at hand-picked times.
CTL/ATL move when intervals.icu recomputes them after the watch syncs, and
activities land whenever training happens -- neither is predictable enough to
time pushes around, and each refresh is only two intervals.icu reads plus one
webhook post. Every ``REFRESH_INTERVAL_SECONDS`` sits well inside TRMNL's
twelve-an-hour ceiling.

Pushing is not the same as displaying: TRMNL holds the data and the device picks
it up on its own refresh, so the panel updates at the device's cadence, not this
job's. Pushing more often than that just means the device always finds fresh data.

A missed push costs nothing permanent -- the panel shows older numbers until the
next one -- and the next scheduled run is itself the retry. So a failure is only
reported once it has persisted for ``ALERT_AFTER_FAILURES`` runs in a row, once,
with a single follow-up when pushes recover.
"""

import asyncio
import logging

from telegram.ext import ContextTypes

from fitness import trmnl
from fitness.metrics import collect

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 30 * 60
# Four consecutive failures at a 30-minute interval: about two hours stale.
ALERT_AFTER_FAILURES = 4
FAILURES_KEY = "fitness_panel_consecutive_failures"


def refresh_panel() -> bool:
    """Fetch the latest metrics and push them. Blocking; call off the event loop."""
    return trmnl.push(collect())


async def fitness_panel_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduler hook: refresh the TRMNL panel in a worker thread.

    Fetching from intervals.icu and posting to TRMNL are both blocking network
    calls, so they run off the event loop. Consecutive failures are counted in
    ``bot_data`` so an outage pings once when it crosses the threshold, not on
    every run while it lasts.
    """
    failures = context.bot_data.get(FAILURES_KEY, 0)
    notify = context.bot_data["minecraft_bot"].send_message_to_me
    try:
        if not await asyncio.to_thread(refresh_panel):
            raise RuntimeError("TRMNL rejected the push")
    except Exception:
        failures += 1
        context.bot_data[FAILURES_KEY] = failures
        logger.exception("Failed to refresh TRMNL fitness panel (%d in a row)", failures)
        if failures == ALERT_AFTER_FAILURES:
            notify(f"📉 TRMNL fitness panel has failed {failures} times in a row — panel is stale")
        return

    context.bot_data[FAILURES_KEY] = 0
    logger.info("TRMNL fitness panel refreshed")
    if failures >= ALERT_AFTER_FAILURES:
        notify("📈 TRMNL fitness panel is updating again")
