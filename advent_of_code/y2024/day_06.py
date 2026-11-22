from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2024, 6)

    pos_to_terrain = {}
    height = len(puzzle_input.splitlines())
    width = len(puzzle_input.splitlines()[0])
    for i, row in enumerate(puzzle_input.splitlines()):
        for j, terr in enumerate(row):

            if terr == '^':
                pos_to_terrain[(i,j)] = '.'
                current_pos = (i,j)
                visited_places={current_pos}

            pos_to_terrain[(i,j)] = terr

    current_vec = (-1, 0)
    while True:
        target_vec = (current_pos[0] + current_vec[0], current_pos[1] + current_vec[1])  
        if target_vec not in pos_to_terrain:
            break
        elif pos_to_terrain[target_vec] == '#':
            if current_vec == (-1, 0):
                current_vec = (0, 1)
            elif  current_vec == (0, 1):
                current_vec = (1, 0)
            elif  current_vec == (1, 0):
                current_vec = (0, -1)
            elif  current_vec == (0, -1):
                current_vec = (-1, 0)
        else:
            current_pos = target_vec
            visited_places.add(current_pos)    
        

    return len(visited_places)

def part_2():
    
    puzzle_input = get_input(2024, 6)

    initial_pos_to_terrain = {}
    for i, row in enumerate(puzzle_input.splitlines()):
        for j, terr in enumerate(row):

            if terr == '^':
                initial_pos_to_terrain[(i,j)] = '.'
                current_pos = (i,j)

            initial_pos_to_terrain[(i,j)] = terr

    current_vec = (-1, 0)

    initial_pos = current_pos
    initial_pos_vec = (current_pos, current_vec)
    loops = 0
    # TODO: should only search positions visited by canonical path?
    for pos in initial_pos_to_terrain:

        if initial_pos_to_terrain[pos] == '#' or pos == initial_pos:
            continue
        else:
            pos_to_terrain = dict(initial_pos_to_terrain)
            pos_to_terrain[pos] = '#'

        current_pos = initial_pos
        current_vec = (-1, 0)
        visited_combos = {initial_pos_vec}
        while True:

            target_vec = (current_pos[0] + current_vec[0], current_pos[1] + current_vec[1])  
            if target_vec not in pos_to_terrain:
                break
            elif pos_to_terrain[target_vec] == '#':
                if current_vec == (-1, 0):
                    current_vec = (0, 1)
                elif  current_vec == (0, 1):
                    current_vec = (1, 0)
                elif  current_vec == (1, 0):
                    current_vec = (0, -1)
                elif  current_vec == (0, -1):
                    current_vec = (-1, 0)
            else:
                current_pos = target_vec
                
            if (current_pos, current_vec) in visited_combos:
                loops += 1
                break
            else:
                visited_combos.add((current_pos, current_vec))
    return loops