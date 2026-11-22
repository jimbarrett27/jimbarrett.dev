from advent_of_code.input import get_input
from hashlib import md5

def part_1():
    puzzle_input = get_input(2016, 5).strip()

    password = ''
    ind = 0

    while len(password) < 8:

        ind += 1
        
        inp = puzzle_input + str(ind)
        hashed = md5(inp.encode()).hexdigest()

        if hashed[:5] == '00000':
            password += hashed[5]

    return password


def part_2():
    puzzle_input = get_input(2016, 5).strip()

    password = [''] * 8
    ind = 0

    while any(p == '' for p in password):

        ind += 1
        
        inp = puzzle_input + str(ind)
        hashed = md5(inp.encode()).hexdigest()

        if hashed[:5] == '00000' and hashed[5].isdigit() and int(hashed[5]) < 8:
            if password[int(hashed[5])] == '':
                password[int(hashed[5])] = hashed[6]

    return ''.join(password)