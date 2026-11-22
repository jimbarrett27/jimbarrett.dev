from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2015, 6)

    lights = []
    for x in range(1000):
        row = []
        for y in range(1000):
            row.append(False)
        lights.append(row)
        
    for instruction in puzzle_input.splitlines():

        instruction_parts = instruction.split()
        if instruction_parts[0] == 'toggle':
            task = instruction_parts[0]
            coord_1 = tuple(map(int,instruction_parts[1].split(',')))
            coord_2 = tuple(map(int,instruction_parts[3].split(',')))
        else:
            task = ' '.join(instruction_parts[:2])
            coord_1 = tuple(map(int,instruction_parts[2].split(',')))
            coord_2 = tuple(map(int,instruction_parts[4].split(',')))

        for x in range(coord_1[0], coord_2[0]+1):
            for y in range(coord_1[1], coord_2[1]+1):
                if task == 'toggle':
                    lights[x][y] = not lights[x][y]
                elif task == 'turn off':
                    lights[x][y] = False
                elif task == 'turn on':
                    lights[x][y] = True

    total_on = 0
    for row in lights:
        total_on += sum(row)
    
    return total_on

def part_2():
    puzzle_input = get_input(2015, 6)

    lights = []
    for x in range(1000):
        row = []
        for y in range(1000):
            row.append(0)
        lights.append(row)
        
    for instruction in puzzle_input.splitlines():

        instruction_parts = instruction.split()
        if instruction_parts[0] == 'toggle':
            task = instruction_parts[0]
            coord_1 = tuple(map(int,instruction_parts[1].split(',')))
            coord_2 = tuple(map(int,instruction_parts[3].split(',')))
        else:
            task = ' '.join(instruction_parts[:2])
            coord_1 = tuple(map(int,instruction_parts[2].split(',')))
            coord_2 = tuple(map(int,instruction_parts[4].split(',')))

        for x in range(coord_1[0], coord_2[0]+1):
            for y in range(coord_1[1], coord_2[1]+1):
                if task == 'toggle':
                    lights[x][y] += 2
                elif task == 'turn off':
                    lights[x][y] -= 1
                    lights[x][y] = 0 if lights[x][y] < 0 else lights[x][y]
                elif task == 'turn on':
                    lights[x][y] += 1

    total_brightness = 0
    for row in lights:
        total_brightness += sum(row)
    
    return total_brightness
