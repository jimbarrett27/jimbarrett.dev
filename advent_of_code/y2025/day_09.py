from advent_of_code.input import get_input
from itertools import combinations

def part_1():
    
    puzzle_input = get_input(2025, 9)

#     puzzle_input = """7,1
# 11,1
# 11,7
# 9,7
# 9,5
# 2,5
# 2,3
# 7,3"""

    pairs = [tuple(map(int, row.split(','))) for row in puzzle_input.splitlines()]

    max_area = 0
    for p1, p2 in combinations(pairs, 2):
        area = (abs(p1[0]-p2[0])+1) * (abs(p1[1]-p2[1])+1)
        if area > max_area:
            max_area = area

    return max_area

def part_2():
    
    puzzle_input = get_input(2025, 9)

#     puzzle_input = """7,1
# 11,1
# 11,7
# 9,7
# 9,5
# 2,5
# 2,3
# 7,3"""

    pairs = [tuple(map(int, row.split(','))) for row in puzzle_input.splitlines()]

    available_tiles = set()


    # for p1, p2 in zip(pairs, pairs[1:] + [pairs[0]]):
        # available_tiles.add(p1)
        # available_tiles.add(p2)
        
        # if p1[0] - p2[0] > 0:
        #     translation = (-1,0)
        # elif p2[0] - p1[0] > 0:
        #     translation = (1, 0)
        # elif p2[1] - p1[1] > 0:
        #     translation = (0, 1)
        # elif p1[1] - p2[1] > 0:
        #     translation = (0, -1)

        # new_point = p1
        # while new_point != p2:
        #     new_point = (new_point[0] + translation[0], new_point[1] + translation[1])
        #     available_tiles.add(new_point)

    