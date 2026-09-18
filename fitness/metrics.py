"""Reduce intervals.icu's raw feeds to the handful of scalars a panel can show.

This module is deliberately pure: :func:`build` takes the two lists returned by
:mod:`fitness.client` and returns a :class:`PanelMetrics`, with no network and no
clock of its own. That keeps it testable, and -- more importantly -- keeps it the
piece that survives a move to a self-hosted TRMNL server, where only the
transport around it changes.

Everything here is sized against TRMNL's 2KB webhook payload cap, which is why
the fitness series is quantised to small integers rather than shipped as floats.

On the form convention: intervals.icu's chart and the TrainingPeaks lineage it
comes from differ over whether form uses *today's* or *yesterday's* CTL/ATL. We
use same-day, which matches what the intervals.icu API hands back for today. If
the panel ever disagrees with the website by a point or two, this is why.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from math import ceil, floor, log10
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

SPARK_DAYS = 90
WEEK_DAYS = 7
PEAK_DAYS = 42

# Chart geometry, in the SVG's own user units. The panel scales it to fit, so
# these are an aspect ratio rather than pixels. CHART_POINTS decimates the daily
# series: 90 points across 520 units is far finer than a 1-bit panel can resolve,
# and the full-resolution path blows the 2KB webhook budget on its own.
CHART_WIDTH = 520
CHART_HEIGHT = 258
CHART_POINTS = 45

# Training Stress Balance bands, following the usual Performance Management
# Chart reading. These are descriptive labels for a glanceable display, not
# training advice.
FORM_BANDS = [
    (25.0, "Very fresh"),
    (5.0, "Fresh"),
    (-10.0, "Neutral"),
    (-30.0, "Building"),
    (float("-inf"), "Overloaded"),
]


def _form_label(form: float) -> str:
    return next(label for threshold, label in FORM_BANDS if form > threshold)


def _nice_axis(peak: float, intervals: int = 5) -> tuple[float, list[float]]:
    """Pick a round axis maximum at or above ``peak``, with its tick values.

    The axis always starts at zero -- CTL and ATL are absolute loads, so a
    zero-suppressed axis would exaggerate every wobble. Fixing the maximum
    instead (the original design pinned it at 100) is what makes a low-CTL
    athlete render as a flat line along the floor, hence choosing it from
    the data.
    """
    if peak <= 0:
        return 10.0, [0.0, 5.0, 10.0]
    raw_step = peak / intervals
    magnitude = 10.0 ** floor(log10(raw_step))
    step = next(
        (m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw_step),
        10 * magnitude,
    )
    axis_max = ceil(peak / step) * step
    return axis_max, [i * step for i in range(int(round(axis_max / step)) + 1)]


def _sample(values: list[float], count: int) -> list[float]:
    """Evenly decimate to ``count`` points, always keeping the first and last."""
    if len(values) <= count:
        return list(values)
    last = len(values) - 1
    return [values[round(i * last / (count - 1))] for i in range(count)]


def _points(values: list[float], axis_max: float) -> str:
    """An SVG points string, integer coordinates to stay inside the payload cap."""
    if not values:
        return ""
    span = max(len(values) - 1, 1)
    return " ".join(
        f"{round(i / span * CHART_WIDTH)},"
        f"{round(CHART_HEIGHT - min(v / axis_max, 1.0) * CHART_HEIGHT)}"
        for i, v in enumerate(values)
    )


def _day_of(activity: dict) -> date:
    return datetime.fromisoformat(activity["start_date_local"]).date()


@dataclass
class WeekSummary:
    """One rolling 7-day block. Distances in km, durations in hours."""

    load: int = 0
    hours: float = 0.0
    km: float = 0.0
    sessions: int = 0


@dataclass
class ChartGeometry:
    """Everything the panel's SVG needs, precomputed.

    TRMNL renders Liquid server-side and runs none of your JavaScript, so the
    geometry the original Claude Design artboard built in ``renderVals()`` has to
    be computed here instead. Paths ship as ready-made SVG strings because
    assembling coordinates in Liquid is far more error-prone than assembling them
    in Python.
    """

    width: int = CHART_WIDTH
    height: int = CHART_HEIGHT
    axis_max: float = 0.0
    ctl_area: str = ""
    atl_points: str = ""
    ticks: list[dict] = field(default_factory=list)
    grid_y: list[int] = field(default_factory=list)


@dataclass
class PanelMetrics:
    as_of: str
    ctl: float
    atl: float
    form: float
    form_label: str
    ramp_rate: float
    ctl_delta_7d: float = 0.0
    ctl_delta_label: str = ""
    updated: str = ""
    ctl_peak_42d: float = 0.0
    chart: ChartGeometry = field(default_factory=ChartGeometry)
    this_week: WeekSummary = field(default_factory=WeekSummary)
    last_week: WeekSummary = field(default_factory=WeekSummary)
    daily_load: list[int] = field(default_factory=list)
    last_activity: str = ""
    last_activity_ago: int = 0
    resting_hr: int | None = None
    hrv: float | None = None

    def as_merge_variables(self) -> dict:
        """Flatten to the JSON TRMNL's webhook expects under ``merge_variables``."""
        return asdict(self)


