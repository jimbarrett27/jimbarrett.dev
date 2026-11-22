from advent_of_code.input import get_input

def part_1():

    puzzle_input = get_input(2015, 1).strip()

    current_floor = 0
    for c in puzzle_input:
        match c:
            case '(':
                current_floor += 1
            case ')':
                current_floor -= 1
            case _:
                raise ValueError('Unexpected char')

    return current_floor

def part_2():
    puzzle_input = get_input(2015, 1).strip()

    current_floor = 0
    for i, c in enumerate(puzzle_input):
        match c:
            case '(':
                current_floor += 1
            case ')':
                current_floor -= 1
            case _:
                raise ValueError('Unexpected char')

        if current_floor < 0:
            return i + 1
