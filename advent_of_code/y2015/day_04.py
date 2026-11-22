from advent_of_code.input import get_input
from hashlib import md5

def part_1():
    
    puzzle_input = get_input(2015, 4).strip()

    attempt = 0
    while True:
        md5_hash = md5(f'{puzzle_input}{attempt}'.encode()).hexdigest()
        if md5_hash.startswith('00000'):
            return attempt

        attempt += 1

def part_2():
    
    puzzle_input = get_input(2015, 4).strip()

    attempt = 0
    while True:
        md5_hash = md5(f'{puzzle_input}{attempt}'.encode()).hexdigest()
        if md5_hash.startswith('000000'):
            return attempt

        attempt += 1