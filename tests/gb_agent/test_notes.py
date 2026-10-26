"""Cleaning up the notes a model writes (no ROM, no model)."""

from gb_agent.notes import clean_notes, fit


def test_plain_notes_are_left_alone():
    notes = "GOAL: get to Route 29.\nSTORY: Elm wants an egg from Mr. Pokémon.\nLESSONS:\n- tap, don't press"
    assert clean_notes(notes) == notes


def test_thinking_is_taken_out():
    assert clean_notes("<thought>Let me think.</thought>GOAL: leave the lab.") == "GOAL: leave the lab."
    # Unclosed at the start: thinking all the way, nothing to keep
    assert clean_notes("<thought\nThe user wants me to update my notes") == ""


def test_a_tool_call_written_out_as_text_gives_its_notes():
    # Gemma, 2026-10-25 step 120: thinking, then the call as text
    reply = ('<thought\nThe user wants me to update my notes.\n</thought>'
             'update_notes(notes="GOAL: head west.\\nSTORY: got a \\"Potion\\".")')
    assert clean_notes(reply) == 'GOAL: head west.\nSTORY: got a "Potion".'
    # Qwen, 2026-10-26: XML tool-call markup around the notes
    reply = ("<tool_call>\n<function=update_notes>\n<parameter=notes>\nGOAL: name it.\n"
             "</parameter>\n</function>\n</tool_call>")
    assert clean_notes(reply) == "GOAL: name it."


def test_copied_state_report_is_taken_out():
    reply = """\
Location: Players House 1F (10x8 tiles), at (7, 4) facing up.
Mode: overworld
People:
- Mom at (7, 3), route: face up
Exits:
- to New Bark Town at (6, 7), route: down 2, left 1, down 1
Map around you (x across, y down):
       1  2  3  4  5
   4   #  .  .  .  .
   8   .  .  @  N  .
GOAL: talk to Mom.
Exits:
- New Bark Town via the mat"""
    assert clean_notes(reply) == ("Location: Players House 1F (10x8 tiles), at (7, 4) facing up.\n"
                                  "GOAL: talk to Mom.\nExits:\n- New Bark Town via the mat")


def test_long_notes_are_cut_at_a_line_keeping_the_start():
    notes = "GOAL: west.\n" + "\n".join(f"LESSON {i}: something learned" for i in range(200))
    cut = fit(notes)
    assert len(cut) <= 2_000 and cut.startswith("GOAL: west.") and cut.endswith("learned")
