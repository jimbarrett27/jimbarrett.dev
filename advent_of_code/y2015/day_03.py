from advent_of_code.input import get_input

def _get_next_house(current_house: tuple[int,int], instruction: str):
    match instruction:
        case '>':
            next_house = (current_house[0]+1, current_house[1])
        case '<':
            next_house = (current_house[0]-1, current_house[1])
        case '^':
            next_house = (current_house[0], current_house[1]-1)
        case 'v':
            next_house = (current_house[0], current_house[1]+1)

    return next_house

def part_1():

    puzzle_input = get_input(2015, 3).strip()
    
    current_house = (0,0)
    visited_houses = {current_house}

    for instruction in puzzle_input:

        current_house = _get_next_house(current_house, instruction)
        visited_houses.add(current_house)

    return len(visited_houses)

def part_2():

    puzzle_input = get_input(2015,3).strip()

    santa_pos = (0,0)
    robo_pos = (0,0)
    visited_houses = {santa_pos}
    santas_turn = True
    for instruction in puzzle_input:
        if santas_turn:
            santa_pos = _get_next_house(santa_pos, instruction)
            visited_houses.add(santa_pos)
        else:
            robo_pos = _get_next_house(robo_pos, instruction)
            visited_houses.add(robo_pos)

        santas_turn = not santas_turn

    return len(visited_houses)