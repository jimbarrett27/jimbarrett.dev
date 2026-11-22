from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2015, 17)

    jars = sorted(map(int,puzzle_input.splitlines()), reverse=True)

    def get_valid_combinations(remaining_jars, sequence):

        target = 150 - sum(sequence)

        valid_combinations = []
        for i, jar in enumerate(remaining_jars):
            if target - jar == 0:
                valid_combinations.append(sequence + [jar])
            elif target - jar < 0:
                continue
            else:
                valid_combinations += get_valid_combinations(remaining_jars[i+1:], sequence + [jar])

        return valid_combinations

    return len(get_valid_combinations(jars, []))

def part_2():
    
    puzzle_input = get_input(2015, 17)

    jars = sorted(map(int,puzzle_input.splitlines()), reverse=True)

    def get_valid_combinations(remaining_jars, sequence):

        target = 150 - sum(sequence)

        valid_combinations = []
        for i, jar in enumerate(remaining_jars):
            if target - jar == 0:
                valid_combinations.append(sequence + [jar])
            elif target - jar < 0:
                continue
            else:
                valid_combinations += get_valid_combinations(remaining_jars[i+1:], sequence + [jar])

        return valid_combinations

    all_combinations = get_valid_combinations(jars, [])
    min_length = len(min(all_combinations, key=len))

    return sum(len(c) == min_length for c in all_combinations)