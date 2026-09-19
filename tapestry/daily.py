"""Generate and store one daily tapestry panel, plus the scheduler hook for it.

``generate_next_panel`` is the shared core used by both the one-off bootstrap
(:mod:`tapestry.bootstrap`) and the daily job below: it reads the previous panel
so the new one continues the seam, fetches today's stories, generates the panel,
and uploads it to GCS with the manifest.
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from telegram.ext import ContextTypes

from tapestry import storage
from tapestry.generator import (
    DEFAULT_MODEL,
    PROMPT_TEMPLATE,
    STORIES_PER_PANEL,
    generate_panel,
)
from tapestry.news import fetch_bbc_stories

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 30 * 60
MAX_RUNS_PER_DAY = 3


def select_stories(exclude_links: set[str] = frozenset()) -> list[dict]:
    """Pick this panel's stories from the BBC feed, skipping ``exclude_links``.

    Fetches the whole feed (not just the top three) so that after dropping
    yesterday's stories there are still fresh ones to choose from. Falls back to
    the top stories only in the pathological case where filtering leaves too few.
    """
    candidates = fetch_bbc_stories()
    fresh = [s for s in candidates if s["link"] not in exclude_links]
    chosen = fresh[:STORIES_PER_PANEL]
    if len(chosen) < STORIES_PER_PANEL:
        logger.warning(
            "Only %d fresh stories after dedup; falling back to top stories", len(chosen)
        )
        chosen = candidates[:STORIES_PER_PANEL]
    return chosen


def generate_next_panel(day: str | None = None, model: str = DEFAULT_MODEL) -> str | None:
    """Generate the next tapestry panel and store it in GCS.

    ``day`` defaults to today (YYYY-MM-DD). Returns the date written, or ``None``
    if a panel for that day already exists (so the job is safe to re-run). Stories
    used by the previous panel are excluded so consecutive days don't repeat a
    story, and the prompt template used is saved alongside the panel for
    provenance. The model used and its stated plan are recorded on the panel.

    The previous panel supplies two things to the new one: its bottom-edge colours
    (so the seam joins) and its plan (so today's foreground knows what it reaches
    up into). Its artwork is deliberately *not* passed on -- see
    :func:`tapestry.generator.generate_panel`.
    """
    day = day or date.today().isoformat()
    index = storage.read_index()

    if index and day in index["dates"]:
        logger.info("Tapestry panel for %s already exists; skipping", day)
        return None

    previous_svg = previous_plan = None
    previous_links: set[str] = set()
    if index and index["dates"]:
        previous = storage.read_panel(index["dates"][-1])
        previous_svg = previous["svg"]
        previous_plan = previous.get("plan")
        previous_links = {s["link"] for s in previous["stories"]}

    stories = select_stories(exclude_links=previous_links)
    panel = generate_panel(
        stories,
        previous_svg=previous_svg,
        model=model,
        day=day,
        previous_plan=previous_plan,
    )

    storage.write_panel({
        "date": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "plan": panel.plan,
        "prompt_template": Path(PROMPT_TEMPLATE).read_text(),
        "stories": [dict(s) for s in stories],
        "svg": panel.svg,
    })
    storage.update_index(day)
    return day


async def daily_tapestry_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduler hook: generate today's panel in a worker thread.

    The generation does blocking network + LLM work, so it runs off the event
    loop. On success it pings the user via the notify bot.

    A failed run reschedules itself (up to ``MAX_RUNS_PER_DAY`` runs in total) so
    an outage at the scheduled hour doesn't cost the day -- ``generate_next_panel``
    is idempotent, so a retry after a late success is a no-op. Once the retries
    are spent the user is told, rather than the day just going quietly missing.
    """
    run = (context.job.data or {}).get("run", 1) if context.job else 1
    try:
        day = await asyncio.to_thread(generate_next_panel)
        if day:
            context.bot_data["minecraft_bot"].send_message_to_me(
                f"🧵 News tapestry updated for {day}"
            )
    except Exception:
        logger.exception("Failed to generate daily tapestry panel (run %d)", run)
        if run < MAX_RUNS_PER_DAY and context.job_queue:
            context.job_queue.run_once(
                daily_tapestry_task, when=RETRY_DELAY_SECONDS, data={"run": run + 1}
            )
            logger.info("Retrying tapestry in %d minutes", RETRY_DELAY_SECONDS // 60)
        else:
            context.bot_data["minecraft_bot"].send_message_to_me(
                f"🧵 News tapestry failed after {run} attempts — no panel today"
            )
