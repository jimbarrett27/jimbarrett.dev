from advent_of_code.input import get_input

test_input = """7 6 4 2 1
1 2 7 8 9
9 7 6 2 1
1 3 2 4 5
8 6 4 4 1
1 3 6 7 9
"""

def part_1():
    
    puzzle_input = get_input(2024, 2)

    # puzzle_input = test_input

    n_safe = 0
    for row in puzzle_input.splitlines():
        numbers = list(map(int, row.split()))

        increasing = numbers[0] < numbers[1] 

        for x1, x2 in zip(numbers[:-1], numbers[1:]):
            if increasing and x1 > x2:
                break
            if not increasing and x2 > x1:
                break
            if abs(x2 - x1) > 3 or abs(x2 - x1) == 0:
                break
        else:
            n_safe += 1
    return n_safe 
        

def part_2():
    puzzle_input = get_input(2024, 2)

    # puzzle_input = test_input

    def _is_safe(sequence):
        increasing = sequence[0] < sequence[1] 
        for x1, x2 in zip(sequence[:-1], sequence[1:]):
            if increasing and x1 > x2:
                break
            if not increasing and x2 > x1:
                break
            if abs(x2 - x1) > 3 or abs(x2 - x1) == 0:
                break
        else:
            return True
        
        return False
        

    n_safe = 0
    for row in puzzle_input.splitlines():
        numbers = list(map(int, row.split()))

        if _is_safe(numbers):
            n_safe += 1
            continue

        for i in range(len(numbers)):
            mod_seq = numbers[:i] + numbers[i+1:]        
            if _is_safe(mod_seq):
                n_safe += 1
                break
        
        
    return n_safe 