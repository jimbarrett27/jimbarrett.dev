"""Generate a Bayeux-style "news tapestry" from news stories via OpenRouter.

Each panel covers three stories; consecutive panels are stitched together with a
vertical overlap so the tapestry grows into one continuous image. The OpenRouter
key is fetched securely by the house LLM helper, so nothing secret lives here.
"""

import logging
from datetime import date as date_cls
from pathlib import Path
from typing import NamedTuple

from llm.llm_util import get_llm_response
from tapestry.style import style_directive
from tapestry.svg import (
    OVERLAP,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    extract_panel,
    seam_palette,
    stitch_svgs,
    svg_problems,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
STORIES_PER_PANEL = 3
MAX_ATTEMPTS = 3
PROMPT_TEMPLATE = str(Path(__file__).parent / "prompts" / "tapestry_panel.jinja2")


class Panel(NamedTuple):
    """A generated panel: its SVG markup and the model's stated plan (if any)."""

    svg: str
    plan: str | None


def generate_panel(
    stories,
    previous_svg: str = None,
    model: str = DEFAULT_MODEL,
    max_attempts: int = MAX_ATTEMPTS,
    day: str = None,
    previous_plan: str = None,
) -> Panel:
    """Generate one tapestry panel from (at least) three stories.

    ``stories`` is a sequence of dicts with ``title``, ``summary`` and ``link``
    keys. Pass ``previous_svg`` to ask the model to visually continue from
    yesterday's panel, and ``previous_plan`` (that panel's stored plan) to tell
    it what it is reaching up into.

    Only the *seam* of ``previous_svg`` is handed over -- the colours painted
    along its bottom edge -- never the markup. Passing the whole previous panel
    is what made the tapestry converge to a single look: the model would inherit
    the palette, the motifs and eventually whole ``<defs>`` blocks verbatim.
    Variety is supplied instead by a per-day style brief seeded on ``day``
    (defaults to today), so consecutive panels are pushed to look unalike.

    Each attempt can fail two ways, and both cost one of ``max_attempts``: the
    call to the model can fail outright (a transient OpenRouter/provider error),
    or it can return a structurally invalid panel (see
    :func:`tapestry.svg.svg_problems`). In the latter case the problem is fed
    back into the next attempt's prompt so the retry knows what to fix. After
    ``max_attempts`` we give up with a ``RuntimeError``. Returns a
    :class:`Panel` with the cleaned SVG and the model's plan.
    """
    day = day or date_cls.today().isoformat()
    params = {
        "stories": [dict(s) for s in stories[:STORIES_PER_PANEL]],
        "seam_palette": seam_palette(previous_svg) if previous_svg else None,
        "previous_plan": previous_plan,
        "style_directive": style_directive(day),
        "panel_width": PANEL_WIDTH,
        "panel_height": PANEL_HEIGHT,
        "overlap": OVERLAP,
    }

    last_problem = None   # fed back into the retry's prompt
    last_failure = None   # why we gave up, whether or not a panel came back
    for attempt in range(1, max_attempts + 1):
        try:
            content = get_llm_response(
                PROMPT_TEMPLATE, {**params, "problem": last_problem}, model
            )
        except Exception as exc:
            # OpenRouter sometimes closes a request with an empty (whitespace
            # keep-alive padding only) body when the upstream provider stalls,
            # which surfaces here as a JSONDecodeError. That's transient, so
            # spend an attempt on it rather than losing the day. There's no
            # model output to critique, so last_problem is left untouched.
            last_failure = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Panel attempt %d/%d with %s never reached the model: %s",
                attempt, max_attempts, model, last_failure,
            )
            continue

        try:
            svg, plan = extract_panel(content)
            problems = svg_problems(svg)
        except ValueError as exc:
            problems = [str(exc)]

        if not problems:
            return Panel(svg=svg, plan=plan)

        last_problem = last_failure = "; ".join(problems)
        logger.warning(
            "Panel attempt %d/%d with %s produced an invalid SVG: %s",
            attempt, max_attempts, model, last_problem,
        )

    raise RuntimeError(
        f"Failed to generate a valid SVG with {model} after {max_attempts} "
        f"attempts (last failure: {last_failure})"
    )


def generate_tapestry(stories, days: int = None, model: str = DEFAULT_MODEL) -> str:
    """Generate one panel per group of three stories and stitch them together.

    ``days`` caps how many panels to generate; defaults to as many complete
    groups of three as ``stories`` allows. Each panel after the first is asked
    to continue seamlessly from the previous one.
    """
    groups = [
        stories[i:i + STORIES_PER_PANEL]
        for i in range(0, len(stories) - (STORIES_PER_PANEL - 1), STORIES_PER_PANEL)
    ]
    if days is not None:
        groups = groups[:days]

    svgs = []
    previous_svg = previous_plan = None
    today = date_cls.today().isoformat()
    for i, group in enumerate(groups):
        # These panels aren't one-per-date, so seed each one's style brief on its
        # position instead: distinct keys are all the brief needs to vary.
        panel = generate_panel(
            group,
            previous_svg=previous_svg,
            model=model,
            day=f"{today}#{i}",
            previous_plan=previous_plan,
        )
        svgs.append(panel.svg)
        previous_svg, previous_plan = panel.svg, panel.plan
        logger.info("Generated tapestry panel %d/%d", len(svgs), len(groups))

    return stitch_svgs(svgs)
