from advent_of_code.input import get_input
from collections import defaultdict

example_strings = [
    'ugknbfddgicrmopn',
    'aaa',
    'jchzalrnumimnmhp',
    'haegwjzuvuyypxyu',
    'dvszwmarrgswjxmb'
]

def part_1():

    def is_nice(s):

        VOWELS = 'aeiou'

        if any(naughty_string in s for naughty_string in ['ab', 'cd', 'pq', 'xy']):
            return False

        if sum(c in VOWELS for c in s) < 3:
            return False

        if not any(a == b for a, b in zip(s[:-1], s[1:])):
            return False
        
        return True

    puzzle_input = get_input(2015, 5)
    number_nice = 0
    for s in puzzle_input.splitlines():
        if is_nice(s.lower()):
            number_nice += 1
    
    return number_nice


def part_2():

    def is_nice(s):

        if not any(a==b for a, b in zip(s[:-2], s[2:])):
            return False

        all_pairs = list(zip(s[:-1], s[1:]))
        pair_to_indexes = defaultdict(list)
        for index, pair in enumerate(all_pairs):
            pair_to_indexes[pair].append(index)
        
        pair_repeats = []
        for pair, indexes in pair_to_indexes.items():
            if len(indexes) < 2:
                pair_repeats.append(False)
            elif len(indexes) == 2 and indexes[1] - indexes[0] == 1:
                pair_repeats.append(False)
            else:
                pair_repeats.append(True)

        if not any(pair_repeats):
            return False
        
        return True

    puzzle_input = get_input(2015, 5)
    number_nice = 0
    for s in puzzle_input.splitlines():
        if is_nice(s.lower()):
            number_nice += 1
    
    return number_nice
