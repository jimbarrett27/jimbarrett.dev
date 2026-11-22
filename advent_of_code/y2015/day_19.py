from advent_of_code.input import get_input
from collections import defaultdict

def part_1():
    
    puzzle_input = get_input(2015, 19)

    mappings = defaultdict(list)
    for line in puzzle_input.splitlines():

        if '=>' in line:
            source, dest = line.split('=>')
            mappings[source.strip()].append(dest.strip())

        else:
            medicine = line.strip()

    possible_molecules = set()
    for source, dests in mappings.items():

        source_len = len(source)
        for i in range(len(medicine) - source_len + 1):
            if medicine[i: i+source_len] == source:
                for dest in dests:
                    possible_molecules.add(medicine[:i] + dest + medicine[i+source_len:])

    return len(possible_molecules)

def part_2():
    """
    Extremely unsatisfying solution here, there's no good reaosn this should work
    but a general solution would be extremely complex to implement
    """
    
    puzzle_input = get_input(2015, 19)

    mappings = defaultdict(list)
    for line in puzzle_input.splitlines():

        if '=>' in line:
            source, dest = line.split('=>')
            mappings[source.strip()].append(dest.strip())

        else:
            medicine = line.strip()


    new_mappings = {}
    for source, dests in mappings.items():
        for dest in dests:
            new_mappings[dest] = source

    mappings = new_mappings

    molecule = medicine
    n = 0
    while molecule != 'e':
        for product, reactant in sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True):
            if product in molecule:
                molecule = molecule.replace(product, reactant, 1)
                n = n+1
            
    return n
