from advent_of_code.input import get_input
from dataclasses import dataclass
from itertools import combinations

@dataclass
class Item:

    name: str
    cost: int
    damage: int
    armour: int

    def __repr__(self):
        return self.name

@dataclass
class Actor:
    health: int
    damage: int
    armour: int
    


WEAPONS = [
    Item('Dagger', 8, 4, 0),
    Item('Shortsword', 10,5,0),
    Item('Warhammer', 25, 6, 0),
    Item('Longsword', 40, 7, 0),
    Item('Greataxe', 74, 8, 0)
]

ARMOUR = [
    Item('Leather', 13, 0, 1),
    Item('Chainmail', 31, 0, 2),
    Item('Splintmail', 53, 0, 3),
    Item('Bandedmail', 75, 0, 4),
    Item('Platemail', 102, 0, 5)
]

RINGS = [
    Item('dam1', 25, 1, 0),
    Item('dam2', 50, 2, 0),
    Item('dam3', 100, 3, 0),
    Item('def1', 20, 0, 1),
    Item('def2', 40, 0, 2),
    Item('def3', 80, 0, 3),
]

def get_possible_loadouts():
    possible_loadouts = []
    for weapon in WEAPONS:
        possible_loadouts.append([weapon])
        for armour in ARMOUR:
            possible_loadouts.append([weapon, armour])
            for n_rings in [1,2]:
                for ring_combo in combinations(RINGS, n_rings):
                    possible_loadouts.append([weapon] + list(ring_combo))
                    possible_loadouts.append([weapon, armour] + list(ring_combo))
    return possible_loadouts


def part_1():
    
    puzzle_input = get_input(2015, 21)

    boss_specs = []
    for line in puzzle_input.splitlines():
        boss_specs.append(int(line.split(':')[-1].strip()))

    possible_loadouts = get_possible_loadouts()

    loadouts = sorted(possible_loadouts, key=lambda items: sum(item.cost for item in items))


    for loadout in loadouts:
        player = Actor(
            100,
            sum(item.damage for item in loadout),
            sum(item.armour for item in loadout)
        )
        boss = Actor(*boss_specs)

        player_turn = True
        while player.health > 0 and boss.health > 0:

            if player_turn:
                boss.health -= max(1, player.damage - boss.armour)
                player_turn = False
            else:
                player.health -= max(1, boss.damage - player.armour)
                player_turn = True            

        if not player_turn:
            return sum(item.cost for item in loadout)
    

def part_2():
    puzzle_input = get_input(2015, 21)

    boss_specs = []
    for line in puzzle_input.splitlines():
        boss_specs.append(int(line.split(':')[-1].strip()))

    possible_loadouts = get_possible_loadouts()

    loadouts = sorted(possible_loadouts, key=lambda items: sum(item.cost for item in items), reverse=True)

    for loadout in loadouts:
        player = Actor(
            100,
            sum(item.damage for item in loadout),
            sum(item.armour for item in loadout)
        )
        boss = Actor(*boss_specs)

        player_turn = True
        while player.health > 0 and boss.health > 0:

            if player_turn:
                boss.health -= max(1, player.damage - boss.armour)
                player_turn = False
            else:
                player.health -= max(1, boss.damage - player.armour)
                player_turn = True            

        if player_turn:
            return sum(item.cost for item in loadout)
    