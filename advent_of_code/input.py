"""Puzzle inputs, which are deliberately kept out of git.

Advent of Code asks that inputs aren't published, so they live with the rest of
the runtime data under ``JIMBARRETT_DATA_DIR`` (the repo root when unset), at
``aoc_inputs/<year>/day_<NN>.txt``. That directory is gitignored.
"""

from pathlib import Path

from util.paths import data_path


def input_path(year: int, day: int) -> Path:
    return data_path("aoc_inputs", str(year), f"day_{day:02d}.txt")


def get_input(year: int, day: int) -> str:
    """The raw puzzle input, trailing newline included."""
    return input_path(year, day).read_text()
