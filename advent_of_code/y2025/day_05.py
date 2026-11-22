from advent_of_code.input import get_input

def part_1():

    puzzle_input = get_input(2025, 5)

    rows = puzzle_input.splitlines()

    fresh_ranges = []
    ids_to_check = []
    for row in rows:
        if '-' in row:
            low, high = map(int, row.split('-'))
            fresh_ranges.append(range(low, high+1))
        elif row.isnumeric():
            ids_to_check.append(int(row))
        else:
            continue
    
    fresh_count = 0
    for i in ids_to_check:
        for r in fresh_ranges:
            if i in r:
                fresh_count += 1
                break

    return fresh_count

def part_2():

    puzzle_input = get_input(2025, 5)

    rows = puzzle_input.splitlines()

    fresh_ranges = []
    for row in rows:
        if '-' in row:
            low, high = map(int, row.split('-'))
            fresh_ranges.append(range(low, high+1))
        else:
            continue
    
    
    sorted_ranges = sorted(fresh_ranges, key=lambda x: x.start)
    previous_stop = 0
    total_fresh = 0
    for r in sorted_ranges:
        inc = r.stop - max(r.start, previous_stop)
        if inc < 0:
            continue
        total_fresh += r.stop - max(r.start, previous_stop)
        previous_stop = r.stop

    return total_fresh