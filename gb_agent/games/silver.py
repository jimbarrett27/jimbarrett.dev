"""Pokemon Silver (USA, Europe).

The ROM isn't in the repo; it lives in ``roms/`` under ``gb_agent.paths.gb_agent_dir()``.

Runs start in the player's bedroom, just after new-game setup. ``SETUP`` is the
input sequence that gets there from power-on, played once by hand (2026-10-21,
watching screenshots) and recorded:

- title screen, NEW GAME
- the clock: left at its default, 10:00, then 0 minutes. The cartridge clock is
  locked, so in-game time stays 10:00 (daytime) for good.
- Professor Oak's introduction; the player's name is the first preset, SILVER
- ends at frame 7452, standing in the bedroom with control

The day of the week isn't set yet; Mom asks downstairs.

The progress values were first found by watching memory (2026-10-21); they're
``wMapGroup``, ``wMapNumber``, ``wYCoord`` and ``wXCoord`` in the pret/pokegold
disassembly, which ``silver_state`` reads everything else from to describe the game
to the agent after each step (see ``silver_gen`` for where the addresses come from).
"""

from pathlib import Path

from gb_agent.paths import gb_agent_path

from gb_agent.games import silver_state
from gb_agent.games.profile import GameProfile, MemRef

_A = "a:4:100"

SETUP = (
    "t:720", "start:4:60", "start:4:60", "a:4:120",  # title screen, NEW GAME
    "t:120", "a:4:90", "t:60", *["a:4:90"] * 8,  # wake-up call; clock at 10:00, 0 min
    "t:120", *[_A] * 17,  # Oak's introduction
    "t:90", *[_A] * 11,
    "down:4:20", _A,  # name: the first preset, SILVER
    "t:60", *[_A] * 5,
    "t:200", *[_A] * 3,
    "t:200", _A, _A,
    "t:300", _A,
    "t:300",  # into the bedroom
)

SILVER = GameProfile(
    name="silver",
    rom=gb_agent_path("roms", "pokemon_silver.gbc"),
    power_on_state=gb_agent_path("states", "silver_power_on.state"),
    start_state=gb_agent_path("states", "silver_bedroom.state"),
    setup=SETUP,
    progress_values={
        "map_group": MemRef(0xDA00),  # 24 in the player's house
        "map_number": MemRef(0xDA01),  # 7 = bedroom, 6 = downstairs
        "y": MemRef(0xDA02),
        "x": MemRef(0xDA03),
    },
    seed_library=Path(__file__).parent / "silver_library",
    notes=(
        "Pokemon Silver for the Game Boy Color. You are SILVER, starting in your "
        "bedroom upstairs at home in New Bark Town. The in-game time is always 10:00."
    ),
    observe=silver_state.observe,
    describe=silver_state.describe,
    read_text=silver_state.text_boxes,
    state_help=silver_state.STATE_HELP,
)
