"""What the agent is told about Pokemon Silver after each step.

``observe`` reads a running game into a plain dict (kept in ``steps.jsonl``);
``describe`` turns two of them, before and after a step, into the text block at
the top of the agent's report. Addresses and names come from ``silver_data``,
generated from the pret/pokegold disassembly (see ``silver_gen``).

The rule for what goes in: what a human player can see on screen or would
remember, never what they couldn't know. So the map and the people on it, yes;
hidden items, enemy stats and story flags, no. And facts, not advice: "you didn't
move, there's a wall above you", never "try going left".

Map events (exits, signs) and collision are read from the ROM through pointers
the game keeps in RAM, exactly as the game does when the player moves.
"""

from pyboy import PyBoy

from gb_agent.games.silver_data import (
    BG_EVENTS, CHARMAP, COLLISION, COLLISION_PERMISSIONS, CONSTANTS, ITEMS, MAPS, MOVES,
    SPECIES, SPRITES, SYMBOLS as S,
)

DIRECTIONS = {0: "down", 4: "up", 8: "left", 12: "right"}
STEP = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OBJECT_LENGTH = S["wObject1Struct"] - S["wPlayerStruct"]
PARTYMON_LENGTH = S["wPartyMon2"] - S["wPartyMon1"]
MAP_BORDER = 3  # blocks of border around the map in wOverworldMapBlocks
COORD_OFFSET = 4  # object coordinates are stored plus 4
WALL, WATER = 0x0F, 0x01
GRASS = {"tall_grass", "long_grass"}
LEDGES = {"hop_down": "v", "hop_down_left": "v", "hop_down_right": "v",
          "hop_left": "<", "hop_right": ">"}
# Things the player can read or check, named by the tile they stand on
THINGS = {"bookshelf", "pc", "radio", "town_map", "mart_shelf", "tv", "window",
          "incense_burner"}
STATUS = [(0b111, "asleep"), (1 << 3, "poisoned"), (1 << 4, "burned"), (1 << 5, "frozen"),
          (1 << 6, "paralysed")]

STATE_HELP = """\
Each report starts with the game's state, read from memory: where you are, what's \
on screen, the people and exits around you, and your Pokemon. Coordinates are \
(x, y) tiles on the current map: x counts right from 0, y counts down from 0, so \
"up" is y - 1. The "Map around you" grid is the area on screen, one character per \
tile:
  @ you    N a person    D an exit (door, stairs, warp)    S something to read or check
  . walkable    g tall grass (wild Pokemon)    ~ water    # blocked
  v < > a ledge: you can only jump down it in that direction    (blank) off the map
Exits list where they lead. "Changes" at the top says what this step did."""


# -- reading -----------------------------------------------------------------

def _u8(pb: PyBoy, name: str, offset: int = 0) -> int:
    return pb.memory[S[name] + offset]


def _le16(pb: PyBoy, addr: int) -> int:
    return pb.memory[addr] | pb.memory[addr + 1] << 8


def _be16(pb: PyBoy, addr: int) -> int:
    return pb.memory[addr] << 8 | pb.memory[addr + 1]


def _rom(pb: PyBoy, bank: int, addr: int) -> int:
    return pb.memory[bank, addr] if addr >= 0x4000 else pb.memory[addr]


def map_name(group: int, number: int) -> str:
    return MAPS.get((group, number), f"map {group}-{number}")


def _collision(pb: PyBoy, x: int, y: int) -> int:
    """The collision type of tile (x, y), as the game's GetCoordTileCollision works it out."""
    width = _u8(pb, "wMapWidth") + 2 * MAP_BORDER
    d, e = x + COORD_OFFSET, y + COORD_OFFSET
    block = pb.memory[S["wOverworldMapBlocks"] + 1 + width + (e >> 1) * width + (d >> 1)]
    addr = _le16(pb, S["wTilesetCollisionAddress"]) + block * 4 + (d & 1) + 2 * (e & 1)
    return _rom(pb, _u8(pb, "wTilesetCollisionBank"), addr)


