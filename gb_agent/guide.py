"""The guide: a walkthrough boiled down to objectives the harness can check.

A human-written walkthrough is mostly trainer lists and asides, and a small model
can't tell from it where in the game it is. So the walkthrough is boiled down once,
by hand, into an ordered list of objectives, each with the story flags that are set
once it's done (``done_when``). The harness reads those flags from the game's memory,
so it always knows which objective is current; the agent never has to work that out.

The objectives file is JSON, a list of:

    {"id": "mystery-egg", "section": "c07", "where": "Route 30",
     "do": "Take the right-hand path north to Mr. Pokemon's house...",
     "done_when": ["EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON"]}

It lives in the data directory (``guide/<game>.json``), not the repo: it's derived
from a copyrighted walkthrough that's ours to use but not to republish. The flag
names are the game profile's business (for Silver, pret/pokegold's names).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gb_agent.paths import gb_agent_path


@dataclass(frozen=True)
class Objective:
    id: str
    section: str  # where it comes from in the walkthrough, e.g. "c07"
    where: str
    do: str
    done_when: tuple[str, ...]  # flags that are all set once it's done


def guide_path(game: str) -> Path:
    return gb_agent_path("guide", f"{game}.json")


def load(path: Path) -> list[Objective]:
    objectives = [Objective(o["id"], o.get("section", ""), o["where"], o["do"],
                            tuple(o["done_when"]))
                  for o in json.loads(path.read_text())]
    ids = [o.id for o in objectives]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: objective ids repeat")
    if empty := [o.id for o in objectives if not o.done_when]:
        raise ValueError(f"{path}: no done_when for {empty}")
    return objectives


def done(objectives: list[Objective], flag: Callable[[str], bool]) -> list[bool]:
    """Whether each objective's flags are all set."""
    return [all(flag(name) for name in o.done_when) for o in objectives]


def current(objectives: list[Objective], flag: Callable[[str], bool]) -> int | None:
    """The index of the objective to work on: the first one not done after the last
    one that is, so a skipped step (an optional tower, say) doesn't hold the guide
    back once the story has moved past it. None once they're all done."""
    finished = done(objectives, flag)
    last = max((i for i, d in enumerate(finished) if d), default=-1)
    return next((i for i in range(last + 1, len(objectives)) if not finished[i]), None)


def show(objectives: list[Objective], index: int | None, ahead: int = 1) -> str:
    """The current objective and the next ``ahead``, as text for the agent."""
    if index is None:
        return "Guide: you've done everything the guide covers."
    lines = []
    for i in range(index, min(index + 1 + ahead, len(objectives))):
        o = objectives[i]
        lines.append(f"{'Now' if i == index else 'Then'} ({o.where}): {o.do}")
    return "\n".join(lines)
