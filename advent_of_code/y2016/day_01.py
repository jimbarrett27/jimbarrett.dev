from advent_of_code.input import get_input

def part_1():
    puzzle_input = get_input(2016,1)
    instructions = [x.strip() for x in puzzle_input.split(',')]
    directions = ['N', 'E', 'S','W']
    
    current_vertical = 0
    current_horizontal = 0
    current_direction = 'N'
    for instruction in instructions:

        turn = instruction[0]
        distance = int(instruction[1:])
        
        if turn == 'R':
            current_direction = directions[(directions.index(current_direction) + 1) % 4]
        else:
            current_direction = directions[(directions.index(current_direction) - 1) % 4]

        if current_direction == 'N':
            current_vertical += distance
        elif current_direction == 'E':
            current_horizontal += distance
        elif current_direction == 'S':
            current_vertical -= distance
        elif current_direction == 'W':
            current_horizontal -= distance

    return abs(current_horizontal) + abs(current_vertical)

def part_2():
    
    puzzle_input = get_input(2016,1)
    instructions = [x.strip() for x in puzzle_input.split(',')]
    directions = ['N', 'E', 'S','W']
    
    current_vertical = 0
    current_horizontal = 0
    current_direction = 'N'

    visited_locations = set()
    for instruction in instructions:

        

        turn = instruction[0]
        distance = int(instruction[1:])
        
        if turn == 'R':
            current_direction = directions[(directions.index(current_direction) + 1) % 4]
        else:
            current_direction = directions[(directions.index(current_direction) - 1) % 4]

        for i in range(distance):

            if current_direction == 'N':
                current_vertical += 1
            elif current_direction == 'E':
                current_horizontal += 1
            elif current_direction == 'S':
                current_vertical -= 1
            elif current_direction == 'W':
                current_horizontal -= 1

            if (current_vertical, current_horizontal) in visited_locations:
                return abs(current_horizontal) + abs(current_vertical)
            else: 
                visited_locations.add((current_vertical, current_horizontal))
    

    return abs(current_horizontal) + abs(current_vertical)