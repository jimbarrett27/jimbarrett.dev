"""The harness's journal for the agent: places and conversations (no ROM)."""

from gb_agent.games.silver_journal import recall, remember


def _obs(map_name="New Bark Town", text=(), facing="down", ahead="floor", people=(),
         exits=("Elms Lab",), edges=None):
    return {"map": {"name": map_name}, "player": {"facing": facing}, "text": [list(text)] if text else [],
            "people": [{"name": p} for p in people], "adjacent": {facing: ahead},
            "exits": [{"to": e} for e in exits],
            "edges": [{"side": s, "to": t} for s, t in (edges or {}).items()]}


def test_places_record_exits_and_edges_newest_last():
    journal = {}
    remember(journal, None, _obs(edges={"west": "Route 29"}), [])
    remember(journal, None, _obs("Elms Lab", exits=["New Bark Town"]), [])
    remember(journal, None, _obs(exits=["Players House 1F"]), [])
    text = recall(journal)
    assert text.startswith("From the game itself")
    assert text.index("- Elms Lab") < text.index("- New Bark Town")
    assert "- New Bark Town: exits to Elms Lab, Players House 1F; edges: west to Route 29" in text


def test_a_conversation_over_several_steps_is_joined_up_and_kept():
    journal = {}
    facing_elm = _obs("Elms Lab", facing="up", ahead="Elm", people=["Elm"])
    talking = _obs("Elms Lab", text=["is"])
    remember(journal, facing_elm, talking, ["MR.POKéMON lives near CHERRYGROVE, the next city. It's almost a direct route to"])
    remember(journal, talking, talking, ["direct route to there. SILVER, I'm counting on you!"])
    assert "(still going)" in recall(journal)
    remember(journal, talking, _obs("Elms Lab"), [])  # a quiet step: it's over
    text = recall(journal)
    assert ('- in Elms Lab, facing Elm: "MR.POKéMON lives near CHERRYGROVE, the next city. '
            "It's almost a direct route to there. SILVER, I'm counting on you!\"") in text


def test_the_same_conversation_again_is_counted():
    journal = {}
    for _ in range(3):
        remember(journal, _obs(ahead="Teacher", people=["Teacher"]), _obs(),
                 ["Oh! Your POKéMON is adorable!"])
        remember(journal, _obs(), _obs(), [])
    assert '- in New Bark Town, facing Teacher (3 times): "Oh! Your POKéMON is adorable!"' \
        in recall(journal)


def test_an_empty_journal_shows_nothing():
    assert recall({}) == ""
