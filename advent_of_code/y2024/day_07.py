from advent_of_code.input import get_input
from itertools import combinations_with_replacement, permutations

test_input = """190: 10 19
3267: 81 40 27
83: 17 5
156: 15 6
7290: 6 8 6 15
161011: 16 10 13
192: 17 8 14
21037: 9 7 18 13
292: 11 6 16 20
"""

def part_1():
    
    puzzle_input = get_input(2024, 7)

    total = 0
    for row in puzzle_input.splitlines():
        target, others = row.split(':')
        target = int(target)
        others = list(map(int, others.split()))

        possible_operations = [['*'], ['+']]
        for _ in range(len(others) - 2):
            next_ops = []
            for ops in possible_operations:
                for op in ['*', '+']:
                    next_ops.append(ops + [op])
            possible_operations = next_ops

        for operations in possible_operations:
            running_tot = others[0]
            for number, operation in zip(others[1:], operations):
                if operation == '*':
                    running_tot *= number
                elif operation == '+':
                    running_tot += number
                
                if running_tot > target:
                    break

            if running_tot == target:
                total += target
                break
    
    return total

def part_2():
    
    puzzle_input = get_input(2024, 7)

    total = 0
    for row in puzzle_input.splitlines():
        target, others = row.split(':')
        target = int(target)
        others = list(map(int, others.split()))

        possible_operations = [['*'], ['+'], ['||']]
        for _ in range(len(others) - 2):
            next_ops = []
            for ops in possible_operations:
                for op in ['*', '+', '||']:
                    next_ops.append(ops + [op])
            possible_operations = next_ops

        for operations in possible_operations:
            running_tot = others[0]
            for number, operation in zip(others[1:], operations):
                if operation == '*':
                    running_tot *= number
                elif operation == '+':
                    running_tot += number
                elif operation == '||':
                    running_tot = int(str(running_tot) + str(number))

                if running_tot > target:
                    break

            if running_tot == target:
                total += target
                break
    
    return total