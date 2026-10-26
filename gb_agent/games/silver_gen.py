"""Write ``silver_data.py`` from a pret/pokegold checkout.

pokegold (github.com/pret/pokegold) is a disassembly of Gold/Silver that builds a
byte-identical ROM, so its symbol file names every address in the game we run.
This script pulls out the addresses ``silver_state`` reads and the name tables it
shows the agent, so the harness never needs pokegold itself:

    cd <pokegold> && make silver   # needs the rgbds version in .rgbds-version
    uv run python -m gb_agent.games.silver_gen <pokegold>

The checkout used (fc702b6, built with rgbds 1.0.4) lives on the server at
``/mnt/storage/data/gb_agent/pokegold``; its ``pokesilver.gbc`` has the same
SHA-1 as our ROM.
"""

import argparse
import re
import subprocess
from pathlib import Path

OUT = Path(__file__).parent / "silver_data.py"

SYMBOLS = [
    # the map and the screen
    "wTilemap", "wOverworldMapBlocks", "wMapWidth", "wMapHeight", "wMapScriptsBank",
    "wTilesetCollisionBank", "wTilesetCollisionAddress", "wBattleMode", "wScriptRunning",
    "wMapGroup", "wMapNumber", "wYCoord", "wXCoord",
    "wCurMapWarpEventCount", "wCurMapWarpEventsPointer",
    "wCurMapBGEventCount", "wCurMapBGEventsPointer",
    "wTileDown", "wTileUp", "wTileLeft", "wTileRight",  # the game's own movement checks
    "wNorthConnectedMapGroup", "wNorthConnectedMapNumber",  # group $ff: no connection
    "wSouthConnectedMapGroup", "wSouthConnectedMapNumber",
    "wWestConnectedMapGroup", "wWestConnectedMapNumber",
    "wEastConnectedMapGroup", "wEastConnectedMapNumber",
    # people: object structs (the player is the first)
    "wPlayerStruct", "wPlayerMapX", "wPlayerMapY", "wPlayerDirection",
    "wObject1Struct", "wObject1Sprite", "wObject1MapX", "wObject1MapY",
    # what you carry
    "wMoney", "wJohtoBadges", "wNumItems", "wItems", "wNumBalls", "wBalls",
    "wNumKeyItems", "wKeyItems",
    # party structs, and the two Pokemon in a battle
    "wPartyCount", "wPartyMon1", "wPartyMon2", "wPartyMon1Moves", "wPartyMon1PP",
    "wPartyMon1Level", "wPartyMon1Status", "wPartyMon1HP", "wPartyMon1MaxHP",
    "wBattleMonSpecies", "wBattleMonLevel", "wBattleMonHP", "wBattleMonMaxHP",
    "wEnemyMonSpecies", "wEnemyMonLevel", "wEnemyMonHP", "wEnemyMonMaxHP",
    # the naming screen (a union with other screens' data: only read while it's up)
    "wNamingScreenDestinationPointer", "wNamingScreenCurNameLength",
    "wNamingScreenMaxNameLength", "wNamingScreenCursorObjectPointer", "wNamingScreenLetterCase",
]
CONSTANTS = ["NUM_OBJECT_STRUCTS", "PARTY_LENGTH", "NUM_MOVES"]


def symbols(pokegold: Path) -> dict[str, int]:
    found = {}
    for line in (pokegold / "pokesilver.sym").read_text().splitlines():
        if m := re.fullmatch(r"([0-9a-f]+):([0-9a-f]+) (\w+)", line):
            found.setdefault(m[3], int(m[2], 16))
    missing = [s for s in SYMBOLS if s not in found]
    if missing:
        raise SystemExit(f"not in pokesilver.sym: {missing}")
    return {s: found[s] for s in SYMBOLS}


def constants(pokegold: Path) -> dict[str, int]:
    found = {}
    for path in (pokegold / "constants").glob("*.asm"):
        for m in re.finditer(r"DEF (\w+) EQU (\d+)\b", path.read_text()):
            found.setdefault(m[1], int(m[2]))
    missing = [c for c in CONSTANTS if c not in found]
    if missing:
        raise SystemExit(f"constants not found: {missing}")
    return {c: found[c] for c in CONSTANTS}


