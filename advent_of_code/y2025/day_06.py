from advent_of_code.input import get_input
from math import prod

def part_1():
    
    puzzle_input = get_input(2025, 6)

#     puzzle_input = """123 328  51 64 
#  45 64  387 23 
#   6 98  215 314
# *   +   *   +  """

    rows = puzzle_input.splitlines()

    inputs = [list() for _ in range(len(rows[0].split()))]

    for row in rows[:-1]:
        vals = row.split()
        for i, v in enumerate(vals):
            inputs[i].append(int(v))

    total = 0
    for op, inps in zip(rows[-1].split(), inputs):
        if op == '+':
            total += sum(inps)
        elif op == '*':
            total += prod(inps)

    return total

def part_2():
    
    puzzle_input = get_input(2025, 6)

#     puzzle_input = """123 328  51 64 
#  45 64  387 23 
#   6 98  215 314
# *   +   *   +  """

    rows = puzzle_input.splitlines()

    number_lengths = []
    wl = 1
    for c in rows[-1][1:]:
        if not c.isspace():
            number_lengths.append(wl-1)
            wl = 0
        wl += 1
    number_lengths.append(wl)

    number_groups = []
    for l in number_lengths:
        number_groups.append(['']* l)

    for row in rows:
        current_ind = 0
        for group_ind, l in enumerate(number_lengths):
            group = number_groups[group_ind]
            for ind in range(l):
                char = row[current_ind]
                if char.isdigit():
                    group[ind] += char
                elif not group[ind] or int(group[ind]) == 0:
                    group[ind] += '0'

                # group[ind] += char if char.isdigit() else '0'
                current_ind += 1
            current_ind += 1
    
    total = 0
    for group, operation in zip(number_groups, rows[-1].split()):
        if operation == '*':
            total += prod(map(int, group))
        elif operation == '+':
            total += sum(map(int, group))

    return total
                

        
                

