from advent_of_code.input import get_input
from collections import defaultdict
from itertools import permutations

def part_1():
    
    puzzle_input = get_input(2015, 13)

    pairing_to_score = defaultdict(lambda: 0)
    all_names = set()
    for line in puzzle_input.splitlines():
        words = line.split()
        name1 = words[0]
        name2 = words[-1].replace('.', '')
        sign = 1 if words[2] == 'gain' else -1
        score = int(words[3])

        pair = tuple(sorted([name1, name2]))
        pairing_to_score[pair] += sign * score
        all_names.add(name1)
        all_names.add(name2)

    best_score = -1
    for p in permutations(all_names):
        score = pairing_to_score[tuple(sorted([p[0], p[-1]]))]
        for pair in zip(p[:-1], p[1:]):
            score += pairing_to_score[tuple(sorted(pair))]

        if score > best_score:
            best_score = score

    return best_score

def part_2():
    
    puzzle_input = get_input(2015, 13)

    pairing_to_score = defaultdict(lambda: 0)
    all_names = set()
    for line in puzzle_input.splitlines():
        words = line.split()
        name1 = words[0]
        name2 = words[-1].replace('.', '')
        sign = 1 if words[2] == 'gain' else -1
        score = int(words[3])

        pair = tuple(sorted([name1, name2]))
        pairing_to_score[pair] += sign * score
        all_names.add(name1)
        all_names.add(name2)

    for name in all_names:
        pairing_to_score[tuple(sorted(['Jimmy', name]))] = 0
        
    all_names.add('Jimmy')

    best_score = -1
    for p in permutations(all_names):
        score = pairing_to_score[tuple(sorted([p[0], p[-1]]))]
        for pair in zip(p[:-1], p[1:]):
            score += pairing_to_score[tuple(sorted(pair))]

        if score > best_score:
            best_score = score

    return best_score