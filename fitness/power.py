"""Reduce intervals.icu's power curves to a "now vs best" panel.

Pure in the same way as :mod:`fitness.metrics`: :func:`build` takes the curves
:func:`fitness.client.fetch_power_curves` returns and does no I/O.

"Now" is the best power for each duration over the last ``NOW_DAYS`` days;
"best" is all time. All time includes now, so the now line can only ever meet
the best line, never cross it -- the gap between them is the distance back to
old form. Deliberately no FTP headline: a modelled FTP from a few easy rides
says more about how hard you rode than how fit you are, whereas a best-effort
curve is only ever what you actually did.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from math import log
from zoneinfo import ZoneInfo

from fitness.metrics import _nice_axis

logger = logging.getLogger(__name__)

NOW_DAYS = 42

# The SVG is drawn at its real pixel size (no preserveAspectRatio stretching),
# so the axis labels can live inside it as text. PLOT_* is the inner box the
# curves are drawn in; the margins hold the labels.
CHART_WIDTH = 524
CHART_HEIGHT = 370
PLOT_LEFT, PLOT_RIGHT = 40, 516
PLOT_TOP, PLOT_BOTTOM = 8, 346

# Durations on a log axis from 1 s to 2 h. Sampled at CHART_POINTS log-spaced
# durations rather than shipping intervals.icu's ~160 points per curve, which
# would be finer than the panel resolves and most of the 2KB webhook budget.
X_MIN_SECS, X_MAX_SECS = 1, 7200
CHART_POINTS = 32
X_TICKS = [(1, "1S"), (5, "5S"), (60, "1M"), (300, "5M"), (1200, "20M"), (3600, "1H")]

# The table's rows, and which of them is the headline.
KEY_DURATIONS = [(5, "5 S"), (60, "1 MIN"), (300, "5 MIN"), (1200, "20 MIN"), (3600, "60 MIN")]
HEADLINE_SECS = 1200


def _x(secs: float) -> int:
    span = log(X_MAX_SECS / X_MIN_SECS)
    return round(PLOT_LEFT + log(secs / X_MIN_SECS) / span * (PLOT_RIGHT - PLOT_LEFT))


def _y(watts: float, axis_max: float) -> int:
    return round(PLOT_BOTTOM - min(watts / axis_max, 1.0) * (PLOT_BOTTOM - PLOT_TOP))


def _at(curve: dict, secs: int) -> int | None:
    """Best power held for ``secs``, or None if no ride in the window was that long.

    The curve is sparse at long durations, so this takes the nearest sampled
    duration at or below ``secs``. Power curves only fall with duration, so
    that slightly flatters a gap in the samples -- by a few watts at most.
    """
    pairs = list(zip(curve.get("secs") or [], curve.get("watts") or []))
    if not pairs or pairs[-1][0] < secs:
        return None
    return next(w for s, w in reversed(pairs) if s <= secs)


def _sample_durations() -> list[int]:
    ratio = (X_MAX_SECS / X_MIN_SECS) ** (1 / (CHART_POINTS - 1))
    return sorted({round(X_MIN_SECS * ratio ** i) for i in range(CHART_POINTS)})


def _points(curve: dict, axis_max: float) -> str:
    """An SVG points string for the curve, stopping at its longest duration."""
    return " ".join(
        f"{_x(secs)},{_y(watts, axis_max)}"
        for secs in _sample_durations()
        if (watts := _at(curve, secs)) is not None
    )


@dataclass
class KeyDuration:
    label: str
    now: int | None
    best: int | None
    # Whole percent of best, or None when either side is missing.
    pct: int | None


@dataclass
class PowerChart:
    axis_max: float = 0.0
    best_area: str = ""
    now_points: str = ""
    y_ticks: list[dict] = field(default_factory=list)
    x_ticks: list[dict] = field(default_factory=list)


@dataclass
class PowerPanel:
    headline_label: str
    headline_pct: int | None
    rows: list[KeyDuration]
    chart: PowerChart
    now_days: int = NOW_DAYS
    updated: str = ""

    def as_merge_variables(self) -> dict:
        return asdict(self)


def build(now_curve: dict, best_curve: dict) -> PowerPanel:
    """Turn the two curves into the panel's table and chart geometry."""
    rows = []
    for secs, label in KEY_DURATIONS:
        now, best = _at(now_curve, secs), _at(best_curve, secs)
        pct = round(100 * now / best) if now and best else None
        rows.append(KeyDuration(label=label, now=now, best=best, pct=pct))

    axis_max, tick_values = _nice_axis(max(best_curve.get("watts") or [0]), intervals=4)
    best_points = _points(best_curve, axis_max)
    best_end = best_points.rsplit(" ", 1)[-1].split(",")[0] if best_points else PLOT_LEFT
    chart = PowerChart(
        axis_max=axis_max,
        # Close the best line down to the baseline so it reads as a filled area.
        best_area=(f"M{PLOT_LEFT},{PLOT_BOTTOM} L {best_points} L {best_end},{PLOT_BOTTOM} Z"
                   if best_points else ""),
        now_points=_points(now_curve, axis_max),
        y_ticks=[{"label": f"{v:g}", "y": _y(v, axis_max)} for v in tick_values],
        x_ticks=[{"label": label, "x": _x(secs)} for secs, label in X_TICKS],
    )

    headline = next(row for row in rows if row.label == dict(KEY_DURATIONS)[HEADLINE_SECS])
    return PowerPanel(
        headline_label=headline.label,
        headline_pct=headline.pct,
        rows=rows,
        chart=chart,
    )


def collect() -> PowerPanel:
    """Fetch both curves from intervals.icu and build the panel."""
    from fitness import client

    curves = {c["id"]: c for c in client.fetch_power_curves(f"{NOW_DAYS}d,all")}
    panel = build(curves.get(f"{NOW_DAYS}d", {}), curves.get("all", {}))
    panel.updated = datetime.now(ZoneInfo("Europe/Stockholm")).strftime("%H:%M")
    return panel
