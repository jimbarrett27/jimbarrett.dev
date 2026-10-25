"""What the agent is shown after a script runs (no Docker)."""

from gb_agent.trace import Trace, summarize_inputs


def press(button, frame):
    return {"frame": frame, "type": "press", "button": button}


def release(button, frame):
    return {"frame": frame, "type": "release", "button": button}


def test_input_summary():
    events = [press("left", 0), release("left", 8), press("left", 24), release("left", 32),
              press("a", 50), release("a", 54)]
    assert summarize_inputs(events) == "left ×2, a ×1 (held ~7 frames)"


def test_input_summary_mentions_buttons_still_held():
    assert summarize_inputs([press("b", 0)]) == "b ×1; still held: b"
    assert summarize_inputs([{"frame": 0, "type": "tick", "frames": 5}]) == "no buttons pressed"


def test_text_report():
    trace = Trace(
        title="walk(steps=2) @ abc1234", status="ok", usable=True,
        start_frame=100, end_frame=148, value={"moved": 2},
        notes=[{"frame": 120, "label": "first step", "value": None}],
        stdout="hello\n", stdout_bytes=6, inputs="left ×2",
        memory=[("x", [3], [1]), ("map", [24, 7], [24, 7])],
        images=[("before (frame 100)", b"png"), ("after (frame 148)", b"png")],
    )
    text = trace.to_text()
    assert text.startswith("walk(steps=2) @ abc1234: ok")
    assert "frames 100→148 (48 used)" in text
    assert "returned: {'moved': 2}" in text
    assert "x: 03 → 01" in text
    assert "map: 18 07 (unchanged)" in text
    assert "[frame 120] first step" in text
    assert "images: before (frame 100), after (frame 148)" in text


def test_text_fits_the_budget_and_keeps_the_end_of_errors():
    trace = Trace(
        title="flaky()", status="error", usable=True, start_frame=0, end_frame=10,
        error={"type": "ValueError", "message": "bad",
               "traceback": "Traceback\n" + "  frame\n" * 2000 + "ValueError: bad at the end"},
        stdout="x" * 50_000, stdout_bytes=50_000,
    )
    text = trace.to_text(budget=1_500)
    assert len(text) <= 1_500
    assert "ValueError: bad at the end" in text
    assert "(first 50000 of 50000 bytes)" not in text  # nothing was cut by the sandbox


def test_an_unusable_step_says_nothing_was_kept():
    trace = Trace(title="loop()", status="timeout", usable=False, start_frame=5, end_frame=5,
                  problem="no result from the sandbox (timeout: killed after 30s)")
    text = trace.to_text()
    assert "loop(): timeout (nothing kept)" in text
    assert "problem: no result" in text


def _png(color, size=(160, 144), box=None):
    import io

    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, color)
    if box:
        ImageDraw.Draw(image).rectangle(box, fill="black")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_screen_change_measures_pixels():
    from gb_agent.trace import screen_change

    white = _png("white")
    assert screen_change(white, white) == 0
    assert screen_change(white, _png("white", box=(0, 0, 15, 8))) == 16 * 9 / (160 * 144)
    assert screen_change(white, _png("red")) == 1.0
    assert screen_change(white, _png("white", size=(10, 10))) == 1.0


def test_screen_change_in_plain_words():
    from gb_agent.trace import describe_change

    assert describe_change(0).startswith("unchanged")
    assert describe_change(0.005) == "a tiny part of the screen changed (0.5% of pixels)"
    assert describe_change(0.26) == "part of the screen changed (26% of pixels)"
    assert describe_change(0.55).startswith("most of the screen")


def test_screen_change_appears_in_the_report():
    trace = Trace(title="t()", status="ok", usable=True, start_frame=0, end_frame=1,
                  screen_change=0.005)
    assert "screen: a tiny part of the screen changed" in trace.to_text()


def test_the_game_state_goes_near_the_top_and_outside_the_budget():
    state = "Where: Players House 2F, you're at (3, 3)\n" + "Map around you:\n  ....@....\n" * 20
    trace = Trace(title="walk @ abc1234", status="ok", usable=True, start_frame=0, end_frame=8,
                  inputs="down ×1", stdout="x" * 5_000, stdout_bytes=5_000, state=state)
    text = trace.to_text(budget=600)
    lines = text.splitlines()
    assert lines[2] == "inputs: down ×1" and lines[3] == "Where: Players House 2F, you're at (3, 3)"
    assert state in text
    assert "printed" in text  # still room for the rest of the report
    assert len(text) <= 600 + len(state) + 1
