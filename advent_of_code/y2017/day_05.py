from advent_of_code.input import get_input

def part_1():
    puzzle_input = list(map(int, get_input(2017, 5).splitlines()[:-1]))
    
    current_pos = 0
    steps = 0
    while 0 <= current_pos < len(puzzle_input):
        jump = puzzle_input[current_pos]
        puzzle_input[current_pos] += 1
        current_pos += jump
        steps += 1

    return steps

    

def part_2():
    puzzle_input = list(map(int, get_input(2017, 5).splitlines()[:-1]))
    
    current_pos = 0
    steps = 0
    while 0 <= current_pos < len(puzzle_input):
        jump = puzzle_input[current_pos]
        
        if puzzle_input[current_pos] >= 3:
            puzzle_input[current_pos] -= 1
        else:
            puzzle_input[current_pos] += 1 
        current_pos += jump
        steps += 1

    return steps
