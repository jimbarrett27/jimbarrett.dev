"""Push the daily meme to its TRMNL private plugin.

Push one manually (generates a fresh meme, so it costs an LLM call)::

    uv run python -m memes.trmnl

The image cannot travel in the webhook -- 2KB of JSON against a few hundred KB of
pixels -- so the flow is: dither it (:mod:`memes.eink`), upload it
(:mod:`memes.storage`), then send the resulting URL here for TRMNL's renderer to
fetch. The markup lives in ``memes/templates_trmnl/meme_full.liquid``.

Pushing is best-effort by design. The Telegram meme is the thing that must not
break, so callers should treat a failure here as a stale panel, not a failed day.
"""

import argparse
import logging
from datetime import date

from gcp_util.secrets import get_trmnl_meme_webhook_url
from memes import eink, storage
from util import trmnl

logger = logging.getLogger(__name__)

# The headline is the only free text on the panel and the column is narrow, so
# cap it rather than let a long title push the footer off the screen.
MAX_HEADLINE_CHARS = 110


def _headline(story: dict | None) -> str:
    if not story:
        return "Today's front page"
    title = story.get("title", "")
    if len(title) > MAX_HEADLINE_CHARS:
        return title[: MAX_HEADLINE_CHARS - 1].rstrip() + "…"
    return title


def push_meme(image_bytes: bytes, story: dict | None = None, day: date | None = None) -> bool:
    """Dither, upload and push the meme. Returns whether TRMNL accepted it."""
    prepared = eink.prepare(image_bytes)
    url = storage.upload_meme(prepared.png, day=day)
    return trmnl.push(get_trmnl_meme_webhook_url(), {
        "meme_url": url,
        "meme_width": prepared.width,
        "meme_height": prepared.height,
        "layout": prepared.layout,
        "headline": _headline(story),
        "day": (day or date.today()).isoformat(),
        "points": (story or {}).get("points") or "",
        "comments": (story or {}).get("comments") or "",
    })


def push_todays_meme() -> bool:
    """Generate a meme from today's front page and push it. Costs an LLM call.

    The scheduled job pushes the same image it sends to Telegram, so the two
    always agree. Running this by hand makes a *new* meme, which will therefore
    differ from whatever Telegram received today.
    """
    from memes.daily_hn_meme import (
        build_meme_prompt, fetch_hn_stories, get_excluded_templates, pick_story,
        record_template_use,
    )
    from memes.generator import generate_meme

    stories = fetch_hn_stories()
    image_bytes, template, agent_text = generate_meme(
        build_meme_prompt(stories), exclude_templates=get_excluded_templates(),
    )
    record_template_use(template)
    logger.info("generated meme from template %s", template)
    return push_meme(image_bytes, pick_story(stories, agent_text))


def main() -> int:
    argparse.ArgumentParser(description="Push a fresh daily meme to TRMNL.").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return 0 if push_todays_meme() else 1


if __name__ == "__main__":
    raise SystemExit(main())
