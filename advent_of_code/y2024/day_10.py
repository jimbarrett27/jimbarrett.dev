from advent_of_code.input import get_input

test_input = """89010123
78121874
87430965
96549874
45678903
32019012
01329801
10456732
"""

def part_1():
    
    puzzle_input = get_input(2024, 10)

    pos_to_val = {}
    trailheads = set()
    for i, row in enumerate(puzzle_input.splitlines()):
        for j, c in enumerate(row):
            pos_to_val[(i,j)] = int(c)
            if int(c) == 0:
                trailheads.add((i,j))

    def find_reachable_peaks(current_pos):
        
        reachable_peaks = set()
        possible_steps = [
            (current_pos[0]-1, current_pos[1]),
            (current_pos[0]+1, current_pos[1]),
            (current_pos[0], current_pos[1]-1),
            (current_pos[0], current_pos[1]+1),
        ]

        for next_pos in possible_steps:
            if next_pos not in pos_to_val:
                continue

            if pos_to_val[next_pos] - pos_to_val[current_pos] != 1:
                continue
            
            if pos_to_val[next_pos] == 9:
                reachable_peaks.add(next_pos)
            else:
                reachable_peaks = reachable_peaks | find_reachable_peaks(next_pos)

        return reachable_peaks
    
    score = 0
    for trailhead in trailheads:
        score += len(find_reachable_peaks(trailhead))

    return score

def part_2():
    
    puzzle_input = get_input(2024, 10)

    pos_to_val = {}
    trailheads = set()
    for i, row in enumerate(puzzle_input.splitlines()):
        for j, c in enumerate(row):
            pos_to_val[(i,j)] = int(c)
            if int(c) == 0:
                trailheads.add((i,j))

    def count_paths(current_pos):
        
        possible_steps = [
            (current_pos[0]-1, current_pos[1]),
            (current_pos[0]+1, current_pos[1]),
            (current_pos[0], current_pos[1]-1),
            (current_pos[0], current_pos[1]+1),
        ]

        n_paths = 0
        for next_pos in possible_steps:
            if next_pos not in pos_to_val:
                continue

            if pos_to_val[next_pos] - pos_to_val[current_pos] != 1:
                continue
            
            if pos_to_val[next_pos] == 9:
                n_paths += 1
            else:
                n_paths += count_paths(next_pos)

        return n_paths
    
    score = 0
    for trailhead in trailheads:
        score += count_paths(trailhead)

    return score