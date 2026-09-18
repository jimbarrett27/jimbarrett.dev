"""Render the meme panel locally, without an LLM call or a push.

    uv run --extra dev python -m memes.preview

Uses a fixed template and caption rather than generating today's meme, so the
layout can be iterated for free. What it cannot show is how a *particular* meme
dithers -- for that, look at the uploaded image after a real run.
"""

import argparse
import logging
from datetime import date
from pathlib import Path

from memes import eink
from memes.renderer import Template, TextBox, render_meme
from util import panel_preview

TEMPLATE = Path(__file__).parent / "templates_trmnl" / "meme_full.liquid"

SAMPLE_HEADLINE = "Show HN: I built a self-hosted dashboard for my e-ink display"


def sample_meme() -> eink.PreparedMeme:
    """A representative meme: a square template, which is the awkward aspect."""
    png = render_meme(
        Template("drake.png", [
            TextBox("top", 250, 0, 250, 250),
            TextBox("bottom", 250, 250, 250, 250),
        ]),
        {"top": "Reading the docs", "bottom": "Asking the LLM that read the docs"},
    )
    return eink.prepare(png)


def todays_meme() -> tuple[eink.PreparedMeme, str, dict]:
    """Generate today's real meme, exactly as the daily job would.

    Costs an LLM call and picks a template under the same cooldown rules as the
    scheduled run, so the preview is the genuine article rather than a mock-up.
    """
    from memes.daily_hn_meme import (
        build_meme_prompt, fetch_hn_stories, pick_story, get_excluded_templates,
    )
    from memes.generator import generate_meme

    stories = fetch_hn_stories()
    img_bytes, template, agent_text = generate_meme(
        build_meme_prompt(stories), exclude_templates=get_excluded_templates(),
    )
    logging.getLogger(__name__).info("template: %s", template)
    story = pick_story(stories, agent_text)
    return eink.prepare(img_bytes), (story or {}).get("title", SAMPLE_HEADLINE), story or {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("panel-preview/memes"))
    parser.add_argument("--today", action="store_true",
                        help="generate today's real meme (costs an LLM call)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.today:
        prepared, headline, story = todays_meme()
    else:
        prepared, headline, story = sample_meme(), SAMPLE_HEADLINE, {}
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # The preview has no bucket, so point the markup at a local copy.
    local_image = out_dir / "meme.png"
    local_image.write_bytes(prepared.png)

    panel_preview.preview(
        TEMPLATE,
        {
            "meme_url": local_image.name,
            "meme_width": prepared.width,
            "meme_height": prepared.height,
            "layout": prepared.layout,
            "headline": headline,
            "day": date.today().isoformat(),
            "points": story.get("points", 412),
            "comments": story.get("comments", 137),
        },
        out_dir,
        # The whole panel is a dithered photograph; mid-grey is the point here.
        check_grey=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
