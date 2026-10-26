"""Everything game-specific, behind one dataclass.

The rest of gb_agent only knows about buttons, frames, the screen and memory, so
adding a game means writing a profile, not changing the harness. A profile may also
describe the game state to the agent (``observe``/``describe``), read host-side
after each kept step; without them the agent only gets screenshots. Whether the
cartridge has a clock (and so needs locking) is read from the ROM header, not
declared here.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pyboy import PyBoy

from gb_agent.emulator import RecordingGame, boot, power_on_state, save_state


@dataclass(frozen=True)
class MemRef:
    """A labelled stretch of game memory."""

    addr: int
    length: int = 1
    bank: int | None = None


def apply_setup(game: RecordingGame, commands: tuple[str, ...]) -> None:
    """Play a profile's setup inputs.

    Each command is ``t:N`` (wait N frames), ``BUTTON`` (a short tap), or
    ``BUTTON:HOLD:AFTER`` (hold for HOLD frames, then wait AFTER frames).
    """
    for command in commands:
        parts = command.split(":")
        if parts[0] == "t" and len(parts) == 2:
            game.tick(int(parts[1]))
        elif len(parts) == 1:
            game.tap(parts[0])
        elif len(parts) == 3:
            game.tap(parts[0], hold=int(parts[1]), after=int(parts[2]))
        else:
            raise ValueError(f"bad setup command {command!r}")


@dataclass(frozen=True)
class GameProfile:
    name: str
    rom: Path
    power_on_state: Path  # the cartridge just switched on; made once and kept
    start_state: Path  # where every run starts: power-on plus `setup`
    setup: tuple[str, ...] = ()  # inputs from power-on to the start (see apply_setup)
    # Logged every step for scoring; read by the harness, never shown to the agent.
    progress_values: dict[str, MemRef] = field(default_factory=dict)
    seed_library: Path | None = None  # scripts copied into each new run's library
    notes: str = ""  # game facts given to the agent
    # The state report: observe(pyboy) -> JSON-able dict, kept with each step;
    # describe(before, after, pressed buttons) -> the text at the top of a report
    # (before is None for a plain description); state_help explains it in the prompt.
    observe: Callable[[PyBoy], dict] | None = None
    describe: Callable[[dict | None, dict, list[str]], str] | None = None
    # read_text(pyboy) -> the text in each box on screen, line by line; read during
    # each step's replay so the report has the text that went by, not just what's left
    read_text: Callable[[PyBoy], list[list[str]]] | None = None
    # A journal the harness keeps for the agent, shown with its notes after a context
    # clear: remember(journal, before, after, text lines) folds in a kept step;
    # recall(journal) -> the text shown ("" for nothing yet).
    remember: Callable[[dict, dict | None, dict, list[str]], None] | None = None
    recall: Callable[[dict], str] | None = None
    state_help: str = ""

    def rom_bytes(self) -> bytes:
        if not self.rom.exists():
            raise FileNotFoundError(f"no ROM for {self.name} at {self.rom}")
        return self.rom.read_bytes()

    def load_start_state(self) -> bytes:
        """The run start state, made the first time it's needed and then kept.

        Kept, not regenerated: a fresh boot stamps the wall-clock time into the
        state, so a remade state would differ byte for byte (though not in play).
        """
        if not self.start_state.exists():
            rom = self.rom_bytes()
            if not self.power_on_state.exists():
                self.power_on_state.parent.mkdir(parents=True, exist_ok=True)
                self.power_on_state.write_bytes(power_on_state(rom))
            pyboy = boot(rom, self.power_on_state.read_bytes())
            try:
                apply_setup(RecordingGame(pyboy, max_frames=10**7), self.setup)
                state = save_state(pyboy)
            finally:
                pyboy.stop(save=False)
            self.start_state.parent.mkdir(parents=True, exist_ok=True)
            self.start_state.write_bytes(state)
        return self.start_state.read_bytes()
