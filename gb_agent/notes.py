"""The agent's notes: what it's asked to keep, and cleaning up what it writes.

Notes are all that survives a context clear, so they're worth guarding. Small local
models put things in them that don't belong: their thinking (``<thought>…</thought>``),
a tool call written out as text instead of made (``update_notes(notes="…")``, or
``<parameter=notes>…</parameter>`` markup), and copies of the state report, map grid
and all, which they'll be shown fresh after the next step anyway (and whose routes
go stale as soon as they move). ``clean_notes`` takes those out; if nothing's left,
the caller keeps the old notes.
"""

import re

MAX_NOTES = 2_000

SECTIONS = """\
GOAL: what you're doing right now, and what's next after it.
STORY: what people have told you to do and what's happened (who sent you where, \
items you were given), so you remember why.
MAP: how places connect (e.g. "New Bark Town: Route 29 is off the west edge").
LESSONS: what works and what doesn't (scripts, controls, things that got you stuck)."""

# A tool call written out as text: update_notes(notes="...") or notes="..."
_CALL = re.compile(r'(?:update_notes\s*\(\s*)?notes\s*=\s*"((?:[^"\\]|\\.)*)"\s*\)?', re.S)
_PARAMETER = re.compile(r"<parameter=notes>\s*(.*?)\s*(?:</parameter>|$)", re.S)
_THINKING = re.compile(r"<(thought|think|thinking)\b[^>]*>.*?</\1>", re.S | re.I)
_MARKUP = re.compile(r"</?(?:tool_call|function|parameter)\b[^>]*>|<\|[^|>]*\|>", re.I)
# Lines of a copied map grid: a header of column numbers, or a row number and cells.
_GRID_HEADER = re.compile(r"^\s*(?:-?\d+\s+){3,}-?\d+\s*$")
_GRID_ROW = re.compile(r"^\s*-?\d+(?:\s+\S){3,}\s*$")
_GRID_TITLE = re.compile(r"^\s*Map around you\b.*$", re.I)
# Lines copied from the state report: its own labels, or its routes (which go stale).
_REPORT_LINE = re.compile(r"^\s*(?:Where|Mode|Changes|Next to you|To read or check[^:]*):"
                          r"|\(-?\d+, -?\d+\), route: |you're at \(", re.I)
_HEADING = re.compile(r"^\s*[\w /-]+:\s*$")  # "Exits:" and the like, on a line of its own
_ITEM = re.compile(r"^(?:\s+\S|\s*[-*•]|\s*\d+\.)")  # a line under a heading


def clean_notes(text: str) -> str:
    """``text`` with thinking, tool-call markup and copied state report taken out."""
    text = _THINKING.sub("", text)
    if m := _PARAMETER.search(text):
        text = m.group(1)
    elif m := _CALL.search(text):
        text = m.group(1).replace("\\n", "\n").replace('\\"', '"')
    # Thinking that was never closed, or a closing tag with no opening: drop what's before.
    if (end := re.search(r"</(?:thought|think|thinking)>", text, re.I)):
        text = text[end.end():]
    elif re.match(r"\s*<(?:thought|think|thinking)\b", text, re.I):
        return ""
    text = _MARKUP.sub("", text)
    lines = [line.rstrip() for line in text.splitlines()
             if not (_GRID_HEADER.match(line) or _GRID_ROW.match(line) or _GRID_TITLE.match(line)
                     or _REPORT_LINE.search(line))]
    # A heading whose lines all went, e.g. "Exits:" over a list of copied routes.
    lines = [line for i, line in enumerate(lines)
             if not (_HEADING.match(line) and not _ITEM.match(lines[i + 1] if i + 1 < len(lines)
                                                              else ""))]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def fit(notes: str, limit: int = MAX_NOTES) -> str:
    """``notes`` cut to ``limit`` characters at a line break, keeping the start (where
    GOAL and STORY are)."""
    if len(notes) <= limit:
        return notes
    cut = notes[:limit]
    return cut[:cut.rfind("\n")] if "\n" in cut[limit // 2:] else cut
