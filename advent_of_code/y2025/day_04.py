from advent_of_code.input import get_input

def part_1():

    puzzle_input = get_input(2025, 4)

    rows = puzzle_input.splitlines()

    roll_coords = set()
    for i in range(len(rows)):
        for j, letter in enumerate(rows[i]):
            if letter == '@':
                roll_coords.add((i,j))
    
    transforms = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    total_accessible = 0
    for coord in roll_coords:
        n_rolls = 0
        for transform in transforms:
            if (coord[0] + transform[0], coord[1] + transform[1]) in roll_coords:
                n_rolls += 1
        
        if n_rolls < 4:
            total_accessible += 1

    return total_accessible


def part_2():

    puzzle_input = get_input(2025, 4)

    rows = puzzle_input.splitlines()

    roll_coords = set()
    for i in range(len(rows)):
        for j, letter in enumerate(rows[i]):
            if letter == '@':
                roll_coords.add((i,j))
    
    transforms = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    rolls_removed = True
    total_accessible = 0
    while rolls_removed:
        rolls_removed = False

        rolls_at_start = list(roll_coords)

        
        for coord in rolls_at_start:
            n_rolls = 0
            for transform in transforms:
                if (coord[0] + transform[0], coord[1] + transform[1]) in roll_coords:
                    n_rolls += 1
            
            if n_rolls < 4:
                total_accessible += 1
                roll_coords.remove(coord)
                rolls_removed = True

    return total_accessible