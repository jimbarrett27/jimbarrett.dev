from advent_of_code.input import get_input
import re

def part_1():
    
    puzzle_input = get_input(2024, 3)
    mult_sum = 0
    mul_statements = re.findall(r'mul\(\d+,\d+\)', puzzle_input)
    for statement in mul_statements:
        n1, n2 = map(int, statement[4:-1].split(','))
        mult_sum += n1 * n2

    return mult_sum

def part_2():
    
    puzzle_input = get_input(2024, 3)

    mult_sum = 0
    do_blocks = puzzle_input.split('do()')
    for block in do_blocks:
        enabled_block = block.split("don't()")[0]
        for mult in re.findall(r'mul\(\d+,\d+\)', enabled_block):
            n1, n2 = map(int, mult[4:-1].split(','))
            mult_sum += n1 * n2
        
    return mult_sum