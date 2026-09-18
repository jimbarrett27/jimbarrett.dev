"""Scheduler hooks for pushing the fitness panel to TRMNL.

Cadence is set by how often the underlying numbers actually move, not by how
often the device redraws. CTL and ATL change once a day, when intervals.icu
recomputes them after the overnight Garmin sync; activities land during the day.
So a morning push carries the new fitness figures and a late-evening push catches
whatever was trained. Both are timed to the sync rather than the clock: the watch
uploads once its owner is up and about, and training happens after work. Two a
day sits far inside TRMNL's twelve-an-hour ceiling.

Pushing is not the same as displaying: TRMNL holds the data and the device picks
it up on its own refresh, so the panel updates at the device's cadence, not this
job's.

Unlike the tapestry, a missed push costs nothing permanent -- the panel simply
shows older numbers until the next one -- so this notifies only on failure.
"""

import asyncio
import logging

from telegram.ext import ContextTypes

from fitness import trmnl
from fitness.metrics import collect

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 15 * 60
MAX_RUNS_PER_DAY = 3


def refresh_panel() -> bool:
    """Fetch the latest metrics and push them. Blocking; call off the event loop."""
    return trmnl.push(collect())


async def fitness_panel_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduler hook: refresh the TRMNL panel in a worker thread.

    Fetching from intervals.icu and posting to TRMNL are both blocking network
    calls, so they run off the event loop. A failure retries a couple of times --
    long enough to ride out a transient outage -- and only then says so, because
    a Telegram ping on every successful push twice a day is just noise.
    """
    run = (context.job.data or {}).get("run", 1) if context.job else 1
    try:
        if await asyncio.to_thread(refresh_panel):
            logger.info("TRMNL fitness panel refreshed (run %d)", run)
            return
        raise RuntimeError("TRMNL rejected the push")
    except Exception:
        logger.exception("Failed to refresh TRMNL fitness panel (run %d)", run)
        if run < MAX_RUNS_PER_DAY and context.job_queue:
            context.job_queue.run_once(
                fitness_panel_task, when=RETRY_DELAY_SECONDS, data={"run": run + 1}
            )
            logger.info("Retrying fitness panel in %d minutes", RETRY_DELAY_SECONDS // 60)
        else:
            context.bot_data["minecraft_bot"].send_message_to_me(
                f"📉 TRMNL fitness panel failed after {run} attempts — panel is stale"
            )
