from advent_of_code.input import get_input
from copy import deepcopy

def part_1():
    puzzle_input = get_input(2015, 18)

    lights = [[False] * 102]
    for line in puzzle_input.splitlines():
        row = [False]
        for c in line:
            row.append(c == '#')
        row.append(False)
        lights.append(row)
    lights.append([False]*102)

    for _ in range(100):
        new_lights = deepcopy(lights)
        for x in range(1,101):
            for y in range(1, 101):

                neighbours = [
                    lights[x-1][y+1],
                    lights[x-1][y],
                    lights[x-1][y-1],
                    lights[x][y-1],
                    lights[x][y+1],
                    lights[x+1][y-1],
                    lights[x+1][y],
                    lights[x+1][y+1]
                ]

                if lights[x][y]:
                    if sum(neighbours) not in {2,3}:
                        new_lights[x][y] = False
                else:
                    if sum(neighbours) == 3:
                        new_lights[x][y] = True
        lights = new_lights

    total_on = 0
    for x in range(1,101):
        for y in range(1, 101):
            total_on += int(lights[x][y])
    
    return total_on


def part_2():
    puzzle_input = get_input(2015, 18)

    lights = [[False] * 102]
    for line in puzzle_input.splitlines():
        row = [False]
        for c in line:
            row.append(c == '#')
        row.append(False)
        lights.append(row)
    lights.append([False]*102)

    lights[1][1] = True
    lights[1][100] = True
    lights[100][1] = True
    lights[100][100] = True

    for _ in range(100):
        new_lights = deepcopy(lights)
        for x in range(1,101):
            for y in range(1, 101):

                if x in {1,100} and y in {1,100}:
                    continue 

                neighbours = [
                    lights[x-1][y+1],
                    lights[x-1][y],
                    lights[x-1][y-1],
                    lights[x][y-1],
                    lights[x][y+1],
                    lights[x+1][y-1],
                    lights[x+1][y],
                    lights[x+1][y+1]
                ]

                if lights[x][y]:
                    if sum(neighbours) not in {2,3}:
                        new_lights[x][y] = False
                else:
                    if sum(neighbours) == 3:
                        new_lights[x][y] = True
        lights = new_lights

    total_on = 0
    for x in range(1,101):
        for y in range(1, 101):
            total_on += int(lights[x][y])
    
    return total_on
