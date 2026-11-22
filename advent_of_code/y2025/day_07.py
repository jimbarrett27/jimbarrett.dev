from advent_of_code.input import get_input

def part_1():

    puzzle_input = get_input(2025, 7)

    rows = puzzle_input.splitlines()

    total_splits = 0

    active_beams = set([rows[0].index('S')])
    for row in rows[1:]:
        splitter_inds = {i for i, c in enumerate(row) if c == '^'}
        
        split_points = active_beams & splitter_inds
        total_splits += len(split_points)

        active_beams |= {s + 1 for s in split_points}
        active_beams |= {s - 1 for s in split_points}
        active_beams -= splitter_inds

    return total_splits

def part_2():

    puzzle_input = get_input(2025, 7)

    rows = puzzle_input.splitlines()

    counts = [0] * len(rows[0])
    counts[rows[0].index('S')] = 1

    for row in rows[1:]:
        splitter_inds = [i for i, c in enumerate(row) if c == '^']

        new_counts = counts.copy()
        for s in splitter_inds:
            new_counts[s-1] += counts[s]
            new_counts[s+1] += counts[s]
            new_counts[s] -= counts[s]
        
        counts = new_counts

    return sum(new_counts)



