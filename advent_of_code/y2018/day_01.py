from advent_of_code.input import get_input


def part_1():
    
    puzzle_input = get_input(2018, 1)

    return sum(map(int,puzzle_input.splitlines()))


def part_2():

    puzzle_input = get_input(2018, 1)   

    seen_frequencies = set()
    current_freq = 0
    while True:
        for mod_str in puzzle_input.splitlines():
            mod = int(mod_str)

            current_freq += mod
            if current_freq in seen_frequencies:
                return current_freq

            seen_frequencies.add(current_freq)
    
