"""The guide: objectives, which one is current, and Silver's story flags.

The ROM test replays the recorded Haiku run (see ``test_silver_state``) to the end,
on Route 29 with a starter, and checks the flags the guide's first objectives use.
"""

import json

import pytest

from gb_agent import guide
from gb_agent.games import silver_flags
from gb_agent.games.silver_data import ENGINE_FLAGS, EVENT_FLAGS, SYMBOLS

from tests.gb_agent.test_silver_state import _replayed


def _objectives(tmp_path, items):
    path = tmp_path / "silver.json"
    path.write_text(json.dumps(items))
    return guide.load(path)


def _three(tmp_path):
    return _objectives(tmp_path, [
        {"id": id_, "where": "somewhere", "do": f"do {id_}", "done_when": [f"F_{id_}"]}
        for id_ in ("a", "b", "c")])


def test_the_current_objective_is_the_first_not_done(tmp_path):
    objectives = _three(tmp_path)
    assert guide.current(objectives, lambda name: False) == 0
    assert guide.current(objectives, lambda name: name == "F_a") == 1


def test_a_skipped_objective_doesnt_hold_the_guide_back(tmp_path):
    objectives = _three(tmp_path)
    assert guide.current(objectives, lambda name: name in {"F_a", "F_c"}) is None
    assert guide.current(objectives, lambda name: name == "F_b") == 2


def test_an_objective_needs_all_its_flags(tmp_path):
    objectives = _objectives(tmp_path, [
        {"id": "a", "where": "x", "do": "y", "done_when": ["F1", "F2"]}])
    assert guide.done(objectives, lambda name: name == "F1") == [False]
    assert guide.done(objectives, lambda name: True) == [True]


def test_show_gives_now_and_then(tmp_path):
    objectives = _three(tmp_path)
    assert guide.show(objectives, 1) == "Now (somewhere): do b\nThen (somewhere): do c"
    assert guide.show(objectives, 2) == "Now (somewhere): do c"
    assert "everything" in guide.show(objectives, None)


@pytest.mark.parametrize("items", [
    [{"id": "a", "where": "x", "do": "y", "done_when": []}],
    [{"id": "a", "where": "x", "do": "y", "done_when": ["F"]}] * 2,
])
def test_bad_objective_files_are_refused(tmp_path, items):
    with pytest.raises(ValueError):
        _objectives(tmp_path, items)


def test_flag_addresses_come_from_pokegold():
    assert SYMBOLS["wEventFlags"] == 0xD7B7
    assert ENGINE_FLAGS["ENGINE_POKEGEAR"] == (0xD67C, 0x80)  # wPokegearFlags, bit 7
    assert ENGINE_FLAGS["ENGINE_MAP_CARD"] == (0xD67C, 0x01)
    assert ENGINE_FLAGS["ENGINE_ZEPHYRBADGE"] == (SYMBOLS["wJohtoBadges"], 0x01)
    assert EVENT_FLAGS["EVENT_GOT_A_POKEMON_FROM_ELM"] == 26
    assert silver_flags.known("EVENT_BEAT_FALKNER") and not silver_flags.known("EVENT_NOPE")


def test_flags_on_route_29_with_a_starter(silver_rom):
    pyboy = _replayed(silver_rom, 300)
    try:
        flag = lambda name: silver_flags.flag(pyboy, name)  # noqa: E731
        assert flag("ENGINE_POKEGEAR") and flag("EVENT_GOT_A_POKEMON_FROM_ELM")
        assert not flag("ENGINE_FLYPOINT_CHERRYGROVE")
        assert not flag("EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON")
        with pytest.raises(KeyError):
            flag("EVENT_NOPE")
    finally:
        pyboy.stop(save=False)
