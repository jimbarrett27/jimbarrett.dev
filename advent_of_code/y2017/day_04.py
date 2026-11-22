from advent_of_code.input import get_input

def part_1():
    input_data = get_input(2017,4).splitlines()[:-1]
    n_valid = 0
    for line in input_data:
        words = line.split()
        if len(set(words)) == len(words):
            n_valid +=1
    return n_valid

def part_2():
    input_data = get_input(2017,4).splitlines()[:-1]
    n_valid = 0
    for line in input_data:
        words = line.split()
        sorted_words = list(map(lambda x: ''.join(sorted(x)), words))
        if len(set(sorted_words)) == len(words):
            n_valid += 1
        
    return n_valid 
