from advent_of_code.input import get_input

def print_screen(screen):

    for row in screen:
        s = ''
        for pix in row:
            s += '#' if pix == 1 else '.'
        print(s)

    print()

def part_1():
    
    puzzle_input = get_input(2016, 8)

    N_ROWS, N_COLS = 6, 50

    screen = []
    for _ in range(N_ROWS):
        row = []
        for _ in range(N_COLS):
            row.append(0)
        screen.append(row)


    for instruction in puzzle_input.splitlines():

        commands = instruction.split()

        if commands[0] == 'rect':
            w, h = map(int,commands[1].split('x'))
            for x in range(w):
                for y in range(h):
                    screen[y][x] = 1

        elif commands[1] == 'row':
            A = int(commands[2].split('=')[-1])
            B = int(commands[-1])
            
            screen[A] = screen[A][-B:] + screen[A][:-B]

        elif commands[1] == 'column':
            A = int(commands[2].split('=')[-1])
            B = int(commands[-1])
            
            relevant_col = [screen[i][A] for i in range(N_ROWS)]
            new_col = relevant_col[-B:] + relevant_col[:-B]

            for i in range(N_ROWS):
                screen[i][A] = new_col[i]


    number_pixels = 0
    for row in screen:
        number_pixels += sum(row)

    print_screen(screen)

    return number_pixels


def part_2():
    
    return "see printed val from part 1"