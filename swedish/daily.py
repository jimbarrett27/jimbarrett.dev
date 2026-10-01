"""Scheduler hook for rotating the Swedish word panel on TRMNL.

Runs hourly. Each run pushes whichever of the day's words is up
(:func:`swedish.daily_words.current_slot`); the first run of a Stockholm day
also generates that day's words. As with the fitness panel, the device picks the
push up on its own refresh, so its refresh interval should be an hour or less
for the rotation to show.

A missed push just leaves the previous word up for another hour, so failures
are reported only once they persist -- the same alert-once shape as
:mod:`fitness.daily`.
"""

import asyncio
import logging
from datetime import timedelta

from telegram.ext import ContextTypes

from swedish import trmnl
from swedish.daily_words import current_merge_variables
from util.timezone import stockholm_now

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 60 * 60
# Three consecutive failures at an hourly interval: three words skipped.
ALERT_AFTER_FAILURES = 3
FAILURES_KEY = "swedish_panel_consecutive_failures"


def seconds_to_next_hour() -> float:
    """Delay until just past the next top of the hour, so pushes line up with slots."""
    now = stockholm_now()
    next_hour = now.replace(minute=0, second=5, microsecond=0) + timedelta(hours=1)
    return (next_hour - now).total_seconds()


def refresh_panel() -> bool:
    """Ensure today's words exist and push the current one. Blocking."""
    return trmnl.push(current_merge_variables())


async def swedish_panel_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduler hook: push the current word in a worker thread, alerting once on outages."""
    failures = context.bot_data.get(FAILURES_KEY, 0)
    notify = context.bot_data["minecraft_bot"].send_message_to_me
    try:
        if not await asyncio.to_thread(refresh_panel):
            raise RuntimeError("TRMNL rejected the push")
    except Exception:
        failures += 1
        context.bot_data[FAILURES_KEY] = failures
        logger.exception("Failed to refresh TRMNL Swedish panel (%d in a row)", failures)
        if failures == ALERT_AFTER_FAILURES:
            notify(f"🇸🇪 TRMNL Swedish panel has failed {failures} times in a row — panel is stale")
        return

    context.bot_data[FAILURES_KEY] = 0
    logger.info("TRMNL Swedish panel refreshed")
    if failures >= ALERT_AFTER_FAILURES:
        notify("🇸🇪 TRMNL Swedish panel is updating again")
