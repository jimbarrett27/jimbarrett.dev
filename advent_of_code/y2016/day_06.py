from advent_of_code.input import get_input
from collections import defaultdict, Counter

def part_1():
    
    puzzle_input = get_input(2016, 6)

    columns = defaultdict(list)
    for line in puzzle_input.splitlines():
        for i, c in enumerate(line):
            columns[i].append(c)

    word = ''
    for i in range(len(columns)):
        word += Counter(columns[i]).most_common(1)[0][0]

    return word

def part_2():
    
    puzzle_input = get_input(2016, 6)

    columns = defaultdict(list)
    for line in puzzle_input.splitlines():
        for i, c in enumerate(line):
            columns[i].append(c)

    word = ''
    for i in range(len(columns)):
        word += list(Counter(columns[i]).most_common())[::-1][0][0]

    return word