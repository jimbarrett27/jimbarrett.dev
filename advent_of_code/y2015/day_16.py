from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2015, 16)

    real_sue = {
        'children': 3,
        'cats': 7,
        'samoyeds': 2,
        'pomeranians': 3,
        'akitas': 0,
        'vizslas': 0,
        'goldfish': 5,
        'trees': 3,
        'cars': 2,
        'perfumes': 1
    }

    for row in puzzle_input.splitlines():
        details = ' '.join(row.split()[2:]).split(',')
        
        matching_sue = True
        for detail in details:
            key, val = detail.split(':')
            if real_sue[key.strip()] != int(val):
                matching_sue = False
                break

        if matching_sue:
            return int(row.split()[1].replace(':',''))


def part_2():
    
    puzzle_input = get_input(2015, 16)

    real_sue = {
        'children': lambda x: x==3,
        'cats': lambda x: x>7,
        'samoyeds': lambda x: x==2,
        'pomeranians': lambda x: x<3,
        'akitas': lambda x: x==0,
        'vizslas': lambda x: x==0,
        'goldfish': lambda x: x<5,
        'trees': lambda x: x>3,
        'cars': lambda x: x==2,
        'perfumes': lambda x: x==1
    }

    for row in puzzle_input.splitlines():
        details = ' '.join(row.split()[2:]).split(',')
        
        matching_sue = True
        for detail in details:
            key, val = detail.split(':')
            if not real_sue[key.strip()](int(val)):
                matching_sue = False
                break

        if matching_sue:
            return int(row.split()[1].replace(':',''))