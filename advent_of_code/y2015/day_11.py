from advent_of_code.input import get_input
from collections import defaultdict

LETTER_TO_NUMB = dict(zip('abcdefghijklmnopqrstuvwxyz', range(26)))

def _increment_base_26(numb: list[int]):

    done = False
    num_len = len(numb)
    for i in range(len(numb)):
        ind = num_len -i - 1
        if numb[ind] == 25:
            numb[ind] = 0
        else:
            numb[ind] = numb[ind] + 1
            done = True
            break

    if not done:
        numb = [1] + numb

    return numb

def _valid_password(p):

    bad_letters = {LETTER_TO_NUMB[l] for l in 'lio'}
    if any(c in bad_letters for c in p):
        return False

    present_pairs = {(a,b) for a,b in zip(p[:-1], p[1:]) if a==b}

    if len(present_pairs) < 2:
        return False

    valid_run = False
    for a, b, c in zip(p[:-2], p[1:-1], p[2:]):
        if c-b == 1 and c-a == 2:
            valid_run = True
            break

    if not valid_run:
        return False

    return True

def part_1():
    
    puzzle_input = get_input(2015, 11).strip()
    numb = [LETTER_TO_NUMB[c] for c in puzzle_input]
    while True:
        numb = _increment_base_26(numb)
        if _valid_password(numb):
            break
        
    NUMB_TO_LETTER = {n: l for l, n in LETTER_TO_NUMB.items()}
    return ''.join(NUMB_TO_LETTER[x] for x in numb)


def part_2():
    
    puzzle_input = part_1()
    numb = [LETTER_TO_NUMB[c] for c in puzzle_input]
    while True:
        numb = _increment_base_26(numb)
        if _valid_password(numb):
            break
        
    NUMB_TO_LETTER = {n: l for l, n in LETTER_TO_NUMB.items()}
    return ''.join(NUMB_TO_LETTER[x] for x in numb)
