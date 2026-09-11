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
from memes.trmnl import push_image

logger = logging.getLogger(__name__)

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={}"
NUM_STORIES = 10
COOLDOWN_DAYS = 3
COOLDOWN_FILE = Path(__file__).parent / "recent_templates.json"


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
            })
    return stories


def _load_cooldowns() -> dict[str, str]:
    """Load {template_name: date_str} from disk."""
    if COOLDOWN_FILE.exists():
        return json.loads(COOLDOWN_FILE.read_text())
    return {}


def _save_cooldowns(data: dict[str, str]) -> None:
    COOLDOWN_FILE.write_text(json.dumps(data))


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


async def send_daily_hn_meme(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        stories = fetch_hn_stories()
        numbered = "\n".join(
            f"{i+1}. {s['title']}" for i, s in enumerate(stories)
        )
        prompt = (
            "Make a meme about the tech/startup world based on today's "
            "Hacker News front page. Here are the top headlines:\n\n"
            f"{numbered}\n\n"
            "After making the meme, reply with ONLY the number of the "
            "article you based it on, e.g. '3'."
        )

        excluded = get_excluded_templates()
        img_bytes, template, agent_text = generate_meme(
            prompt, exclude_templates=excluded,
        )
        record_template_use(template)
        logger.info(f"Daily HN meme: template={template}, size={len(img_bytes)}")

        # Try to match the article number from the agent's response
        caption = None
        match = re.search(r"\b(\d{1,2})\b", agent_text)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(stories):
                story = stories[idx]
                caption = story["hn_url"]

        await context.bot.send_photo(
            chat_id=get_telegram_user_id(),
            photo=io.BytesIO(img_bytes),
            caption=caption,
        )

        # The e-ink panel is a bonus surface, not the point of the job: a failed
        # push must not look like a failed meme.
        try:
            push_image(img_bytes)
        except Exception:
            logger.exception("Failed to push daily HN meme to TRMNL")
    except Exception:
        logger.exception("Failed to send daily HN meme")
