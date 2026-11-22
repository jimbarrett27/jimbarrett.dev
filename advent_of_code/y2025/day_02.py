from advent_of_code.input import get_input
from itertools import batched

def part_1():
    
    puzzle_input = get_input(2025, 2)

    total = 0
    ranges = puzzle_input.split(',')
    for r in ranges:
        low, high = map(int,r.split('-'))
        numbers_to_check = list(range(low, high+1))

        for n in numbers_to_check:
            sn = str(n)
            ln = len(sn)
            if len(sn) % 2 == 0 and sn[:ln//2] == sn[ln//2:]:
                total += n

    return total

def part_2():
    
    puzzle_input = get_input(2025, 2)

    total = 0
    ranges = puzzle_input.split(',')
    for r in ranges:
        low, high = map(int,r.split('-'))
        numbers_to_check = list(range(low, high+1))

        for n in numbers_to_check:
            sn = str(n)
            ln = len(sn)

            for chunk_size in range(1, (ln //2) + 1):
                if ln % chunk_size != 0:
                    continue

                subs = set(batched(sn, chunk_size))

                if len(subs) == 1:
                    total += n
                    break

    return total
                
                
