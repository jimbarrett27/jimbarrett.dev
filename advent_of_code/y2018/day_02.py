from advent_of_code.input import get_input
from collections import Counter

def part_1():

    puzzle_input = get_input(2018, 2)

    totals = Counter()
    for cs in puzzle_input.splitlines():
        counts = Counter(cs)

        rev = {c: v for v, c in counts.items()}

        for count in rev.keys():
            totals[count] += 1

    ans = totals[2] * totals[3]

    print(totals)

    return ans

def part_2():

    puzzle_input = get_input(2018, 2)

    min_diff = 999
    best_matching = ''
    for i, s1 in enumerate(puzzle_input.splitlines()):
        for j, s2 in enumerate(puzzle_input.splitlines()):

            if j >= i:
                continue

            diff = 0
            matching = ''
            for c1, c2 in zip(s1, s2, strict=True):
                if c1 != c2:
                    diff += 1
                else:
                    matching += c1

            if diff < min_diff:

                best_matching = matching
                min_diff = diff

    return best_matching