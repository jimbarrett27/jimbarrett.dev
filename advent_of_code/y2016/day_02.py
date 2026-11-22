from advent_of_code.input import get_input

def part_1():
    puzzle_input = get_input(2016, 2)

    coord_to_number = {
        (-1,-1): 1,
        (-1, 0): 4,
        (-1,1): 7,
        (0,-1): 2,
        (0,0): 5,
        (0,1): 7,
        (1, -1): 3,
        (1, 0): 6,
        (1,1): 9
    }

    current_pos = (0,0)

    number = ''
    for instruction_row in puzzle_input.splitlines():
        moves = list(instruction_row)

        for move in moves:
            match move:
                case 'U':
                    new_pos = (current_pos[0], current_pos[1]-1)
                case 'D':
                    new_pos = (current_pos[0], current_pos[1]+1)
                case 'L':
                    new_pos = (current_pos[0]-1, current_pos[1])
                case 'R':
                    new_pos = (current_pos[0]+1, current_pos[1])

            if new_pos in coord_to_number:
                current_pos = new_pos

        number += str(coord_to_number[current_pos])

    return int(number)

def part_2():
    puzzle_input = get_input(2016, 2)

    coord_to_number = {
        (-1,-1): '2',
        (-1, 0): '6',
        (-1,1): 'A',
        (0,-1): '3',
        (0,0): '7',
        (0,1): 'B',
        (1, -1): '4',
        (1, 0): '8',
        (1,1): 'C',
        (-2, 0): '5',
        (2, 0): '9',
        (0, -2): '1',
        (0, 2): 'D'
    }

    current_pos = (0,0)

    number = ''
    for instruction_row in puzzle_input.splitlines():
        moves = list(instruction_row)

        for move in moves:
            match move:
                case 'U':
                    new_pos = (current_pos[0], current_pos[1]-1)
                case 'D':
                    new_pos = (current_pos[0], current_pos[1]+1)
                case 'L':
                    new_pos = (current_pos[0]-1, current_pos[1])
                case 'R':
                    new_pos = (current_pos[0]+1, current_pos[1])

            if new_pos in coord_to_number:
                current_pos = new_pos

        number += str(coord_to_number[current_pos])

    return number