def consts(path: Path, prefix: str = "") -> dict[int, str]:
    """``const_def`` / ``const NAME`` runs as {value: NAME}; the first name for a value wins.

    With a ``prefix``, only names that start with it are kept (and it's dropped).
    """
    out, value = {}, 0
    for line in path.read_text().splitlines():
        line = line.split(";")[0].strip()
        if m := re.fullmatch(r"const_def(?:\s+(-?\d+))?(?:,.*)?", line):
            value = int(m[1]) if m[1] else 0
        elif m := re.fullmatch(r"const\s+(\w+)", line):
            if m[1].startswith(prefix):
                out.setdefault(value, m[1].removeprefix(prefix))
            value += 1
        elif m := re.fullmatch(r"const_skip(?:\s+(\d+))?", line):
            value += int(m[1]) if m[1] else 1
    return out


def maps(path: Path) -> dict[tuple[int, int], str]:
    out, group, number = {}, 0, 0
    for line in path.read_text().splitlines():
        line = line.split(";")[0].strip()
        if line.startswith("newgroup"):
            group, number = group + 1, 0
        elif m := re.match(r"map_const\s+(\w+)", line):
            number += 1
            out[(group, number)] = m[1]
    return out


def charmap(path: Path) -> dict[int, str]:
    """Printable characters only: no control codes like ``<LF>``, and no kana (the
    Japanese charmap shares the file)."""
    out = {}
    for m in re.finditer(r'charmap "(.*?)",\s*\$([0-9a-f]+)', path.read_text()):
        char = {"<PK>": "PK", "<MN>": "MN"}.get(m[1], m[1])
        if not (char.startswith("<") and len(char) > 1) and not re.search("[\u3040-\u30ff]", char):
            out.setdefault(int(m[2], 16), char)
    return out


def collision(pokegold: Path) -> tuple[dict[int, str], list[int]]:
    names = {}
    text = (pokegold / "constants/collision_constants.asm").read_text()
    for m in re.finditer(r"DEF COLL_(\w+)\s+EQU \$([0-9a-f]+)\s*(;.*)?", text):
        if not (m[3] and re.search(r"unused|garbage", m[3])):
            names.setdefault(int(m[2], 16), m[1])
    perms = {"LAND_TILE": 0x00, "WATER_TILE": 0x01, "WALL_TILE": 0x0F, "TALK": 0x10}
    table = []
    for line in (pokegold / "data/collision/collision_permissions.asm").read_text().splitlines():
        if m := re.match(r"\s*db (\w+)(?: \| (\w+))?", line):
            table.append(perms[m[1]] | (perms[m[2]] if m[2] else 0))
    if len(table) != 256:
        raise SystemExit(f"collision permissions: {len(table)} entries, expected 256")
    return names, table


def nice(name: str) -> str:
    """PLAYERS_HOUSE_2F -> Players House 2F."""
    return " ".join(w if w[:1].isdigit() else w.capitalize() for w in name.split("_") if w)


def render(pokegold: Path) -> str:
    commit = subprocess.run(["git", "-C", str(pokegold), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "unknown"
    c = pokegold / "constants"
    coll_names, coll_perms = collision(pokegold)
    tables = {
        "SYMBOLS": symbols(pokegold),
        "CONSTANTS": constants(pokegold),
        "CHARMAP": charmap(c / "charmap.asm"),
        "MAPS": {k: nice(v) for k, v in maps(c / "map_constants.asm").items()},
        "SPRITES": {k: nice(v) for k, v in consts(c / "sprite_constants.asm", "SPRITE_").items()},
        "SPECIES": {k: nice(v) for k, v in consts(c / "pokemon_constants.asm").items()},
        "MOVES": {k: nice(v) for k, v in consts(c / "move_constants.asm").items()},
        "ITEMS": {k: nice(v) for k, v in consts(c / "item_constants.asm").items()},
        "BG_EVENTS": consts(c / "script_constants.asm", "BGEVENT_"),
        "COLLISION": {k: v.lower() for k, v in coll_names.items()},
        "COLLISION_PERMISSIONS": coll_perms,
    }
    out = [f'"""Generated by ``python -m gb_agent.games.silver_gen`` from pret/pokegold {commit}.',
           "", "Don't edit by hand; regenerate.", '"""', ""]
    for name, value in tables.items():
        if isinstance(value, list):
            out.append(f"{name} = {value!r}")
            continue
        out.append(f"{name} = {{")
        for k, v in value.items():
            out.append(f"    {k!r}: 0x{v:04X}," if name == "SYMBOLS" else f"    {k!r}: {v!r},")
        out.append("}")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pokegold", type=Path)
    args = parser.parse_args()
    OUT.write_text(render(args.pokegold))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
