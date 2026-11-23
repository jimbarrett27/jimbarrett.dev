from advent_of_code.input import get_input
from collections import defaultdict, Counter

def manhattan_distance(p1, p2):
    xs = p1[0], p2[0]
    ys = p1[1], p2[1]
    return abs((max(xs)-min(xs)) + (max(ys)-min(ys)))

def part_1():

    puzzle_input = get_input(2018, 6)

    coords = {(int(x),int(y)) for  x,y in map(lambda z: z.split(','), puzzle_input.splitlines())}

    coord_to_letter = {c: l for c, l in zip(coords, 'abcdef')}
    coord_to_letter['.'] = '.'

    min_x = min(c[0] for c in coords)
    max_x = max(c[0] for c in coords)
    min_y = min(c[1] for c in coords)
    max_y = max(c[1] for c in coords)

    max_radius = max(max_x - min_x, max_y - min_y)

    point_to_closest = {}
    for i in range(0, max_radius):
        moves = set(zip(range(i+1), range(i, -1, -1)))
        moves.update({(-move[0], move[1]) for move in moves})
        moves.update({(move[0], -move[1]) for move in moves})

        this_round = defaultdict(set)
        for coord in coords:
            for move in moves:
                x, y = coord[0] + move[0], coord[1] + move[1]

                if (x,y) in point_to_closest:
                    continue

                this_round[(x,y)].add(coord)


        touched_coords = {'.'}
        finalised = {}
        for point, cs in this_round.items():
            
            if len(cs) > 1:
                finalised[point] = '.'
            else:
                c = list(cs)[0]
                finalised[point] = c
                touched_coords.add(c)
                
        point_to_closest.update(finalised)

    counts = Counter(v for v in point_to_closest.values() if v not in touched_coords)

    return max(counts.values())


def part_2():

    puzzle_input = get_input(2018, 6)

    coords = {(int(x),int(y)) for  x,y in map(lambda z: z.split(','), puzzle_input.splitlines())}

    max_radius = 10000

    point_to_sum = Counter()
    point_to_coords_considered = defaultdict(set)
    coord_to_seen_coords = defaultdict(set)

    for coord in coords:

        for i in range(0, max_radius):

            if len(coord_to_seen_coords[coord]) == len(coords):
                continue
            moves = set(zip(range(i+1), range(i, -1, -1)))
            moves.update({(-move[0], move[1]) for move in moves})
            moves.update({(move[0], -move[1]) for move in moves})

            for move in moves:
                x, y = coord[0] + move[0], coord[1] + move[1]

                point_to_sum[(x,y)] += i
                point_to_coords_considered[(x,y)].add(coord)

                if (x,y) in coords:
                    coord_to_seen_coords[coord].add((x,y))

    area = 0
    for point, cs in point_to_coords_considered.items():
        if len(cs) == len(coords) and point_to_sum[point] < max_radius:
            area += 1

    return area