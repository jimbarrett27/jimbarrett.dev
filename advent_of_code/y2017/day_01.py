from advent_of_code.input import get_input

def part_1():
    puzzle_input = get_input(2017,1).strip()
    total = 0
    for i in range(len(puzzle_input)):
        if puzzle_input[i-1] == puzzle_input[i]:
            total += int(puzzle_input[i-1])

    return total

def part_2():
    puzzle_input = get_input(2017,1).strip()
    total = 0
    half_input_length = len(puzzle_input)//2
    for i in range(len(puzzle_input)):
        if puzzle_input[i-half_input_length] == puzzle_input[i]:
            total += int(puzzle_input[i-half_input_length])

    return total
