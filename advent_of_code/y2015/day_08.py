from advent_of_code.input import get_input


hex_chars = 'abcdef0123456789'

def part_1():
    puzzle_input = get_input(2015, 8)
    total = 0
    for line in puzzle_input.splitlines():
        code_length = len(line)
        line = line[1:-1]
        line = line.replace(r'\\', '?')
        line = line.replace(r'\"', '?')

        for h1 in hex_chars:
            for h2 in hex_chars:
                line = line.replace(r'\x' + h1 + h2 , '?')
        memory_length = len(line)
        total += code_length - memory_length
        
    return total

def part_2():
    puzzle_input = get_input(2015, 8)
    total = 0
    for line in puzzle_input.splitlines():
        code_length = len(line)
        line = line.replace(r'"', '??')
        line = line.replace('\\', '??')
        line = f'"{line}"'
        
        total += len(line) - code_length
        
    return total