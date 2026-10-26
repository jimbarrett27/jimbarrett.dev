"""The Pokemon Silver state report.

The ROM tests replay a real run (Claude Haiku's, which reached Route 29) from the
start state, using the inputs in ``fixtures/silver_haiku_inputs.txt``, and check
what the report says at known moments of it. The ``describe`` tests need no ROM.
"""

from pathlib import Path

import pytest

from gb_agent.emulator import apply_event, boot, save_state
from gb_agent.games import SILVER
from gb_agent.games.silver_data import SYMBOLS
from gb_agent.games.silver_state import STEP, _tile, describe, observe, text_boxes
from gb_agent.steps import replay as replay_step
from gb_agent.text_log import TextLog

INPUTS = Path(__file__).parent / "fixtures" / "silver_haiku_inputs.txt"


def _steps() -> list[tuple[int, list[dict]]]:
    steps = []
    for line in INPUTS.read_text().splitlines():
        if line.startswith("#"):
            continue
        step, *tokens = line.split()
        steps.append((int(step), [
            {"type": "tick", "frames": int(t[1:])} if t[0] == "t"
            else {"type": "press" if t[0] == "+" else "release", "button": t[1:]}
            for t in tokens]))
    return steps


def _replayed(silver_rom, upto: int):
    """A game at the end of step ``upto`` of the recorded run, settled for half a second."""
    pyboy = boot(silver_rom, SILVER.load_start_state())
    for step, events in _steps():
        if step > upto:
            break
        for event in events:
            apply_event(pyboy, event)
    apply_event(pyboy, {"type": "tick", "frames": 30})
    return pyboy


def _tap(pyboy, button: str) -> None:
    for event in ({"type": "press", "button": button}, {"type": "tick", "frames": 8},
                  {"type": "release", "button": button}, {"type": "tick", "frames": 12}):
        apply_event(pyboy, event)


def _follow(pyboy, route: str, then: str | None) -> None:
    """Walk a route one tap per tile, as an agent would (a tap that only turns the
    player is repeated), then take the last step through an exit or over an edge."""
    parts = [p for p in route.split(", ") if p]
    if then and not then.startswith("face"):
        parts.append(" ".join(then.split()[:2]))
    for part in parts:
        direction, count = (part.split()[1], 1) if part.startswith("jump") else part.split()
        for _ in range(int(count)):
            here = lambda: (observe(pyboy)["player"]["x"], observe(pyboy)["player"]["y"])  # noqa: E731
            before = here()
            _tap(pyboy, direction)
            if here() == before:
                _tap(pyboy, direction)
    apply_event(pyboy, {"type": "tick", "frames": 90})


@pytest.fixture(scope="module")
def replay(silver_rom):
    """{step: (observation, the game's own collision of the 4 tiles around the player)}."""
    pyboy = boot(silver_rom, SILVER.load_start_state())
    seen = {0: (observe(pyboy), None)}
    try:
        for step, events in _steps():
            for event in events:
                apply_event(pyboy, event)
            game = {d: pyboy.memory[SYMBOLS[f"wTile{d.title()}"]]
                    for d in ("up", "down", "left", "right")}
            seen[step] = (observe(pyboy), game)
    finally:
        pyboy.stop(save=False)
    return seen


def test_addresses_match_the_ones_found_by_hand():
    found = {label: ref.addr for label, ref in SILVER.progress_values.items()}
    assert found == {"map_group": SYMBOLS["wMapGroup"], "map_number": SYMBOLS["wMapNumber"],
                     "y": SYMBOLS["wYCoord"], "x": SYMBOLS["wXCoord"]}


def test_the_bedroom_at_the_start(replay):
    obs, _ = replay[0]
    assert obs["map"]["name"] == "Players House 2F"
    assert (obs["player"]["x"], obs["player"]["y"], obs["player"]["facing"]) == (3, 3, "down")
    assert obs["exits"] == [{"x": 7, "y": 0, "to": "Players House 1F", "route": "right 4, up 3"}]
    assert obs["adjacent"] == {"up": "floor", "down": "floor", "left": "floor", "right": "floor"}
    rows = obs["grid"]["rows"]
    assert rows[4][4] == "@" and rows[1][8] == "D"  # the player, and the stairs at (7, 0)
    assert obs["party"] == [] and obs["money"] == 3000


def test_mom_talking_downstairs(replay):
    obs, _ = replay[30]
    assert obs["map"]["name"] == "Players House 1F"
    assert obs["text"] == [["He said he wanted", "you to do"]]
    assert obs["script_running"]
    assert [(p["name"], p["x"], p["y"]) for p in obs["people"]] == [("Mom", 9, 2)]
    assert obs["adjacent"]["down"] == "Mom"
    assert obs["adjacent"]["up"] == "exit to Players House 2F"


