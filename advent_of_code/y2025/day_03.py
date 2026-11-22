from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2025, 3).splitlines()

    total = 0
    for row in puzzle_input:
        d1 = max(row[:-1])
        max_ind = row.index(d1)
        d2 = max(row[max_ind+1:])
        total += int(d1+d2)

    return total



def part_2():

    puzzle_input = get_input(2025, 3).splitlines()

    comb_size = 12

    total = 0
    for row in puzzle_input:

        min_ind = 0
        max_vals = ''
        i=comb_size -1
        while i >= 0:
            subset = row[min_ind:len(row)-i]
            max_val = max(subset)
            min_ind += subset.index(max_val) +1
            max_vals += max_val
            i-=1
        total += int(max_vals)

    return total