def _boxes(pb: PyBoy) -> list[list[str]]:
    """The text inside every box (┌…┐ over └…┘) on screen, line by line."""
    tiles = [[pb.memory[S["wTilemap"] + row * 20 + col] for col in range(20)] for row in range(18)]
    char = lambda b: CHARMAP.get(b, " ")  # noqa: E731
    boxes = []
    for top in range(18):
        for left in range(20):
            if char(tiles[top][left]) != "┌":
                continue
            right = next((c for c in range(left + 1, 20) if char(tiles[top][c]) == "┐"), None)
            bottom = next((r for r in range(top + 1, 18) if char(tiles[r][left]) == "└"), None)
            if right is None or bottom is None:
                continue
            lines = ["".join(char(tiles[r][c]) for c in range(left + 1, right)).strip()
                     for r in range(top + 1, bottom)]
            if lines := [line for line in lines if line]:
                boxes.append(lines)
    return boxes


def _people(pb: PyBoy) -> list[dict]:
    people = []
    for i in range(CONSTANTS["NUM_OBJECT_STRUCTS"] - 1):
        base = i * OBJECT_LENGTH
        sprite = _u8(pb, "wObject1Sprite", base)
        if sprite:
            people.append({"name": SPRITES.get(sprite, f"sprite {sprite}"),
                           "x": _u8(pb, "wObject1MapX", base) - COORD_OFFSET,
                           "y": _u8(pb, "wObject1MapY", base) - COORD_OFFSET})
    return people


def _events(pb: PyBoy) -> tuple[list[dict], list[dict]]:
    """The current map's exits and readable things, from its event data in ROM."""
    bank = _u8(pb, "wMapScriptsBank")
    exits = []
    pointer = _le16(pb, S["wCurMapWarpEventsPointer"])
    for i in range(_u8(pb, "wCurMapWarpEventCount")):
        y, x, _, group, number = (_rom(pb, bank, pointer + i * 5 + k) for k in range(5))
        exits.append({"x": x, "y": y, "to": map_name(group, number)})
    things = []
    pointer = _le16(pb, S["wCurMapBGEventsPointer"])
    for i in range(_u8(pb, "wCurMapBGEventCount")):
        y, x, kind = (_rom(pb, bank, pointer + i * 5 + k) for k in range(3))
        if BG_EVENTS.get(kind) == "ITEM":
            continue  # a hidden item: not something a player can see
        tile = COLLISION.get(_collision(pb, x, y))
        things.append({"x": x, "y": y,
                       "what": tile.replace("_", " ") if tile in THINGS else "something"})
    return exits, things


def _tile(collision: int) -> tuple[str, str]:
    """A collision type as a grid character and a name."""
    name = COLLISION.get(collision, "")
    permission = COLLISION_PERMISSIONS[collision] & 0x0F
    char = LEDGES.get(name) or ("g" if name in GRASS else "~" if permission == WATER
                                else "#" if permission == WALL else ".")
    return char, name.replace("_", " ") or {"~": "water", "#": "wall"}.get(char, "floor")


def _grid(pb: PyBoy, x: int, y: int, people: list[dict], exits: list[dict],
          things: list[dict]) -> dict:
    """The tiles on screen: 10 across, 9 down, with the player 4 from the top left."""
    width, height = _u8(pb, "wMapWidth") * 2, _u8(pb, "wMapHeight") * 2
    marks = {**{(t["x"], t["y"]): "S" for t in things},
             **{(e["x"], e["y"]): "D" for e in exits},
             **{(p["x"], p["y"]): "N" for p in people}, (x, y): "@"}
    left, top = x - 4, y - 4
    rows = []
    for ty in range(top, top + 9):
        row = ""
        for tx in range(left, left + 10):
            if (tx, ty) in marks:
                row += marks[(tx, ty)]
            elif not (0 <= tx < width and 0 <= ty < height):
                row += " "
            else:
                row += _tile(_collision(pb, tx, ty))[0]
        rows.append(row)
    return {"left": left, "top": top, "rows": rows}