def test_reading_text_during_a_replay_gets_the_whole_conversation(silver_rom):
    """Mom's talk downstairs, as one long step: it's over by the end, but the text
    read along the way has all of it, and reading it doesn't change the replay."""
    pyboy = _replayed(silver_rom, 24)
    start = save_state(pyboy)
    pyboy.stop(save=False)
    events = [e for step, events in _steps() if 25 <= step <= 40 for e in events]
    log = TextLog()
    looked = replay_step(silver_rom, start, events, look=lambda pb: log.add(text_boxes(pb)))
    assert looked == replay_step(silver_rom, start, events)
    assert "He said he wanted you to do some-thing for him." in log.text()
    assert "SILVER received POKéGEAR." in log.text()
    assert log.gone_by


def test_a_step_that_ends_mid_walk_reports_where_the_player_is_going(replay):
    obs, _ = replay[95]  # the screenshot shows the player right under the door
    assert (obs["player"]["x"], obs["player"]["y"]) == (13, 6)
    assert obs["player"]["walking"]
    assert obs["adjacent"]["up"] == "exit to Players House 1F"


def test_elms_lab_with_the_starters_on_the_table(replay):
    obs, _ = replay[149]
    names = [(p["name"], p["x"], p["y"]) for p in obs["people"]]
    assert ("Elm", 5, 2) in names and ("Poke Ball", 7, 3) in names
    assert {"x": 6, "y": 1, "what": "bookshelf"} in obs["things"]
    assert obs["party"][0]["species"] == "Cyndaquil"
    assert [m["name"] for m in obs["party"][0]["moves"]] == ["Tackle", "Leer"]


def test_a_wild_battle(replay):
    obs, _ = replay[262]
    assert obs["battle"]["kind"] == "wild"
    assert obs["battle"]["enemy"] == {"species": "Pidgey", "level": 3, "hp_percent": 6}
    assert obs["battle"]["you"]["species"] == "Cyndaquil"
    assert obs["text"] == [["Enemy PIDGEY", "used TACKLE!"]]
    assert "grid" not in obs  # the map buffers hold battle graphics


def test_ledges_on_route_29(replay):
    obs, _ = replay[244]
    assert obs["map"]["name"] == "Route 29"
    assert any(c in row for row in obs["grid"]["rows"] for c in "v<>")


def test_no_map_while_the_buffer_holds_something_else(replay):
    obs, _ = replay[245]  # a wild battle is about to start
    assert obs["grid"] is None and obs["adjacent"] is None
    assert "not readable right now" in describe(None, obs)


def test_routes_avoid_furniture_and_use_mats_and_edges(replay):
    downstairs, _ = replay[30]
    mom = next(p for p in downstairs["people"] if p["name"] == "Mom")
    assert (mom["route"], mom["then"]) == ("", "face down")  # she's right below
    door = next(e for e in downstairs["exits"] if (e["x"], e["y"]) == (7, 7))
    assert door["then"] == "down 1 more to go through"  # a mat, not a door
    town, _ = replay[95]
    assert {e["side"]: e["to"] for e in town["edges"]} == {"west": "Route 29", "east": "Route 27"}
    assert next(e for e in town["edges"] if e["side"] == "east")["route"] is None  # water


@pytest.mark.parametrize("step, kind, target", [
    (0, "exits", "Players House 1F"),  # around the furniture to the stairs
    (95, "exits", "Elms Lab"),  # across town to a door
    (244, "edges", "New Bark Town"),  # along Route 29, around its ledges, over the edge
])
def test_following_a_route_gets_there(silver_rom, step, kind, target):
    """Story scripts and wild battles can stop a walk part way, so these are moments
    of the recorded run where nothing does."""
    pyboy = _replayed(silver_rom, step)
    try:
        item = next(i for i in observe(pyboy)[kind] if i["to"] == target)
        _follow(pyboy, item["route"], item.get("then"))
        assert observe(pyboy)["map"]["name"] == target
    finally:
        pyboy.stop(save=False)


def test_collision_agrees_with_the_game_wherever_the_player_stands(replay):
    """The game's own movement checks are the ground truth for the 4 tiles around the
    player; they're stale just after a warp (so exit tiles are skipped) and mid-walk."""
    checked = 0
    for step, (obs, game) in replay.items():
        p = obs["player"]
        on_exit = any((e["x"], e["y"]) == (p["x"], p["y"]) for e in obs.get("exits", []))
        if game is None or obs.get("grid") is None or p["walking"] or on_exit:
            continue
        rows, left, top = obs["grid"]["rows"], obs["grid"]["left"], obs["grid"]["top"]
        for d, (dx, dy) in STEP.items():
            x, y = p["x"] + dx, p["y"] + dy
            char = rows[y - top][x - left]
            if char not in "NDS " and game[d] != 0xFF:  # 0xFF: off the map
                assert char == _tile(game[d])[0], (step, d, char, hex(game[d]))
                checked += 1
    assert checked > 500


