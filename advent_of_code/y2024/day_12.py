from advent_of_code.input import get_input
from collections import defaultdict

test_input = """RRRRIICCFF
RRRRIICCCF
VVRRRCCFFF
VVRCCCJFFF
VVVVCJJCFE
VVIVCCJJEE
VVIIICJJEE
MIIIIIJJEE
MIIISIJEEE
MMMISSJEEE
"""

test_input = """EEEEE
EXXXX
EEEEE
EXXXX
EEEEE
"""




def part_1():
    
    puzzle_input = get_input(2024, 12)

    # puzzle_input = test_input

    plant_type_to_pos = defaultdict(list)
    pos_to_plant_type = {}
    for i, row in enumerate(puzzle_input.splitlines()):
        for j, plant in enumerate(row):
            plant_type_to_pos[plant].append((i,j))
            pos_to_plant_type[(i,j)] = plant

    
    def find_contiguous_region(pos, plant_type, contiguous_region):

        if pos not in pos_to_plant_type:
            return
        
        if pos_to_plant_type[pos] != plant_type:
            return

        if pos in contiguous_region:
            return

        
        contiguous_region.add(pos)

        for neighbouring_pos in {
            (pos[0]-1, pos[1]), 
            (pos[0]+1, pos[1]), 
            (pos[0], pos[1]-1), 
            (pos[0], pos[1]+1)
        }:
            find_contiguous_region(neighbouring_pos, plant_type, contiguous_region)

    total_price = 0
    for plant_type in plant_type_to_pos:

        positions = plant_type_to_pos[plant_type]

        contiguous_regions = []
        for pos in positions:
            if any(pos in region for region in contiguous_regions):
                continue
            
            region = set()
            find_contiguous_region(pos, plant_type, region)

            contiguous_regions.append(region)

        for region in contiguous_regions:
            perimiter = 0
            for pos in region:
                for neighbouring_pos in {
                    (pos[0]-1, pos[1]), 
                    (pos[0]+1, pos[1]), 
                    (pos[0], pos[1]-1), 
                    (pos[0], pos[1]+1)
                }:
                    if neighbouring_pos not in pos_to_plant_type or pos_to_plant_type[neighbouring_pos] != plant_type:
                        perimiter += 1

            total_price += perimiter * len(region)

    return total_price


    

def part_2():
    pass