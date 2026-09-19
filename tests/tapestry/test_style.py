"""Unit tests for the per-day scene brief."""

from datetime import date

from tapestry.style import ARRANGEMENTS, BUSYNESS, style_directive


def test_a_day_always_gets_the_same_brief():
    # A backfill must reproduce a day's intent, not reroll it.
    assert style_directive("2026-07-21") == style_directive("2026-07-21")


def test_consecutive_days_get_different_briefs():
    days = [f"2026-07-{d:02d}" for d in range(1, 32)]
    briefs = [style_directive(d) for d in days]

    assert all(a != b for a, b in zip(briefs, briefs[1:]))


def test_briefs_spread_across_the_palette_pool():
    """The point of the brief is variety, so it must not collapse to a few picks.

    A month of dates should yield a month of distinct briefs; if the seeding were
    broken (e.g. seeded on something constant) this drops to one.
    """
    briefs = [style_directive(f"2026-07-{d:02d}") for d in range(1, 32)]

    assert len(set(briefs)) > 25


def axes(day):
    """Split a brief into its (ground, layout, detail) axes."""
    parts = dict(
        p.split(": ", 1) for p in style_directive(day).rstrip(".").split(". ") if ": " in p
    )
    return parts["Ground"], parts["Layout"], parts["Detail"]


def test_consecutive_days_differ_on_every_rotated_axis():
    """2026-07-22 and 07-23 both drew crowds: sampled axes collided by chance.

    Ground, layout and detail are rotated by day number now, so neighbours can
    never share any of the three.
    """
    days = [f"2026-07-{d:02d}" for d in range(1, 32)]

    for today, tomorrow in zip(days, days[1:]):
        for i, axis in enumerate(("ground", "layout", "detail")):
            assert axes(today)[i] != axes(tomorrow)[i], f"{today}/{tomorrow} share a {axis}"


def test_rotated_axes_do_not_march_in_lockstep():
    """Co-prime list lengths, so pairings cycle rather than repeating every 4 days."""
    days = [date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + n).isoformat()
            for n in range(60)]
    pairs = {(axes(d)[1], axes(d)[2]) for d in days}

    assert len(pairs) == len(ARRANGEMENTS) * len(BUSYNESS)


def test_a_non_date_key_still_yields_a_brief():
    # generate_tapestry seeds on position; an unparseable key must not raise.
    assert style_directive("not-a-date").startswith("Ground:")
