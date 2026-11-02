"""Pokemon Silver's story flags, for the guide's checks.

``wEventFlags`` is one bit per ``EVENT_*`` constant; engine flags (Pokegear cards,
badges, towns visited...) are bits scattered through WRAM, located by the game's own
table. Both come from pret/pokegold via ``silver_data``. The harness reads these to
find the current guide objective; they're never shown to the agent, who only gets
what a player could see (see ``silver_state``).
"""

from pyboy import PyBoy

from gb_agent.games.silver_data import ENGINE_FLAGS, EVENT_FLAGS, SYMBOLS as S


def flag(pb: PyBoy, name: str) -> bool:
    """Whether the ``EVENT_*`` or ``ENGINE_*`` flag ``name`` is set."""
    if name in EVENT_FLAGS:
        bit = EVENT_FLAGS[name]
        addr, mask = S["wEventFlags"] + bit // 8, 1 << bit % 8
    elif name in ENGINE_FLAGS:
        addr, mask = ENGINE_FLAGS[name]
    else:
        raise KeyError(f"no flag {name!r}")
    return bool(pb.memory[addr] & mask)


def known(name: str) -> bool:
    return name in EVENT_FLAGS or name in ENGINE_FLAGS
