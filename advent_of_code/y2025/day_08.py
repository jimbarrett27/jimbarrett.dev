from advent_of_code.input import get_input
import math
from collections import defaultdict

def part_1():
    puzzle_input = get_input(2025, 8)

    rows = puzzle_input.splitlines()
    pair_to_distance = {}
    for i in range(len(rows)):
        for j in range(i):
            pair = (j, i)
            pi = list(map(int,rows[i].split(',')))
            pj = list(map(int,rows[j].split(',')))
            distance = math.sqrt((pi[0] - pj[0])**2 + (pi[1] - pj[1])**2 + (pi[2] - pj[2])**2)

            pair_to_distance[pair] = distance

    circuits = []
    for pair in sorted(pair_to_distance.keys(), key=pair_to_distance.get)[:1000]:

        i, j = pair

        i_present = any(i in c for c in circuits)
        j_present = any(j in c for c in circuits)

        if i_present and not j_present:
            for c in circuits:
                if i in c:
                    break
            c.add(j)
        elif j_present and not i_present:
            for c in circuits:
                if j in c:
                    break
            c.add(i)
        elif i_present and j_present:
            to_merge = []
            for c in circuits:
                if i in c:
                    to_merge.append(c)
                if j in c:
                    to_merge.append(c)
            
            if to_merge[0] == to_merge[1]:
                continue
            circuits.remove(to_merge[0])
            circuits.remove(to_merge[1])
            circuits.append(to_merge[0] | to_merge[1])

        else:
            circuits.append(set([i,j]))

    lengths = list(map(len, circuits))

    return math.prod(sorted(lengths, reverse=True)[:3])

def part_2():
    
    puzzle_input = get_input(2025, 8)

    rows = puzzle_input.splitlines()
    pair_to_distance = {}
    for i in range(len(rows)):
        for j in range(i):
            pair = (j, i)
            pi = list(map(int,rows[i].split(',')))
            pj = list(map(int,rows[j].split(',')))
            distance = math.sqrt((pi[0] - pj[0])**2 + (pi[1] - pj[1])**2 + (pi[2] - pj[2])**2)

            pair_to_distance[pair] = distance

    circuits = []
    for pair in sorted(pair_to_distance.keys(), key=pair_to_distance.get):

        i, j = pair

        i_present = any(i in c for c in circuits)
        j_present = any(j in c for c in circuits)

        if i_present and not j_present:
            for c in circuits:
                if i in c:
                    break
            c.add(j)
        elif j_present and not i_present:
            for c in circuits:
                if j in c:
                    break
            c.add(i)
        elif i_present and j_present:
            to_merge = []
            for c in circuits:
                if i in c:
                    to_merge.append(c)
                if j in c:
                    to_merge.append(c)
            
            if to_merge[0] == to_merge[1]:
                continue
            circuits.remove(to_merge[0])
            circuits.remove(to_merge[1])
            circuits.append(to_merge[0] | to_merge[1])

        else:
            circuits.append(set([i,j]))

        if len(circuits) == 1 and len(circuits[0]) == len(rows):
            break

    return int(rows[i].split(',')[0]) * int(rows[j].split(',')[0])