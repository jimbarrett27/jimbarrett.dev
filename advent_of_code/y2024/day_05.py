from advent_of_code.input import get_input
from dataclasses import dataclass, field

def part_1():
    
    puzzle_input = get_input(2024, 5)

    @dataclass
    class Numb:
        val: int
        lts: set = field(default_factory=set)
        gts: set = field(default_factory=set)

        def __lt__(self, other):
            return other.val in self.lts
        def __gt__(self, other):
            return other.val in self.gts
        
    val_to_numb = {}

    tot = 0 
    update_phase = False
    for row in puzzle_input.splitlines():
        
        if row == '':
            update_phase = True
            continue

        if not update_phase:
            v1, v2 = map(int, row.split('|'))
            
            if v1 not in val_to_numb:
                val_to_numb[v1] = Numb(v1)
            if v2 not in val_to_numb:
                val_to_numb[v2] = Numb(v2)
            
            val_to_numb[v1].lts.add(v2)
            val_to_numb[v2].gts.add(v1)
        else:
            vals = [val_to_numb[val] for val in map(int, row.split(','))]
            sorted_vals = sorted(vals)
            
            if vals == sorted_vals:
                tot += sorted_vals[len(sorted_vals)//2].val

        
    return tot

def part_2():
    
    puzzle_input = get_input(2024, 5)

    @dataclass
    class Numb:
        val: int
        lts: set = field(default_factory=set)
        gts: set = field(default_factory=set)

        def __lt__(self, other):
            return other.val in self.lts
        def __gt__(self, other):
            return other.val in self.gts
        
    val_to_numb = {}

    tot = 0 
    update_phase = False
    for row in puzzle_input.splitlines():
        
        if row == '':
            update_phase = True
            continue

        if not update_phase:
            v1, v2 = map(int, row.split('|'))
            
            if v1 not in val_to_numb:
                val_to_numb[v1] = Numb(v1)
            if v2 not in val_to_numb:
                val_to_numb[v2] = Numb(v2)
            
            val_to_numb[v1].lts.add(v2)
            val_to_numb[v2].gts.add(v1)
        else:
            vals = [val_to_numb[val] for val in map(int, row.split(','))]
            sorted_vals = sorted(vals)
            
            if vals != sorted_vals:
                tot += sorted_vals[len(sorted_vals)//2].val

        
    return tot