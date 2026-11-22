from advent_of_code.input import get_input

def _apply_look_and_say(s):
    counts = []
    digits = []

    current_digit = s[0]
    run_length = 1
    for digit in s[1:]:
        if digit == current_digit:
            run_length += 1
        else:
            counts.append(run_length)
            digits.append(current_digit)
            run_length = 1
        current_digit = digit
    
    counts.append(run_length)
    digits.append(current_digit) 

    s = ''
    for c, d in zip(counts, digits):
        s += f'{c}{d}'

    return s

def part_1():
    
    puzzle_input = get_input(2015, 10).strip()
    current_str = puzzle_input
    for _ in range(40):
        current_str = _apply_look_and_say(current_str)

    return len(current_str)

def part_2():
    
    puzzle_input = get_input(2015, 10).strip()
    current_str = puzzle_input
    for _ in range(50):
        current_str = _apply_look_and_say(current_str)

    return len(current_str)