from advent_of_code.input import get_input

def part_1():

    puzzle_input = get_input(2025, 1)

    instructions = puzzle_input.splitlines()

    current = 50
    n_zeros = 0

    for instruction in instructions:

        direction = instruction[0]
        amount = int(instruction[1:])

        if direction == 'R':
            current = (current + amount) % 100
        else:
            current = (current - amount) % 100

        if current == 0:
            n_zeros += 1
            
    return n_zeros

def part_2():
    
    puzzle_input = get_input(2025, 1)

    instructions = puzzle_input.splitlines()

    current = 50
    n_zeros = 0

    for instruction in instructions:
        direction = instruction[0]
        amount = int(instruction[1:])

        for _ in range(amount):
            if direction == 'R':
                current += 1
            else:
                current -= 1

            current = current % 100
            if current == 0:
                n_zeros += 1

    return n_zeros 