# -- describe, on hand-made observations ----------------------------------------

def _obs(**changes) -> dict:
    obs = {
        "map": {"group": 24, "number": 7, "name": "Players House 2F", "width": 8, "height": 6},
        "player": {"x": 3, "y": 3, "facing": "down", "walking": False},
        "script_running": False, "text": [], "battle": None, "party": [], "bag": [],
        "money": 3000, "badges": 0, "people": [],
        "exits": [{"x": 7, "y": 0, "to": "Players House 1F", "route": "right 4, up 3"}],
        "things": [],
        "adjacent": {"up": "wall", "down": "floor", "left": "floor", "right": "floor"},
        "grid": {"left": -1, "top": -1, "rows": [" ######SD", "   ...@..."]},
    }
    for key, value in changes.items():
        obs[key] = {**obs[key], **value} if isinstance(value, dict) and obs.get(key) else value
    return obs


def test_a_move_during_a_cutscene_says_walking_is_locked():
    # Qwen, 2026-10-26: Mom walking up to the player downstairs
    locked = _obs(script_running=True)
    text = describe(locked, locked, ["left"])
    assert "a cutscene or conversation has control, so you can't walk" in text
    assert "toward: floor" not in text


def test_the_naming_screen_says_what_the_cursor_is_on():
    naming = {"title": "CYNDAQUIL'S NICKNAME?", "name": "", "max": 10, "cursor": "A",
              "column": 0, "row": 0}
    opened = _obs(naming=naming)
    text = describe(_obs(text=[["Give a nickname?"]]), opened, ["a"])
    assert "Changes: naming screen opened" in text
    assert "Mode: naming screen (CYNDAQUIL'S NICKNAME?)" in text
    assert 'Name so far: "" (0 of 10 letters)' in text and "Cursor on: A" in text
    assert "Where:" not in text and "Map around you" not in text  # the map isn't on screen
    typed = _obs(naming={**naming, "name": "  ", "cursor": "END", "column": 8, "row": 4})
    assert 'name: "" -> "  "; cursor moved to: END' in describe(opened, typed, ["a", "start"])
    assert 'naming screen closed (the name was "  "' in describe(typed, _obs(), ["a"])


def test_a_blocked_move_says_what_is_in_the_way():
    facing_up = _obs(player={"facing": "up"})
    text = describe(facing_up, facing_up, ["up", "up"])
    assert "Changes: didn't move (pressed up); facing up, toward: wall" in text


def test_a_tap_that_only_turns_says_so():
    text = describe(_obs(), _obs(player={"facing": "left"}), ["left"])
    assert "Changes: turned to face left, without moving" in text


def test_moving_and_changing_map():
    assert "moved: (3, 3) -> (3, 5)" in describe(_obs(), _obs(player={"y": 5}), ["down"])
    downstairs = _obs(map={"number": 6, "name": "Players House 1F"})
    assert "map changed: Players House 2F -> Players House 1F" in describe(_obs(), downstairs)


def test_text_new_same_and_closed():
    talking = _obs(text=[["Hello!"]])
    assert "new text on screen" in describe(_obs(), talking, ["a"])
    assert "same text still on screen" in describe(talking, talking, ["a"])
    assert "text closed" in describe(talking, _obs(), ["a"])
    assert "Text on screen: Hello!" in describe(None, talking)


def test_items_money_and_battles_in_the_changes():
    battle = {"kind": "wild", "you": {"species": "Cyndaquil", "level": 5, "hp": 19, "max_hp": 19},
              "enemy": {"species": "Pidgey", "level": 3, "hp_percent": 100}}
    after = _obs(bag=[{"name": "Potion", "count": 1}], money=2900, battle=battle)
    text = describe(_obs(), after)
    assert "battle started (wild): Pidgey L3" in text
    assert "bag: Potion +1" in text and "money: $3000 -> $2900" in text
    assert "Battle (wild): your Cyndaquil L5 HP 19/19 vs Pidgey L3 HP 100%" in text


def test_no_changes_line_without_a_before():
    text = describe(None, _obs())
    assert not text.startswith("Changes") and text.startswith("Where: Players House 2F")
    assert "Exits: to Players House 1F at (7, 0), route: right 4, up 3" in text
    assert "Map around you (x across, y down):" in text


def test_the_grid_is_labelled_with_coordinates():
    grid = {"left": 5, "top": -1, "rows": ["     ", "#.@.D", "#...."]}
    text = describe(None, _obs(grid=grid))
    lines = text.splitlines()
    at = lines.index("Map around you (x across, y down):")
    assert lines[at + 1:at + 4] == [
        "       5  6  7  8  9",  # row -1 is off the map, so it's left out
        "   0   #  .  @  .  D",
        "   1   #  .  .  .  .",
    ]
