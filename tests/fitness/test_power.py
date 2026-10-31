"""Unit tests for the power-curve panel reduction (no network)."""

from fitness.power import (
    CHART_POINTS,
    PLOT_BOTTOM,
    PLOT_LEFT,
    PLOT_RIGHT,
    PLOT_TOP,
    _at,
    build,
)


def curve(pairs: list[tuple[int, int]]) -> dict:
    return {"secs": [s for s, _ in pairs], "watts": [w for _, w in pairs]}


BEST = curve([(1, 850), (5, 790), (60, 440), (300, 300), (1200, 250),
              (1800, 230), (3600, 206), (7500, 180)])
NOW = curve([(1, 560), (5, 490), (60, 280), (300, 215), (1200, 192), (1860, 175)])


def test_at_takes_nearest_sample_at_or_below():
    assert _at(BEST, 5) == 790
    assert _at(BEST, 4000) == 206   # between samples: the shorter one's power
    assert _at(NOW, 3600) is None   # no ride in the window was an hour long
    assert _at({}, 5) is None


def test_rows_compare_now_with_best():
    panel = build(NOW, BEST)
    rows = {row.label: row for row in panel.rows}
    assert (rows["20 MIN"].now, rows["20 MIN"].best, rows["20 MIN"].pct) == (192, 250, 77)
    assert rows["60 MIN"].now is None and rows["60 MIN"].pct is None
    assert (panel.headline_label, panel.headline_pct) == ("20 MIN", 77)


def test_no_recent_rides_leaves_now_empty():
    panel = build({}, BEST)
    assert panel.chart.now_points == ""
    assert panel.headline_pct is None
    assert all(row.now is None for row in panel.rows)
    assert panel.chart.best_area.endswith("Z")


def test_chart_geometry_stays_in_the_plot():
    chart = build(NOW, BEST).chart
    assert chart.axis_max >= 850
    for points in (chart.now_points, chart.best_area.split(" L ")[1]):
        coords = [tuple(map(int, p.split(","))) for p in points.split()]
        assert len(coords) <= CHART_POINTS
        assert all(PLOT_LEFT <= x <= PLOT_RIGHT and PLOT_TOP <= y <= PLOT_BOTTOM
                   for x, y in coords)
    # The now curve stops at its longest ride; best runs on to the axis end.
    last_now_x = int(chart.now_points.split()[-1].split(",")[0])
    last_best_x = int(chart.best_area.split(" L ")[1].split()[-1].split(",")[0])
    assert last_now_x < last_best_x
