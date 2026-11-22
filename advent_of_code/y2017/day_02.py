from advent_of_code.input import get_input

def part_1():
    puzzle_input = get_input(2017,2).splitlines()[:-1]

    checksum = 0
    for row in map(lambda x: x.split(),puzzle_input): 
        checksum += max(map(int,row)) - min(map(int,row))

    return checksum

def part_2():
    puzzle_input = get_input(2017,2).splitlines()[:-1]

    checksum = 0
    for row in map(lambda x: x.split(),puzzle_input): 
        sorted_row = sorted(map(int, row), reverse=True)
        done = False
        for n1 in sorted_row:
            for n2 in sorted_row:
                if n2 >= n1:
                    continue

                if n1 % n2 == 0:
                    done = True
                    checksum += n1 // n2
                    break

            if done:
                break

    return checksum
