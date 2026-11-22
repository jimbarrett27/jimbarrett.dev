from advent_of_code.input import get_input
from collections import Counter

def part_1():
    
    puzzle_input = get_input(2024, 1)

    n1s = []
    n2s = []
    for row in puzzle_input.splitlines():
        n1, n2 = map(int, row.split())
        n1s.append(n1)
        n2s.append(n2)
    
    diff_sum = 0
    for n1, n2 in zip(sorted(n1s), sorted(n2s)):
        diff_sum += abs(n1-n2)

    return diff_sum

def part_2():
    
    puzzle_input = get_input(2024, 1)

    n1s = []
    n2s = []
    for row in puzzle_input.splitlines():
        n1, n2 = map(int, row.split())
        n1s.append(n1)
        n2s.append(n2)

    n2_counts = Counter(n2s)

    similarity_sum = 0
    for n in n1s:
        similarity_sum += n*n2_counts[n]

    return similarity_sum