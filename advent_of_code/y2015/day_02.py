from advent_of_code.input import get_input

def part_1():

    puzzle_input = get_input(2015, 2)

    total_paper = 0
    for dims in puzzle_input.split('\n')[:-1]:
        l, w, h = map(int, dims.split('x'))
        s1 = l*w
        s2 = l*h
        s3 = w*h

        total_paper += 2*(s1 + s2 + s3) + min(s1,s2,s3)

    return total_paper

def part_2():
    
    puzzle_input = get_input(2015, 2)

    total_ribbon = 0
    for dims in puzzle_input.split('\n')[:-1]:
        l, w, h = sorted(map(int, dims.split('x')))

        total_ribbon += 2*(l+w) + (l*w*h)

    return total_ribbon