def _map_loaded(pb: PyBoy, x: int, y: int, exits: list[dict]) -> bool:
    """Whether the map buffer holds this map. It shares memory with a decompression
    buffer, so as a battle starts it can briefly hold graphics instead. The game
    keeps the collision of the four tiles around the player, and if none of them
    agree with the buffer, the buffer is wrong. (Just after a warp those four are
    still the old map's, so on an exit tile the buffer gets the benefit of the doubt.)
    """
    if any((e["x"], e["y"]) == (x, y) for e in exits):
        return True
    width, height = _u8(pb, "wMapWidth") * 2, _u8(pb, "wMapHeight") * 2
    compared = [(_collision(pb, x + dx, y + dy), _u8(pb, f"wTile{d.title()}"))
                for d, (dx, dy) in STEP.items() if 0 <= x + dx < width and 0 <= y + dy < height]
    return not compared or any(ours == theirs for ours, theirs in compared)


def _adjacent(pb: PyBoy, x: int, y: int, people: list[dict], exits: list[dict],
              things: list[dict]) -> dict:
    out = {}
    for direction, (dx, dy) in STEP.items():
        at = lambda items: [i for i in items if (i["x"], i["y"]) == (x + dx, y + dy)]  # noqa: E731
        if person := at(people):
            out[direction] = person[0]["name"]
        elif exit_ := at(exits):
            out[direction] = f"exit to {exit_[0]['to']}"
        elif thing := at(things):
            what = thing[0]["what"]
            out[direction] = what if what != "something" else "something to read or check"
        else:
            out[direction] = _tile(_collision(pb, x + dx, y + dy))[1]
    return out


def _status(byte: int) -> str:
    return next((name for mask, name in STATUS if byte & mask), "")


def _party(pb: PyBoy) -> list[dict]:
    party = []
    for i in range(min(_u8(pb, "wPartyCount"), CONSTANTS["PARTY_LENGTH"])):
        base = S["wPartyMon1"] + i * PARTYMON_LENGTH
        field = lambda name: base + S[name] - S["wPartyMon1"]  # noqa: E731
        moves = []
        for k in range(CONSTANTS["NUM_MOVES"]):
            move = pb.memory[field("wPartyMon1Moves") + k]
            if move:
                moves.append({"name": MOVES.get(move, f"move {move}"),
                              "pp": pb.memory[field("wPartyMon1PP") + k] & 0x3F})
        party.append({"species": SPECIES.get(pb.memory[base], f"species {pb.memory[base]}"),
                      "level": pb.memory[field("wPartyMon1Level")],
                      "hp": _be16(pb, field("wPartyMon1HP")),
                      "max_hp": _be16(pb, field("wPartyMon1MaxHP")),
                      "status": _status(pb.memory[field("wPartyMon1Status")]),
                      "moves": moves})
    return party


def _bag(pb: PyBoy) -> list[dict]:
    bag = []
    for count, items in (("wNumItems", "wItems"), ("wNumBalls", "wBalls")):
        for i in range(min(_u8(pb, count), 20)):
            item = pb.memory[S[items] + 2 * i]
            bag.append({"name": ITEMS.get(item, f"item {item}"),
                        "count": pb.memory[S[items] + 2 * i + 1]})
    for i in range(min(_u8(pb, "wNumKeyItems"), 25)):
        item = pb.memory[S["wKeyItems"] + i]
        bag.append({"name": ITEMS.get(item, f"item {item}"), "count": 1})
    return bag


def _battle(pb: PyBoy) -> dict | None:
    mode = _u8(pb, "wBattleMode")
    if not mode:
        return None
    enemy_max = _be16(pb, S["wEnemyMonMaxHP"])
    return {"kind": "wild" if mode == 1 else "trainer",
            "you": {"species": SPECIES.get(_u8(pb, "wBattleMonSpecies"), "?"),
                    "level": _u8(pb, "wBattleMonLevel"),
                    "hp": _be16(pb, S["wBattleMonHP"]), "max_hp": _be16(pb, S["wBattleMonMaxHP"])},
            "enemy": {"species": SPECIES.get(_u8(pb, "wEnemyMonSpecies"), "?"),
                      "level": _u8(pb, "wEnemyMonLevel"),
                      "hp_percent": round(100 * _be16(pb, S["wEnemyMonHP"]) / enemy_max)
                      if enemy_max else 0}}


