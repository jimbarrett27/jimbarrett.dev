from advent_of_code.input import get_input

test_input = """Button A: X+94, Y+34
Button B: X+22, Y+67
Prize: X=8400, Y=5400

Button A: X+26, Y+66
Button B: X+67, Y+21
Prize: X=12748, Y=12176

Button A: X+17, Y+86
Button B: X+84, Y+37
Prize: X=7870, Y=6450

Button A: X+69, Y+23
Button B: X+27, Y+71
Prize: X=18641, Y=10279
"""

def part_1():
    
    puzzle_input = get_input(2024, 13)

    a_buttons = []
    b_buttons = []
    prizes = []
    for row in puzzle_input.splitlines():
        if row.startswith('Button A:'):
            x_str, y_str = row.split(':')[1].split(',')
            a_buttons.append((int(x_str.replace('X+', '')), int(y_str.replace('Y+', ''))))
        elif row.startswith('Button B:'):
            x_str, y_str = row.split(':')[1].split(',')
            b_buttons.append((int(x_str.replace('X+', '')), int(y_str.replace('Y+', ''))))
        elif row.startswith('Prize:'):
            x_str, y_str = row.split(':')[1].split(',')
            prizes.append((int(x_str.replace('X=', '')), int(y_str.replace('Y=', ''))))

    overall_presses = 0
    for a, b, p in zip(a_buttons, b_buttons, prizes):
        possible_combos = []
        for x in range(100):
            for y in range(100):
                tot = (x*a[0] + y*b[0], x*a[1] + y*b[1])
                if tot == p:
                    possible_combos.append(3*x + y)

        if len(possible_combos) > 0:
            overall_presses += min(possible_combos)
    
    return overall_presses


def part_2():
    
    puzzle_input = get_input(2024, 13)

    # puzzle_input = test_input

    a_buttons = []
    b_buttons = []
    prizes = []
    for row in puzzle_input.splitlines():
        if row.startswith('Button A:'):
            x_str, y_str = row.split(':')[1].split(',')
            a_buttons.append((int(x_str.replace('X+', '')), int(y_str.replace('Y+', ''))))
        elif row.startswith('Button B:'):
            x_str, y_str = row.split(':')[1].split(',')
            b_buttons.append((int(x_str.replace('X+', '')), int(y_str.replace('Y+', ''))))
        elif row.startswith('Prize:'):
            x_str, y_str = row.split(':')[1].split(',')
            prizes.append((int(x_str.replace('X=', '')), int(y_str.replace('Y=', ''))))
    

    overall_tokens = 0
    for a, b, p in zip(a_buttons, b_buttons, prizes):

        p = (p[0] + 10000000000000, p[1] + 10000000000000)

        det = (a[0]*b[1]) - (a[1]*b[0])

        if det == 0:
            continue

        a_presses = (b[1]*p[0] - b[0]*p[1]) / det
        b_presses = (a[0]*p[1] - a[1]*p[0]) / det

        if a_presses != int(a_presses):
            continue

        if b_presses != int(b_presses):
            continue

        overall_tokens += 3*a_presses + b_presses          


    return int(overall_tokens)