"""Stitching the text that went by during a step back together (no ROM)."""

from gb_agent.text_log import TextLog


def _log(*samples):
    log = TextLog()
    for boxes in samples:
        log.add(boxes)
    return log


def test_lines_typing_out_and_scrolling_up_come_out_once():
    log = _log(
        [["Th"]],
        [["There are only two"]],
        [["There are only two", "of"]],
        [["There are only two", "of us, so we're"]],
        [["of us, so we're"]],  # scrolling up
        [["of us, so we're", "alway"]],
        [["of us, so we're", "always busy."]],
        [],
    )
    assert log.text() == "There are only two of us, so we're always busy."
    assert log.gone_by


def test_a_line_broken_with_a_hyphen_joins_up():
    log = _log([["Call me if some-", "thing comes up."]], [])
    assert log.text() == "Call me if some-thing comes up."


def test_the_same_conversation_twice_shows_twice():
    hello = [[["Yo, SILVER!"]], [["I hear PROF.ELM"]], [["I hear PROF.ELM", "discovered some"]],
             [["discovered some", "new POKéMON."]], []]
    log = _log(*hello, *hello)
    once = "Yo, SILVER! I hear PROF.ELM discovered some new POKéMON."
    assert log.text() == f"{once} {once}"


def test_text_still_on_screen_at_the_end_isnt_gone_by():
    log = _log([], [["Hello!"]])
    assert log.text() == "Hello!"
    assert not log.gone_by
