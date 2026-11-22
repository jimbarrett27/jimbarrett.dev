from advent_of_code.input import get_input
from itertools import permutations

def part_1():
    puzzle_input = get_input(2015, 9)

    pair_to_distance = {}
    all_places = set()
    for line in puzzle_input.splitlines():
        words = line.split()
        p1 = words[0]
        p2 = words[2]
        dist = int(words[-1])

        pair_to_distance[(p1,p2)] = dist
        pair_to_distance[(p2, p1)] = dist

        all_places.add(p1)
        all_places.add(p2)


    min_dist = 1000000000000000    
    for p in permutations(all_places):

        valid_route = True
        dist = 0
        for p1, p2 in zip(p[:-1], p[1:]):
            if (p1,p2) in pair_to_distance:
                dist += pair_to_distance[(p1,p2)]
            else:
                valid_route = False
                break
        
        if not valid_route:
            continue

        if dist < min_dist:
            min_dist = dist

    return min_dist

def part_2():
    
    puzzle_input = get_input(2015, 9)

    pair_to_distance = {}
    all_places = set()
    for line in puzzle_input.splitlines():
        words = line.split()
        p1 = words[0]
        p2 = words[2]
        dist = int(words[-1])

        pair_to_distance[(p1,p2)] = dist
        pair_to_distance[(p2, p1)] = dist

        all_places.add(p1)
        all_places.add(p2)


    max_dist = 0    
    for p in permutations(all_places):

        valid_route = True
        dist = 0
        for p1, p2 in zip(p[:-1], p[1:]):
            if (p1,p2) in pair_to_distance:
                dist += pair_to_distance[(p1,p2)]
            else:
                valid_route = False
                break
        
        if not valid_route:
            continue

        if dist > max_dist:
            max_dist = dist

    return max_dist