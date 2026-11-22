from advent_of_code.input import get_input

def part_1():
    puzzle_input = get_input(2015, 25)

    target_y, target_x = [int(word[:-1]) for word in puzzle_input.strip().split() if word[:-1].isdigit()] 

    x = 1
    for i in range(1,target_x):
        x += (i+1)

    y = x
    for i in range(target_y-1):
        y += target_x + i


    num = 20151125
    for i in range(y-1):
        num = (num * 252533) % 33554393

    return num

def part_2():
    return "Merry Christmas!"