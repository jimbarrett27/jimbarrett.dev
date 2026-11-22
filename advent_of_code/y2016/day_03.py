from advent_of_code.input import get_input

def part_1():
    puzzle_input = get_input(2016, 3)

    n_possible = 0
    for row in puzzle_input.splitlines():
        s1, s2, s3 = list(map(int,row.split()))
        
        if any([
            s1 +s2 <= s3,
            s1 + s3 <= s2,
            s2 + s3 <= s1
        ]):
            continue
        
        n_possible += 1

    return n_possible
            

def part_2():
    
    puzzle_input = get_input(2016, 3)

    n_possible = 0
    s1s = []
    s2s = []
    s3s = []
    for i, row in enumerate(puzzle_input.splitlines()):
        
        s1, s2, s3 = list(map(int,row.split()))
        s1s.append(s1)
        s2s.append(s2)
        s3s.append(s3)

        if (i+1) % 3 == 0:

            for x in [s1s, s2s, s3s]:

                s1, s2, s3 = x
                if any([
                    s1 +s2 <= s3,
                    s1 + s3 <= s2,
                    s2 + s3 <= s1
                ]):
                    continue
                n_possible += 1
            
            s1s = []
            s2s = []
            s3s = []
        

    return n_possible