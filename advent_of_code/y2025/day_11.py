from advent_of_code.input import get_input
from collections import defaultdict

def part_1():
    puzzle_input = """aaa: you hhh
you: bbb ccc
bbb: ddd eee
ccc: ddd eee fff
ddd: ggg
eee: out
fff: out
ggg: out
hhh: ccc fff iii
iii: out""" 

    puzzle_input = get_input(2025, 11)

    input_to_output = defaultdict(list)
    for row in puzzle_input.splitlines():
        ins, outs = row.split(':')
        input_to_output[ins] += outs.strip().split()

    next_keys = ['you']
    n_outs = 0
    while len(next_keys) > 0:
        next_ones = sum([input_to_output[k] for k in next_keys], start=[])
        n_outs += sum(1 for x in next_ones if x == 'out')
        next_keys = [k for k in next_ones if k != 'out']

    return n_outs    


def part_2():
    
    puzzle_input = """svr: aaa bbb
aaa: fft
fft: ccc
bbb: tty
tty: ccc
ccc: ddd eee
ddd: hub
hub: fff
eee: dac
dac: fff
fff: ggg hhh
ggg: out
hhh: out"""

    puzzle_input = get_input(2025, 11)

    input_to_output = defaultdict(list)
    for row in puzzle_input.splitlines():
        ins, outs = row.split(':')
        input_to_output[ins] += outs.strip().split()

    the_cache = {}
    
    def recurse(seen_fft, seen_dac, loc):
        print(loc == 'out')

        cache_key = (seen_fft, seen_dac, loc)
        if cache_key in the_cache:
            return the_cache[cache_key]

        if loc == 'out':
            print('caching_something')
            if seen_fft and seen_dac:
                the_cache[cache_key] = 1
                return 1
            else:
                the_cache[cache_key] = 0
                return 0

        next_locs = input_to_output[loc]

        total = 0

        
        for next_loc in next_locs:
            
            seen_fft = seen_fft or (next_loc == 'fft')
            seen_dac = seen_dac or (next_loc == 'dac')

            total += recurse(seen_fft, seen_dac, next_loc)

        return total

    return recurse(False, False, 'svr')