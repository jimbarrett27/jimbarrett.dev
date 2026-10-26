"""The text that went past during a step, not just what's left on screen at the end.

A step that talks to someone and mashes through the conversation ends with the box
closed, so a before/after comparison sees nothing. The host's replay of the step
reads the text boxes every few frames instead and hands them to a ``TextLog``,
which stitches the lines back together: text types out a letter at a time and
scrolls up a line at a time, so the same line turns up partly typed, then whole,
then again one row higher.
"""

RECENT = 3  # lines a scrolled-up line is looked for among
MAX_LINES = 60


class TextLog:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.on_screen: list[str] = []  # the lines in the boxes at the last sample
        self._last: list[list[str]] | None = None

    def add(self, boxes: list[list[str]]) -> None:
        """One sample: the text in every box on screen, line by line."""
        if boxes == self._last:
            return
        self._last = boxes
        self.on_screen = [line for box in boxes for line in box]
        for line in self.on_screen:
            self._add_line(line)

    def _add_line(self, line: str) -> None:
        recent = self.lines[-RECENT:]
        if any(old.startswith(line) for old in recent):
            return  # already seen: scrolled up, or still typing out an earlier sample's line
        if self.lines and line.startswith(self.lines[-1]):
            self.lines[-1] = line  # the last line, typed further
        elif len(self.lines) < MAX_LINES:
            self.lines.append(line)

    @property
    def gone_by(self) -> bool:
        """Was there text that's no longer on screen at the end?"""
        return any(line not in self.on_screen for line in self.lines)

    def text(self) -> str:
        """Everything seen, as running text."""
        return join(self.lines)


def join(lines: list[str]) -> str:
    """Lines of text as running text (a line ending in "-" was broken mid-word)."""
    out = ""
    for line in lines:
        out += line if not out or out.endswith("-") else " " + line
    return out