def _summarise(activities: list[dict], start: date, end: date) -> WeekSummary:
    """Aggregate activities with ``start <= day < end``."""
    window = [a for a in activities if start <= _day_of(a) < end]
    return WeekSummary(
        load=sum(int(a.get("icu_training_load") or 0) for a in window),
        hours=round(sum(a.get("moving_time") or 0 for a in window) / 3600, 1),
        km=round(sum(a.get("distance") or 0 for a in window) / 1000, 1),
        sessions=len(window),
    )


def build(wellness: list[dict], activities: list[dict], today: date) -> PanelMetrics:
    """Collapse the raw feeds into the panel's scalars.

    ``wellness`` must be oldest-first as :func:`fitness.client.fetch_wellness`
    returns it. Weeks are rolling 7-day blocks ending today rather than calendar
    weeks, so the panel never shows a nearly-empty week just because it is
    Monday morning.
    """
    if not wellness:
        raise ValueError("no wellness data: cannot build a panel")

    latest = wellness[-1]
    ctl = float(latest.get("ctl") or 0.0)
    atl = float(latest.get("atl") or 0.0)
    form = ctl - atl

    window = wellness[-SPARK_DAYS:]
    ctl_series = [float(row.get("ctl") or 0.0) for row in window]
    atl_series = [float(row.get("atl") or 0.0) for row in window]

    axis_max, tick_values = _nice_axis(max(ctl_series + atl_series))
    ctl_points = _points(_sample(ctl_series, CHART_POINTS), axis_max)
    chart = ChartGeometry(
        axis_max=round(axis_max, 1),
        # Close the CTL line down to the baseline so it reads as a filled area.
        ctl_area=f"M0,{CHART_HEIGHT} L {ctl_points} L {CHART_WIDTH},{CHART_HEIGHT} Z",
        atl_points=_points(_sample(atl_series, CHART_POINTS), axis_max),
        ticks=[
            {"label": f"{value:g}", "y": round(CHART_HEIGHT - value / axis_max * CHART_HEIGHT)}
            for value in reversed(tick_values)
        ],
        grid_y=[
            round(CHART_HEIGHT - value / axis_max * CHART_HEIGHT)
            for value in tick_values
            if 0 < value < axis_max
        ],
    )

    week_ago = wellness[-(WEEK_DAYS + 1)] if len(wellness) > WEEK_DAYS else wellness[0]
    peak_window = [float(row.get("ctl") or 0.0) for row in wellness[-PEAK_DAYS:]]

    # Both blocks must span exactly WEEK_DAYS or the deltas are meaningless:
    # this week is the WEEK_DAYS days ending today inclusive, last week the
    # WEEK_DAYS immediately before that.
    this_week_start = today - timedelta(days=WEEK_DAYS - 1)
    this_week = _summarise(activities, this_week_start, today + timedelta(days=1))
    last_week = _summarise(
        activities, this_week_start - timedelta(days=WEEK_DAYS), this_week_start
    )

    by_day = {}
    for activity in activities:
        day = _day_of(activity)
        by_day[day] = by_day.get(day, 0) + int(activity.get("icu_training_load") or 0)
    # Same window as this_week, so the bars always sum to this_week.load.
    daily_load = [
        by_day.get(this_week_start + timedelta(days=offset), 0)
        for offset in range(WEEK_DAYS)
    ]

    delta = round(ctl - float(week_ago.get("ctl") or 0.0), 1)
    last = activities[-1] if activities else None

    return PanelMetrics(
        as_of=latest["id"],
        ctl=round(ctl, 1),
        atl=round(atl, 1),
        form=round(form, 1),
        form_label=_form_label(form),
        ramp_rate=round(float(latest.get("rampRate") or 0.0), 1),
        ctl_delta_7d=delta,
        # Liquid has no tidy way to force a leading "+", so format it here.
        ctl_delta_label=f"{delta:+.1f}",
        ctl_peak_42d=round(max(peak_window), 1) if peak_window else 0.0,
        chart=chart,
        this_week=this_week,
        last_week=last_week,
        daily_load=daily_load,
        last_activity=(last.get("type") or "") if last else "",
        last_activity_ago=(today - _day_of(last)).days if last else 0,
        resting_hr=int(latest["restingHR"]) if latest.get("restingHR") else None,
        hrv=round(float(latest["hrv"]), 1) if latest.get("hrv") else None,
    )


def collect(today: date | None = None) -> PanelMetrics:
    """Fetch from intervals.icu and build the panel metrics."""
    from fitness import client

    day = today or date.today()
    metrics = build(
        client.fetch_wellness(days=SPARK_DAYS, today=day),
        client.fetch_activities(days=2 * WEEK_DAYS + 1, today=day),
        day,
    )
    # Wall-clock of this fetch, for the panel's "updated" stamp. Kept out of
    # build() so that stays a pure function of its inputs.
    metrics.updated = datetime.now(ZoneInfo("Europe/Stockholm")).strftime("%H:%M")
    return metrics