def observe(pb: PyBoy) -> dict:
    """The game as a player would describe it, as plain JSON-able data."""
    group, number = _u8(pb, "wMapGroup"), _u8(pb, "wMapNumber")
    # The player object moves at the start of a step; wX/YCoord only once it's done,
    # so a report that lands mid-step would otherwise show the old tile.
    x, y = _u8(pb, "wPlayerMapX") - COORD_OFFSET, _u8(pb, "wPlayerMapY") - COORD_OFFSET
    battle = _battle(pb)
    obs = {
        "map": {"group": group, "number": number, "name": map_name(group, number),
                "width": _u8(pb, "wMapWidth") * 2, "height": _u8(pb, "wMapHeight") * 2},
        "player": {"x": x, "y": y,
                   "facing": DIRECTIONS.get(_u8(pb, "wPlayerDirection") & 0x0C, "down"),
                   "walking": (x, y) != (_u8(pb, "wXCoord"), _u8(pb, "wYCoord"))},
        "script_running": bool(_u8(pb, "wScriptRunning")),
        "text": _boxes(pb),
        "battle": battle,
        "party": _party(pb),
        "bag": _bag(pb),
        "money": int.from_bytes(bytes(pb.memory[S["wMoney"] + i] for i in range(3)), "big"),
        "badges": bin(_u8(pb, "wJohtoBadges")).count("1"),
    }
    if battle is None:  # in battle the map buffers hold battle graphics, not the map
        people = _people(pb)
        exits, things = _events(pb)
        loaded = _map_loaded(pb, x, y, exits)
        obs.update(people=people, exits=exits, things=things if loaded else [],
                   adjacent=_adjacent(pb, x, y, people, exits, things) if loaded else None,
                   grid=_grid(pb, x, y, people, exits, things) if loaded else None)
    return obs


# -- describing ----------------------------------------------------------------

def _where(dx: int, dy: int) -> str:
    """How to get somewhere from the player, e.g. "(from you: 5 up, 4 right)"."""
    parts = [f"{abs(dy)} {'down' if dy > 0 else 'up'}" if dy else "",
             f"{abs(dx)} {'right' if dx > 0 else 'left'}" if dx else ""]
    steps = ", ".join(p for p in parts if p)
    return f"(from you: {steps})" if steps else "(where you are)"


def _mon(m: dict) -> str:
    status = f", {m['status']}" if m.get("status") else ""
    moves = ", ".join(f"{mv['name']} {mv['pp']}pp" for mv in m["moves"])
    return f"{m['species']} L{m['level']} HP {m['hp']}/{m['max_hp']}{status} ({moves})"


def _changes(before: dict, after: dict, pressed: list[str]) -> list[str]:
    lines = []
    b, a = before["player"], after["player"]
    if before["map"]["name"] != after["map"]["name"]:
        lines.append(f"map changed: {before['map']['name']} -> {after['map']['name']}")
    elif (b["x"], b["y"]) != (a["x"], a["y"]):
        lines.append(f"moved: ({b['x']}, {b['y']}) -> ({a['x']}, {a['y']})")
    elif b["facing"] != a["facing"]:
        lines.append(f"turned to face {a['facing']}, without moving")
    elif after["battle"] is None and (dirs := [p for p in pressed if p in STEP]):
        ahead = (after.get("adjacent") or {}).get(a["facing"], "unknown")
        lines.append(f"didn't move (pressed {', '.join(dict.fromkeys(dirs))}); "
                     f"facing {a['facing']}, toward: {ahead}")
    if before["battle"] is None and after["battle"] is not None:
        e = after["battle"]["enemy"]
        lines.append(f"battle started ({after['battle']['kind']}): {e['species']} L{e['level']}")
    elif before["battle"] is not None and after["battle"] is None:
        lines.append("battle ended")
    if after["text"] != before["text"]:
        lines.append("new text on screen" if after["text"] else "text closed")
    elif after["text"]:
        lines.append("same text still on screen")
    hp_before = {i: m for i, m in enumerate(before["party"])}
    for i, m in enumerate(after["party"]):
        old = hp_before.get(i)
        if old is None or old["species"] != m["species"]:
            lines.append(f"new in party: {m['species']} L{m['level']}")
        else:
            if old["level"] != m["level"]:
                lines.append(f"{m['species']} grew to L{m['level']}")
            if old["hp"] != m["hp"]:
                lines.append(f"{m['species']} HP {old['hp']} -> {m['hp']}")
    bag_before = {i["name"]: i["count"] for i in before["bag"]}
    bag_after = {i["name"]: i["count"] for i in after["bag"]}
    for name in dict.fromkeys([*bag_before, *bag_after]):
        delta = bag_after.get(name, 0) - bag_before.get(name, 0)
        if delta:
            lines.append(f"bag: {name} {'+' if delta > 0 else ''}{delta}")
    if before["money"] != after["money"]:
        lines.append(f"money: ${before['money']} -> ${after['money']}")
    if before["badges"] != after["badges"]:
        lines.append(f"badges: {before['badges']} -> {after['badges']}")
    return lines


