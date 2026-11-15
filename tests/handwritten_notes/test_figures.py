"""Tests for handwritten_notes.figures, with the vision call faked."""

import json
import xml.etree.ElementTree as ET

import pytest

from handwritten_notes import figures

PAGES = [(b"page-one", "image/jpeg"), (b"page-two", "image/png")]
TRANSCRIPT = """## Plan
[figure:flowchart: ingest to review loop]
- ship it
---
[sketch: a cat]
[figure:plot: loss falling with epochs]
"""
PLOT = {
    "title": "Training", "x_label": "epochs", "y_label": "loss",
    "curves": [{"label": "train", "points": [[0, 5], [5, 2], [10, 1]]},
               {"label": "val", "kind": "scatter", "points": [[0, 6], [10, 2]]}],
    "annotations": [{"x": 5, "y": 2, "text": "overfits?"}],
}


@pytest.fixture
def model(monkeypatch):
    """Answer by prompt: Mermaid for flowcharts, PLOT JSON for plots."""
    monkeypatch.setattr(figures, "prepare", lambda data, mime: (data, mime))
    calls = []
    replies = {str(figures.FLOWCHART_PROMPT): "```mermaid\nflowchart LR\n  A --> B\n```",
               str(figures.PLOT_PROMPT): json.dumps(PLOT)}

    def fake(template_path, params, images, model_name):
        calls.append((template_path, params, images))
        reply = replies[template_path]
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(figures, "get_vision_response", fake)
    monkeypatch.setattr(figures.mermaid, "render_png", lambda source: b"PNG:" + source.encode())
    return type("Model", (), {"calls": calls, "replies": replies})


def test_finds_figures_with_their_pages_and_skips_sketches():
    found = figures.find_figures(TRANSCRIPT, pages=2)
    assert [(m.kind, m.description, m.page) for m in found] == [
        ("flowchart", "ingest to review loop", 0),
        ("plot", "loss falling with epochs", 1),
    ]


def test_page_is_clamped_to_the_pages_sent():
    [marker] = figures.find_figures("---\n---\n[figure:plot: x]", pages=1)
    assert marker.page == 0


def test_redraws_inline_and_sends_each_figure_its_own_page(model):
    redrawn = figures.redraw_all(TRANSCRIPT, PAGES)

    assert redrawn.transcript == """## Plan
```mermaid
flowchart LR
  A --> B
```
*ingest to review loop*
- ship it
---
[sketch: a cat]
![[{{figure-1}}]]
*loss falling with epochs*
"""
    assert len(redrawn.svgs) == 1
    assert [(images, params) for _, params, images in model.calls] == [
        ([PAGES[0]], {"description": "ingest to review loop", "context": ""}),
        ([PAGES[1]], {"description": "loss falling with epochs", "context": ""}),
    ]


def test_no_markers_means_no_calls(model):
    assert figures.redraw_all("- just text", PAGES) == figures.Redrawn("- just text", [], [])
    assert model.calls == []


@pytest.mark.parametrize("prompt, reply", [
    (figures.FLOWCHART_PROMPT, "Sorry, I can't see a diagram."),
    (figures.FLOWCHART_PROMPT, RuntimeError("model exploded")),
    (figures.PLOT_PROMPT, "not json"),
    (figures.PLOT_PROMPT, json.dumps({"title": "no curves"})),
])
def test_a_failed_redraw_leaves_its_marker(model, prompt, reply):
    model.replies[str(prompt)] = reply
    text = figures.redraw_all(TRANSCRIPT, PAGES).transcript
    kind = "flowchart" if prompt == figures.FLOWCHART_PROMPT else "plot"
    assert f"[figure:{kind}:" in text
    assert text.count("[figure:") == 1  # the other one still got redrawn


def test_render_plot_makes_svg_with_searchable_text():
    svg = figures.render_plot(figures.PlotSpec.model_validate(PLOT))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    for word in (b"Training", b"epochs", b"loss", b"overfits?", b"train", b"val"):
        assert word in svg


def test_render_plot_handles_log_axes_and_ticks():
    spec = figures.PlotSpec.model_validate(
        {**PLOT, "x_log": True, "show_ticks": True, "x_range": [1, 10],
         "curves": [{"points": [[1, 1], [10, 2]], "style": "dashed"}]})
    assert figures.render_plot(spec).startswith(b"<?xml")


def test_every_redraw_gets_a_chat_preview(model):
    previews = figures.redraw_all(TRANSCRIPT, PAGES).previews
    assert [p.description for p in previews] == ["ingest to review loop", "loss falling with epochs"]
    assert previews[0].png == b"PNG:flowchart LR\n  A --> B"
    assert previews[1].png.startswith(b"\x89PNG")


def test_a_failed_flowchart_preview_still_redraws_the_note(model, monkeypatch):
    def broken(source):
        raise RuntimeError("no browser")
    monkeypatch.setattr(figures.mermaid, "render_png", broken)

    redrawn = figures.redraw_all(TRANSCRIPT, PAGES)
    assert "```mermaid\nflowchart LR" in redrawn.transcript
    assert [p.description for p in redrawn.previews] == ["loss falling with epochs"]


def test_for_chat_drops_figures_but_not_other_embeds():
    text = ("intro\n\n```mermaid\nflowchart LR\n  A --> B\n```\n*a loop*\n\n"
            "middle\n![[{{figure-1}}]]\n*a plot*\n\n![[photo.jpg]]\n```python\nx = 1\n```")
    assert figures.for_chat(text) == "intro\n\nmiddle\n\n![[photo.jpg]]\n```python\nx = 1\n```"


def test_for_chat_leaves_unredrawn_markers():
    assert figures.for_chat("[figure:plot: loss]") == "[figure:plot: loss]"


def test_annotation_outside_the_axes_is_still_drawn():
    spec = figures.PlotSpec.model_validate(
        {"y_range": [0, 10], "curves": [{"points": [[0, 1], [10, 9]]}],
         "annotations": [{"x": 5, "y": -1.5, "text": "valley of despair"}]})
    assert b"valley of despair" in figures.render_plot(spec)


def test_smooth_passes_through_every_point():
    points = [(0, 0), (1, 3), (2, 1), (4, 4)]
    curve = figures.smooth(points)
    assert len(curve) > len(points)
    for point in points:
        assert any((abs(curve - point).sum(axis=1) < 1e-9))


def test_two_points_stay_a_straight_line():
    assert figures.smooth([(0, 0), (1, 1)]).tolist() == [[0, 0], [1, 1]]
