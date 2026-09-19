"""Daily Hacker News meme — fetches top stories and generates a meme."""

import io
import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

import requests
from telegram.ext import ContextTypes

from gcp_util.secrets import get_telegram_user_id
from memes.generator import generate_meme
from util.paths import data_path

logger = logging.getLogger(__name__)

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={}"
NUM_STORIES = 10
COOLDOWN_DAYS = 3


def cooldown_file() -> Path:
    """Recently-used meme templates (see :mod:`util.paths`)."""
    return data_path("memes", "recent_templates.json")


def fetch_hn_stories(n: int = NUM_STORIES) -> list[dict]:
    story_ids = requests.get(HN_TOP_STORIES_URL, timeout=10).json()[:n]
    stories = []
    for sid in story_ids:
        item = requests.get(HN_ITEM_URL.format(sid), timeout=10).json()
        if item and item.get("title"):
            stories.append({
                "id": sid,
                "title": item["title"],
                "url": item.get("url", HN_ITEM_PAGE.format(sid)),
                "hn_url": HN_ITEM_PAGE.format(sid),
                # Shown on the TRMNL panel; absent on very fresh items.
                "points": item.get("score"),
                "comments": item.get("descendants"),
            })
    return stories


def _load_cooldowns() -> dict[str, str]:
    """Load {template_name: date_str} from disk."""
    path = cooldown_file()
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_cooldowns(data: dict[str, str]) -> None:
    path = cooldown_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def get_excluded_templates() -> list[str]:
    """Return template names used within the last COOLDOWN_DAYS days."""
    cooldowns = _load_cooldowns()
    cutoff = date.today() - timedelta(days=COOLDOWN_DAYS)
    # Prune old entries while we're at it
    active = {k: v for k, v in cooldowns.items() if date.fromisoformat(v) > cutoff}
    _save_cooldowns(active)
    return list(active.keys())


def record_template_use(template_name: str) -> None:
    cooldowns = _load_cooldowns()
    cooldowns[template_name] = date.today().isoformat()
    _save_cooldowns(cooldowns)


def build_meme_prompt(stories: list[dict]) -> str:
    """The agent prompt for today's meme, plus the ask for which story it used."""
    numbered = "\n".join(f"{i+1}. {s['title']}" for i, s in enumerate(stories))
    return (
        "Make a meme about the tech/startup world based on today's "
        "Hacker News front page. Here are the top headlines:\n\n"
        f"{numbered}\n\n"
        "After making the meme, reply with ONLY the number of the "
        "article you based it on, e.g. '3'."
    )


def pick_story(stories: list[dict], agent_text: str) -> dict | None:
    """Resolve the agent's reply to one of ``stories``, or None if it didn't say.

    The agent is asked for a bare number, but it is a language model, so treat
    the reply as prose that probably contains one.
    """
    match = re.search(r"\b(\d{1,2})\b", agent_text)
    if not match:
        return None
    index = int(match.group(1)) - 1
    return stories[index] if 0 <= index < len(stories) else None


async def send_daily_hn_meme(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        stories = fetch_hn_stories()
        img_bytes, template, agent_text = generate_meme(
            build_meme_prompt(stories), exclude_templates=get_excluded_templates(),
        )
        record_template_use(template)
        logger.info(f"Daily HN meme: template={template}, size={len(img_bytes)}")

        story = pick_story(stories, agent_text)
        await context.bot.send_photo(
            chat_id=get_telegram_user_id(),
            photo=io.BytesIO(img_bytes),
            caption=story["hn_url"] if story else None,
        )
    except Exception:
        logger.exception("Failed to send daily HN meme")
        return

    # Best-effort: the Telegram meme is the thing that must not break, so a
    # failure to reach TRMNL costs a stale panel and nothing more.
    try:
        from memes.trmnl import push_meme

        push_meme(img_bytes, story)
    except Exception:
        logger.exception("Failed to push daily meme to TRMNL")
