"""What the harness remembers for the agent: places it has been and what it was told.

The agent's own notes are only as good as the model writing them; on 2026-10-26 Qwen
heard Elm's errand (go to Mr. Pokémon, near Cherrygrove), updated its notes twice
straight after, and left it out both times. So the harness keeps two lists itself,
from the game's memory rather than the model's, and shows them with the notes
after every context clear:

- **places**: each map visited, where its exits lead and what its edges join
- **conversations**: the text of the last few, where they happened and who the
  player was facing, with a count when the same one comes round again

``remember`` folds one kept step into the journal (a JSON-able dict), so a journal
can be rebuilt for any step from a run's steps.jsonl; ``recall`` is the text shown.
"""

from gb_agent.text_log import join

MAX_CONVERSATIONS = 8
MAX_SAID = 600  # characters of each conversation shown
MAX_PLACES = 15  # the most recently visited
MAX_TALKING = 4_000  # characters kept of a conversation still going


def remember(journal: dict, before: dict | None, after: dict, text: list[str]) -> None:
    """Fold one kept step in: ``before``/``after`` are its observations, ``text`` the
    lines that went by during it."""
    if after.get("exits") is not None:  # the map's on screen (not a battle or a menu)
        name = after["map"]["name"]
        places = journal.setdefault("places", {})
        place = places.pop(name, None) or {"exits": [], "edges": {}}
        for e in after["exits"]:
            if e["to"] not in place["exits"]:
                place["exits"].append(e["to"])
        for e in after.get("edges") or []:
            place["edges"][e["side"]] = e["to"]
        places[name] = place  # re-inserted, so the dict runs oldest visit first

    talking = journal.get("talking")
    if text:
        if talking is None:
            where = (before or after)["map"]["name"]
            talking = journal["talking"] = {"where": where, "with": _facing(before), "said": ""}
        talking["said"] = _overlap(talking["said"], join(text))[-MAX_TALKING:]
    elif talking is not None and not after["text"]:  # a quiet step: it's over
        _finish(journal, talking)


def _overlap(said: str, new: str) -> str:
    """``new`` joined onto ``said``, where ``new`` may start with the end of ``said``: a
    step starts with whatever was on screen, often a line the last step saw half typed."""
    for k in range(min(len(said), len(new)), 1, -1):
        if said.endswith(new[:k]):
            return said + new[k:]
    return f"{said} {new}" if said else new


def _facing(obs: dict | None) -> str | None:
    """The person the player is facing, if any."""
    if not obs:
        return None
    ahead = (obs.get("adjacent") or {}).get(obs["player"]["facing"])
    return ahead if ahead in {p["name"] for p in obs.get("people") or []} else None


def _finish(journal: dict, talking: dict) -> None:
    journal.pop("talking")
    said = talking["said"]
    conversations = journal.setdefault("conversations", [])
    for i, old in enumerate(conversations):
        if old["said"] == said and old["where"] == talking["where"]:
            conversations.append({**conversations.pop(i), "times": old["times"] + 1})
            return
    conversations.append({"where": talking["where"], "with": talking["with"], "said": said,
                          "times": 1})
    del conversations[:-MAX_CONVERSATIONS]


def recall(journal: dict) -> str:
    """The journal as shown to the agent, or "" if there's nothing in it yet."""
    lines = []
    if places := journal.get("places"):
        lines.append("Places you've been (newest last):")
        for name, place in list(places.items())[-MAX_PLACES:]:
            parts = []
            if place["exits"]:
                parts.append("exits to " + ", ".join(place["exits"]))
            if place["edges"]:
                parts.append("edges: " + ", ".join(f"{side} to {to}"
                                                    for side, to in place["edges"].items()))
            lines.append(f"- {name}: " + ("; ".join(parts) or "no exits seen"))
    conversations = list(journal.get("conversations") or [])
    if talking := journal.get("talking"):
        conversations.append({**talking, "said": talking["said"] + " (still going)",
                              "times": 1})
    if conversations:
        lines.append("What you've been told, oldest first:")
        for c in conversations:
            said = c["said"] if len(c["said"]) <= MAX_SAID else c["said"][:MAX_SAID] + "…"
            who = f", facing {c['with']}" if c["with"] else ""
            times = f" ({c['times']} times)" if c["times"] > 1 else ""
            lines.append(f"- in {c['where']}{who}{times}: \"{said}\"")
    if not lines:
        return ""
    return "From the game itself (read from its memory, so always accurate):\n" + "\n".join(lines)
