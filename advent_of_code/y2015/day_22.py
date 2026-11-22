from advent_of_code.input import get_input
from dataclasses import dataclass
from copy import deepcopy
@dataclass
class Spell:

    name: str
    mana_cost: int
    instant_damage: int = 0
    instant_heal: int = 0
    damage_per_turn: int = 0
    
    mana_regen_per_turn: int = 0
    armour_boost: int = 0 

    effect_length: int = 0

    # def __repr__(self):
    #     return self.name

@dataclass
class Actor:

    health: int
    damage: int
    armour: int
    mana: int

SPELLS = [
    Spell('Magic Missile', 53, instant_damage=4),
    Spell('Drain', 73, instant_damage=2, instant_heal=2),
    Spell('Shield', 113, effect_length=6, armour_boost=7),
    Spell('Poison', 173, effect_length=6, damage_per_turn=3),
    Spell('Recharge', 229, effect_length=5, mana_regen_per_turn=101)
]


lowest = 100000

def part_1():
    
    puzzle_input = get_input(2015, 22)

    boss_specs = []
    for line in puzzle_input.splitlines():
        boss_specs.append(int(line.split(':')[-1].strip()))
    boss_specs.append(0)
    boss_specs.append(0)
    boss = Actor(*boss_specs)

    player_specs = [50, 0, 0, 500]
    player = Actor(*player_specs)


    def find_win(player: Actor, boss: Actor, player_turn: bool, active_spells: list[Spell], n_turns, spell_sequence):


        new_player = deepcopy(player)
        new_boss = deepcopy(boss)

        new_active_spells = []
        new_player.armour = 0
        for spell in active_spells:
            if spell.effect_length > 0:
                new_boss.health -= spell.damage_per_turn
                new_player.mana += spell.mana_regen_per_turn
                new_player.armour += spell.armour_boost
            
            new_spell = deepcopy(spell)
            new_spell.effect_length -= 1

            if new_spell.effect_length > 0:
                new_active_spells.append(new_spell)

        if new_player.health <= 0:
            # print('player died', spell_sequence)
            return False

        if new_boss.health <= 0:
            # print('boss died!', spell_sequence)
            return [spell_sequence]
        
        if n_turns > 18:
            # print('too many turns', spell_sequence)
            return False
        
        if all(new_player.mana < spell.mana_cost for spell in SPELLS):
            # print('Player ran out of mana', spell_sequence)
            return False
        
        valid_strategies = []
        if not player_turn:

            new_player.health -= max(1, new_boss.damage - new_player.armour)

            outcome = find_win(new_player, new_boss, not player_turn, new_active_spells, n_turns+1, spell_sequence)
            if outcome is not False:
                valid_strategies += outcome
        
        else:

            for spell in SPELLS:

                new_new_player = deepcopy(new_player)
                new_new_boss = deepcopy(new_boss)
    
                if new_new_player.mana < spell.mana_cost:
                    continue

                elif any(spell.name == active_spell.name for active_spell in new_active_spells):
                    continue

                new_spell = deepcopy(spell)
                new_new_player.mana -= new_spell.mana_cost
                new_new_player.health += new_spell.instant_heal
                new_new_boss.health -= new_spell.instant_damage
                outcome = find_win(new_new_player, new_new_boss, not player_turn, new_active_spells + [new_spell] , n_turns+1, spell_sequence + [new_spell])
                if outcome is not False:
                    valid_strategies += outcome


        return valid_strategies

    

    best_strategy =  min(find_win(player, boss, True, [], 0, []), key = lambda spells: sum(spell.mana_cost for spell in spells))
    print(best_strategy)
    return sum(spell.mana_cost for spell in best_strategy)

def part_2():
    puzzle_input = get_input(2015, 22)

    boss_specs = []
    for line in puzzle_input.splitlines():
        boss_specs.append(int(line.split(':')[-1].strip()))
    boss_specs.append(0)
    boss_specs.append(0)
    boss = Actor(*boss_specs)

    player_specs = [50, 0, 0, 500]
    player = Actor(*player_specs)


    def find_win(player: Actor, boss: Actor, player_turn: bool, active_spells: list[Spell], n_turns, spell_sequence):


        new_player = deepcopy(player)
        new_boss = deepcopy(boss)

        new_active_spells = []
        new_player.armour = 0
        for spell in active_spells:
            if spell.effect_length > 0:
                new_boss.health -= spell.damage_per_turn
                new_player.mana += spell.mana_regen_per_turn
                new_player.armour += spell.armour_boost
            
            new_spell = deepcopy(spell)
            new_spell.effect_length -= 1

            if new_spell.effect_length > 0:
                new_active_spells.append(new_spell)

        if player_turn:
            new_player.health -= 1

        if new_player.health <= 0:
            # print('player died', spell_sequence)
            return False

        if new_boss.health <= 0:
            # print('boss died!', spell_sequence)
            return [spell_sequence]
        
        if n_turns > 18:
            # print('too many turns', spell_sequence)
            return False
        
        if all(new_player.mana < spell.mana_cost for spell in SPELLS):
            # print('Player ran out of mana', spell_sequence)
            return False
        
        valid_strategies = []
        if not player_turn:

            new_player.health -= max(1, new_boss.damage - new_player.armour)

            outcome = find_win(new_player, new_boss, not player_turn, new_active_spells, n_turns+1, spell_sequence)
            if outcome is not False:
                valid_strategies += outcome
        
        else:

            for spell in SPELLS:

                new_new_player = deepcopy(new_player)
                new_new_boss = deepcopy(new_boss)
    
                if new_new_player.mana < spell.mana_cost:
                    continue

                elif any(spell.name == active_spell.name for active_spell in new_active_spells):
                    continue

                new_spell = deepcopy(spell)
                new_new_player.mana -= new_spell.mana_cost
                new_new_player.health += new_spell.instant_heal
                new_new_boss.health -= new_spell.instant_damage
                outcome = find_win(new_new_player, new_new_boss, not player_turn, new_active_spells + [new_spell] , n_turns+1, spell_sequence + [new_spell])
                if outcome is not False:
                    valid_strategies += outcome


        return valid_strategies

    

    best_strategy =  min(find_win(player, boss, True, [], 0, []), key = lambda spells: sum(spell.mana_cost for spell in spells))
    return sum(spell.mana_cost for spell in best_strategy)