from advent_of_code.input import get_input


def part_1():
    puzzle_input = int(get_input(2015, 20).strip())

    trial_houses = 1000000
    houses = [10] * trial_houses
    for i in range(1,trial_houses):
        for j in range(i, trial_houses, i+1):
            houses[j] += (i+1)*10
            
                
    for i in range(trial_houses):
        if houses[i] >= puzzle_input:
            break

    return i+1



def part_2():
    puzzle_input = int(get_input(2015, 20).strip())

    trial_houses = 1000000
    houses = [11] * trial_houses
    for i in range(1,trial_houses):
        for j in range(50):
            next_ind = i + ((i+1)* j)
            # hopefully we've caught the answer by now
            if next_ind >= trial_houses:
                break
            houses[next_ind] += (i+1)*11
            
                
    for i in range(trial_houses):
        if houses[i] >= puzzle_input:
            break

    return i+1