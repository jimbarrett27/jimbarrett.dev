from advent_of_code.input import get_input

def get_reduced_length(polymer: str):

    action_taken = True
    while action_taken:
        unique_components = set(polymer.lower())
        action_taken = False
        for component in unique_components:
            modified_polymer = polymer.replace(f'{component}{component.upper()}', '').replace(f'{component.upper()}{component}', '')

            if len(modified_polymer) != len(polymer):
                action_taken = True

            polymer = modified_polymer

    return len(polymer)

def part_1():

    puzzle_input = """dabAcCaCBAcCcaDA
"""
    puzzle_input = get_input(2018, 5)

    polymer = puzzle_input.splitlines()[0]

    return get_reduced_length(polymer)

def part_2():

    puzzle_input = """dabAcCaCBAcCcaDA
"""
    puzzle_input = get_input(2018, 5)

    polymer = puzzle_input.splitlines()[0]

    unique_components = set(polymer.lower())
    min_polymer_length = 100000
    for component in unique_components:
        modified_polymer = polymer.replace(component, '').replace(component.upper(), '')
        reduced_length = get_reduced_length(modified_polymer)
        if reduced_length < min_polymer_length:
            min_polymer_length = reduced_length

    return min_polymer_length