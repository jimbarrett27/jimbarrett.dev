"""A deterministic per-day scene brief for the tapestry.

Panels are no longer shown yesterday's markup (see :func:`tapestry.svg.seam_palette`),
which stopped them inheriting its palette -- but that markup had also been quietly
carrying the *house style*: the figure vocabulary, the outline weight, the terrain
treatment. With it gone the panels needed something to hold them together, and a
first attempt at this module supplied the opposite: it rolled palette, lighting
and figure scale freely, and every day came out looking like a different artist.

So the division of labour here is deliberate and narrow. The house style is fixed
prose in the prompt template and never varies. This module varies only what the
panel *depicts*: which ground it sits on, how the three stories are laid out, and
where the detail is concentrated. Palette, figure scale, outline treatment and
overall lightness are all absent by design -- those are what made the tapestry
stop reading as one artefact.

Picks are seeded by the date, so a day always gets the same brief no matter how
often it is regenerated -- a backfill reproduces the artwork's intent rather than
rerolling it.
"""

import random
from datetime import date

# Ground the scene sits on. Every option stays inside the house register, so the
# terrain changes day to day without the tapestry changing medium -- and every
# option is mid-toned. An earlier "dark ploughed soil and bare winter ground"
# drew a near-black band straight across 2026-07-22, contradicting the prompt's
# own "keep the overall lightness middling" rule two lines above it.
GROUNDS = [
    "parched tan earth and dry grassland",
    "grey urban pavement, cobbles and kerbstones",
    "sage-green field and open pasture",
    "freshly turned earth in muted mid-brown, with stubble and furrows",
    "pale sand and shingle with dusty blue water",
]

# A second terrain appearing in one part of the width, so the ground is not one
# flat tone across the panel -- this is most of what made the good days read as
# varied rather than repetitive.
ACCENT_GROUNDS = [
    "a band of dusty blue water crossing one section",
    "a stretch of sage-green field in one section",
    "an area of grey paving in one section",
    "a rise of tan hillside in one section",
]

# How the three stories are distributed across the 1600px width.
ARRANGEMENTS = [
    "three roughly equal zones side by side, divided by changes in terrain rather than by lines",
    "one story taking the middle half of the width, the other two flanking it more narrowly",
    "the three interleaved, with elements of each drifting into its neighbours",
    "a strong left-to-right progression, each scene handing off into the next",
]

# Where the small incident is concentrated. Three options, deliberately: this
# list is rotated against ARRANGEMENTS (four) and GROUNDS (five), and rotating
# two lists of equal length would lock them in step so only a few of the possible
# pairings ever occurred.
BUSYNESS = [
    "one dense knot of activity with quieter worked ground to either side",
    "evenly worked across the full width, no part left empty",
    "unevenly weighted, busiest towards one end and calmer at the other",
]

# Something continuous to tie the three scenes into one image.
CONNECTORS = [
    "let smoke or birds drift across the whole width",
    "thread a road, river or rope through all three scenes",
    "run a loose line of small objects or creatures low along the bottom",
    "scatter debris, papers or embers so they carry between the scenes",
]


def _ordinal(day: str) -> int | None:
    """Day number for ``day``, or ``None`` if it isn't a date.

    Accepts the ``YYYY-MM-DD#n`` keys that :func:`tapestry.generator.generate_tapestry`
    uses for panels that aren't one-per-date, counting each position as a day.
    """
    base, _, suffix = day.partition("#")
    try:
        ordinal = date.fromisoformat(base).toordinal()
    except ValueError:
        return None
    return ordinal + (int(suffix) if suffix.isdigit() else 0)


def style_directive(day: str) -> str:
    """Return the scene brief for ``day`` (YYYY-MM-DD) as a prose paragraph.

    Deterministic in ``day``: the same date always yields the same brief. Any
    stable string works as a key -- callers drawing panels that aren't one-per-date
    seed on position instead.

    Ground, layout and detail are *rotated* by day number rather than sampled, so
    consecutive days are guaranteed to differ on all three. Sampling them let
    neighbouring days collide by chance, which is how 2026-07-22 and 07-23 both
    came out as ranks of small figures. The three lists have co-prime lengths
    (5, 4, 3) so their combinations cycle with a period of 60 days rather than
    marching in lockstep.
    """
    rng = random.Random(f"tapestry-scene-{day}")
    n = _ordinal(day)

    def pick(options, offset):
        # Fall back to sampling for keys that aren't dates at all.
        return options[(n + offset) % len(options)] if n is not None else rng.choice(options)

    return (
        f"Ground: mostly {pick(GROUNDS, 0)}; plus {rng.choice(ACCENT_GROUNDS)}. "
        f"Layout: {pick(ARRANGEMENTS, 0)}. "
        f"Detail: {pick(BUSYNESS, 0)}. "
        f"Also: {rng.choice(CONNECTORS)}."
    )