def describe(before: dict | None, after: dict, pressed: list[str] = ()) -> str:
    """The state block for a report: what changed (if ``before``), then the state now."""
    p, m = after["player"], after["map"]
    lines = []
    if before is not None:
        changes = _changes(before, after, list(pressed))
        lines.append("Changes: " + ("; ".join(changes) if changes else "none"))
    lines.append(f"Where: {m['name']} ({m['width']}x{m['height']} tiles), you're at "
                 f"({p['x']}, {p['y']}) facing {p['facing']}"
                 + (" (mid-step)" if p["walking"] else ""))
    mode = "battle" if after["battle"] else "overworld"
    if after["script_running"] and not after["battle"]:
        mode += "; a script is running (a cutscene or conversation has control)"
    lines.append(f"Mode: {mode}")
    for box in after["text"]:
        lines.append("Text on screen: " + " / ".join(box))
    if battle := after["battle"]:
        you, enemy = battle["you"], battle["enemy"]
        lines.append(f"Battle ({battle['kind']}): your {you['species']} L{you['level']} "
                     f"HP {you['hp']}/{you['max_hp']} vs {enemy['species']} L{enemy['level']} "
                     f"HP {enemy['hp_percent']}%")
    else:
        rel = lambda t: _where(t["x"] - p["x"], t["y"] - p["y"])  # noqa: E731
        if after["people"]:
            lines.append("People: " + "; ".join(
                f"{q['name']} at ({q['x']}, {q['y']}) {rel(q)}" for q in after["people"]))
        if after["exits"]:
            lines.append("Exits: " + "; ".join(
                f"to {e['to']} at ({e['x']}, {e['y']}) {rel(e)}" for e in after["exits"]))
        grid = after["grid"]
        on_screen = [t for t in after["things"]
                     if 0 <= t["x"] - grid["left"] < 10 and 0 <= t["y"] - grid["top"] < 9
                     ] if grid else []
        if on_screen:
            kinds: dict[str, list[str]] = {}
            for t in on_screen:
                kinds.setdefault(t["what"], []).append(f"({t['x']}, {t['y']})")
            lines.append("To read or check on screen: " + "; ".join(
                f"{what} {', '.join(spots)}" for what, spots in kinds.items()))
        if after["adjacent"] is None:
            lines.append("Map around you: not readable right now (the screen is changing)")
        else:
            lines.append("Next to you: " + ", ".join(f"{d} {what}"
                                                      for d, what in after["adjacent"].items()))
            lines.append(f"Map around you (top left is ({grid['left']}, {grid['top']})):")
            rows = [row.rstrip() for row in grid["rows"]]
            while rows and not rows[-1]:  # off the bottom of the map; nothing to see
                rows.pop()
            lines += [f"  {row}" for row in rows]
    if after["party"]:
        lines.append("Party: " + "; ".join(_mon(mon) for mon in after["party"]))
    bag = ", ".join(f"{i['name']} x{i['count']}" for i in after["bag"]) or "empty"
    lines.append(f"Bag: {bag} | Money: ${after['money']} | Badges: {after['badges']}")
    return "\n".join(lines)
