from advent_of_code.input import get_input

def part_1():
    puzzle_input = list(map(int,get_input(2017, 6).strip().split()))

    stringify = lambda x: ','.join(map(str,x))
    
    seen_states = set()
    seen_states.add(stringify(puzzle_input))
    iterations = 0
    while True:
        current_ind = puzzle_input.index(max(puzzle_input))
        val = puzzle_input[current_ind]
        puzzle_input[current_ind] = 0
        for i in range(val):
            current_ind = (current_ind + 1) % len(puzzle_input)
            puzzle_input[current_ind] += 1

        iterations += 1
        new_state = stringify(puzzle_input)
        if new_state in seen_states:
            break

        seen_states.add(new_state)

    return iterations

def part_2():
    puzzle_input = list(map(int,get_input(2017, 6).strip().split()))

    stringify = lambda x: ','.join(map(str,x))
    
    seen_states = dict()
    iterations = 0
    seen_states[stringify(puzzle_input)] = iterations
    while True:
        current_ind = puzzle_input.index(max(puzzle_input))
        val = puzzle_input[current_ind]
        puzzle_input[current_ind] = 0
        for i in range(val):
            current_ind = (current_ind + 1) % len(puzzle_input)
            puzzle_input[current_ind] += 1

        iterations += 1
        new_state = stringify(puzzle_input)

        if new_state in seen_states:
            break 
         
        seen_states[new_state] = iterations

    return iterations - seen_states[new_state]

   
