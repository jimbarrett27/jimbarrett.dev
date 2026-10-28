"""The oracle's digest of a series, from hand-built runs."""

import json

from gb_agent.oracle import digest, events

HOUR = 3600
NOW = 1_800_000_000


def obs(map_name="Route 29", level=6, battle=None, text=(), badges=0, caught=1, party=None):
    return {"map": {"name": map_name}, "battle": battle, "text": [list(text)] if text else [],
            "badges": badges, "money": 3000, "dex": {"caught": caught, "seen": 3},
            "party": party if party is not None else
            [{"species": "Cyndaquil", "nickname": "CYNDAQUIL", "level": level, "hp": 20,
              "max_hp": 21}]}


def make_run(root, run_id, steps, *, resumed_from=None, notes="", said=(), stop=None):
    run = root / run_id
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({
        "run": run_id, "resumed_from": {"run": resumed_from} if resumed_from else None,
        "steps": len(steps), "kept_steps": len(steps), "llm_calls": len(steps), "minutes": 60,
        "frame": 36_000, "stop_reason": stop}))
    (run / "steps.jsonl").write_text("".join(
        json.dumps({"step": n, "kept": True, "time": t, "observation": o}) + "\n"
        for n, (t, o) in enumerate(steps, start=1)) + '{"step": 99, "kept": tr')  # cut short
    (run / "agents.jsonl").write_text("".join(
        json.dumps({"kind": "llm", "time": t, "text": text}) + "\n" for t, text in said))
    if notes:
        (run / "notes.md").write_text(notes)
    return run


def test_the_window_is_detailed_and_earlier_is_milestones(tmp_path):
    first = make_run(tmp_path, "a", [
        (NOW - 30 * HOUR, obs("Players House 2F", party=[])),
        (NOW - 29 * HOUR, obs("New Bark Town", party=[])),
        (NOW - 28 * HOUR, obs("Elms Lab")),  # got Cyndaquil
        (NOW - 27 * HOUR, obs("New Bark Town")),  # been here: not a milestone
        (NOW - 20 * HOUR, obs("Route 29", level=7)),
    ])
    second = make_run(tmp_path, "b", [
        (NOW - 5 * HOUR, obs("Route 46", level=7)),
        (NOW - 4 * HOUR, obs("Route 46", level=7, battle={"kind": "wild", "enemy": {
            "species": "Geodude", "level": 3}})),
        (NOW - 3 * HOUR, obs("Route 46", level=7, text=["SILVER whited", "out!"])),
        (NOW - 2 * HOUR, obs("Players House 2F", level=7)),
    ], resumed_from="a", notes="GOAL: Dark Cave", said=[
        (NOW - 40 * HOUR, "old news"), (NOW - 1 * HOUR, "Heading home.")], stop="max_minutes")

    d = digest([first, second], NOW, previous=[{"time": "t", "text": "Last time..."}])

    earlier = [line.split("  ", 1)[1] for line in d["earlier"]]
    assert earlier == ["in Players House 2F", "went to New Bark Town (first time)",
                       "went to Elms Lab (first time)", "Cyndaquil joined the party (Lv 6)",
                       "went to Route 29 (first time)", "Cyndaquil grew to Lv 7"]
    recent = [line.split("  ", 1)[1] for line in d["recent"]]
    assert recent == ["went to Route 46", "wild battle: Geodude Lv 3",
                      "blacked out (sent back to the last Pokemon Center or home, lost money)",
                      "went to Players House 2F"]
    assert [s.split("  ", 1)[1] for s in d["said"]] == ["Heading home."]
    assert d["notes"] == "GOAL: Dark Cave" and d["status"] == "stopped (max_minutes)"
    assert d["state"]["map"] == "Players House 2F" and d["state"]["party"] == "Cyndaquil Lv 7 HP 20/21"
    assert d["totals"]["llm_calls"] == 9 and d["hours_played"] == 2.0
    assert (d["run"], d["step"]) == ("b", 4)
    assert d["previous"] == [{"time": "t", "text": "Last time..."}]


def test_nothing_to_say_about_an_empty_series():
    d = digest([], NOW)
    assert d["state"] is None and d["recent"] == [] and d["status"] == "no runs yet"


def test_a_nickname_and_a_catch():
    before = obs(caught=1)
    after = obs(caught=2, party=[*before["party"], {"species": "Pidgey", "nickname": "PIDGE",
                                                    "level": 3, "hp": 9, "max_hp": 15}])
    assert [t for t, _ in events(before, after)] == ["Pidgey joined the party (Lv 3)",
                                                    "caught a Pokemon (2 caught)"]
    older = {**obs(), "dex": None}  # from before observations had the Pokedex
    assert events(older, obs(caught=1)) == []
