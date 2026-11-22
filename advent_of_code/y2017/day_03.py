PUZZLE_INPUT = 265149

def part_1():
    
    step_count = 0
    n_steps_per = 1
    step_accum = 0
    dir_ind = 0
    directions = ['r', 'u', 'l', 'd']
    
    pos = (0, 0)
    for i in range(PUZZLE_INPUT - 1):
        if step_count == n_steps_per:
            step_count = 0
            dir_ind += 1
            step_accum += 1
            if step_accum == 2:
                step_accum = 0
                n_steps_per += 1

        direction = directions[dir_ind % 4]
        
        if direction == 'r':
            pos = (pos[0] + 1, pos[1])
        elif direction == 'u':
            pos = (pos[0], pos[1]+1)
        elif direction == 'l':
            pos = (pos[0]-1, pos[1])
        else:
            pos = (pos[0], pos[1]-1)

        step_count += 1


    return sum(map(abs, pos))
        

from itertools import product

def part_2():
    
    step_count = 0
    n_steps_per = 1
    step_accum = 0
    dir_ind = 0
    directions = ['r', 'u', 'l', 'd']
    
    pos_to_value = {}
    pos = (0,0)
    pos_to_value[pos] = 1
    while pos_to_value[pos] <= PUZZLE_INPUT:
        if step_count == n_steps_per:
            step_count = 0
            dir_ind += 1
            step_accum += 1
            if step_accum == 2:
                step_accum = 0
                n_steps_per += 1

        direction = directions[dir_ind % 4]
        
        if direction == 'r':
            pos = (pos[0] + 1, pos[1])
        elif direction == 'u':
            pos = (pos[0], pos[1]+1)
        elif direction == 'l':
            pos = (pos[0]-1, pos[1])
        else:
            pos = (pos[0], pos[1]-1)

        neighbour_sum = 0
        for neighbour_vec in product([-1, 0, 1], [-1, 0, 1]):
            neighbour_pos = (pos[0] + neighbour_vec[0], pos[1] + neighbour_vec[1])

            if neighbour_pos in pos_to_value:
                neighbour_sum += pos_to_value[neighbour_pos]

        pos_to_value[pos] = neighbour_sum

        step_count += 1



    return neighbour_sum
     
