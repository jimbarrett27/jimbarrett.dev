from advent_of_code.input import get_input
from collections import Counter, defaultdict

def part_1():
    
    puzzle_input = get_input(2018, 3)

    square_claims = Counter()
    for claim in puzzle_input.splitlines():

        info = claim.split('@')[1]
        le, te = map(int, info.split(':')[0].split(','))
        w, h = map(int, info.split(':')[1].split('x'))

        for x in range(le, le + w):
            for y in range(te, te + h):

                square_claims[(x, y)] += 1

    return sum(1 for v in square_claims.values() if v > 1)

def part_2():

    puzzle_input = get_input(2018, 3)
        
    square_claims = Counter()    
    claim_id_to_claimed_squares = defaultdict(set)
    for claim in puzzle_input.splitlines():

        claim_id, info = claim.split('@')
        le, te = map(int, info.split(':')[0].split(','))
        w, h = map(int, info.split(':')[1].split('x'))

        for x in range(le, le + w):
            for y in range(te, te + h):

                square_claims[(x,y)] += 1
                claim_id_to_claimed_squares[claim_id].add((x,y))


    for claim_id, claimed_squares in claim_id_to_claimed_squares.items():
        if all(map(lambda x: square_claims[x] == 1, claimed_squares)):
            return claim_id[1:]
        
    
