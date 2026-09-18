"""Unit tests for the pure panel-metric reduction (no network)."""

from datetime import date

import pytest

from fitness.metrics import (
    CHART_HEIGHT,
    CHART_POINTS,
    WEEK_DAYS,
    _nice_axis,
    _sample,
    build,
)

TODAY = date(2026, 9, 17)


def wellness_day(day: str, ctl: float, atl: float, **extra) -> dict:
    return {"id": day, "ctl": ctl, "atl": atl, "rampRate": 0.0, **extra}


def activity(day: str, load: int, *, type_: str = "Run", seconds: int = 1800,
             metres: float = 5000.0) -> dict:
    return {
        "start_date_local": f"{day}T07:00:00",
        "type": type_,
        "name": "session",
        "icu_training_load": load,
        "moving_time": seconds,
        "distance": metres,
    }


def test_form_is_ctl_minus_atl():
    metrics = build([wellness_day("2026-09-17", 30.0, 12.0)], [], TODAY)
    assert metrics.form == 18.0
    assert metrics.form_label == "Fresh"


@pytest.mark.parametrize(
    "ctl,atl,label",
    [(30, 2, "Very fresh"), (30, 20, "Fresh"), (30, 33, "Neutral"),
     (30, 50, "Building"), (30, 70, "Overloaded")],
)
def test_form_labels_cover_the_bands(ctl, atl, label):
    assert build([wellness_day("2026-09-17", ctl, atl)], [], TODAY).form_label == label


def test_weeks_span_equal_windows_and_do_not_overlap():
    # One activity on every one of the last 14 days, load 10 each.
    acts = [activity(f"2026-09-{day:02d}", 10) for day in range(4, 18)]
    metrics = build([wellness_day("2026-09-17", 20.0, 15.0)], acts, TODAY)
    assert metrics.this_week.sessions == WEEK_DAYS
    assert metrics.last_week.sessions == WEEK_DAYS
    assert metrics.this_week.load == metrics.last_week.load


def test_daily_load_sums_to_this_week():
    acts = [activity("2026-09-15", 40), activity("2026-09-11", 60),
            activity("2026-09-03", 99)]  # the last one is outside both weeks
    metrics = build([wellness_day("2026-09-17", 20.0, 15.0)], acts, TODAY)
    assert len(metrics.daily_load) == WEEK_DAYS
    assert sum(metrics.daily_load) == metrics.this_week.load == 100


def test_same_day_activities_are_combined():
    acts = [activity("2026-09-15", 40), activity("2026-09-15", 25)]
    metrics = build([wellness_day("2026-09-17", 20.0, 15.0)], acts, TODAY)
    assert sum(metrics.daily_load) == 65
    assert metrics.this_week.sessions == 2


@pytest.mark.parametrize(
    "peak,expected_max",
    [(22.6, 25.0), (68.0, 80.0), (4.2, 5.0), (140.0, 150.0), (0.0, 10.0)],
)
def test_nice_axis_rounds_up_and_starts_at_zero(peak, expected_max):
    axis_max, ticks = _nice_axis(peak)
    assert axis_max == pytest.approx(expected_max)
    assert axis_max >= peak
    assert ticks[0] == 0.0
    assert ticks[-1] == pytest.approx(axis_max)


def test_axis_adapts_to_a_low_ctl_athlete():
    """The original design pinned the axis at 100, flattening a low-CTL line."""
    low, _ = _nice_axis(22.6)
    high, _ = _nice_axis(68.0)
    assert low < 100 and low < high


def test_sample_keeps_both_ends():
    sampled = _sample([float(i) for i in range(90)], 45)
    assert len(sampled) == 45
    assert sampled[0] == 0.0 and sampled[-1] == 89.0
    assert _sample([1.0, 2.0], 45) == [1.0, 2.0]


def test_chart_paths_are_closed_and_within_bounds():
    wellness = [
        wellness_day(f"2026-0{6 + d // 30}-{d % 30 + 1:02d}", 10.0 + d * 0.1, 8.0)
        for d in range(60)
    ]
    chart = build(wellness, [], TODAY).chart
    assert chart.ctl_area.startswith(f"M0,{CHART_HEIGHT} L ")
    assert chart.ctl_area.endswith("Z")
    assert len(chart.atl_points.split()) == CHART_POINTS
    ys = [int(p.split(",")[1]) for p in chart.atl_points.split()]
    assert all(0 <= y <= CHART_HEIGHT for y in ys)


def test_ctl_delta_and_peak_use_their_windows():
    wellness = [
        wellness_day(f"2026-08-{d + 1:02d}", ctl=float(d), atl=5.0) for d in range(30)
    ]
    metrics = build(wellness, [], TODAY)
    assert metrics.ctl_delta_7d == pytest.approx(7.0)   # rose 1/day for 7 days
    assert metrics.ctl_peak_42d == pytest.approx(29.0)  # the latest is the max


def test_missing_optional_fields_do_not_blow_up():
    metrics = build([wellness_day("2026-09-17", 20.0, 15.0)], [], TODAY)
    assert metrics.resting_hr is None and metrics.hrv is None
    assert metrics.last_activity == "" and metrics.last_activity_ago == 0


def test_empty_wellness_is_an_error():
    with pytest.raises(ValueError):
        build([], [], TODAY)
