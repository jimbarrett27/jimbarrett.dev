from advent_of_code.input import get_input
from itertools import combinations_with_replacement

def part_1():
    puzzle_input = """[.##.] (3) (1,3) (2) (2,3) (0,2) (0,1) {3,5,4,7}
[...#.] (0,2,3,4) (2,3) (0,4) (0,1,2) (1,2,3,4) {7,5,12,7,2}
[.###.#] (0,1,2,3,4) (0,3,4) (0,1,2,4,5) (1,2) {10,11,11,5,10,5}"""

    puzzle_input = get_input(2025, 10)

    rows = puzzle_input.splitlines()

    total_presses = 0
    for row in rows:

        elements = row.split()
        target_state = [0 if e == '.' else 1 for e in elements[0][1:-1]]
        buttons = [list(map(int, x[1:-1].split(','))) for x in elements[1:-1]]

        n_presses = 0
        solution_found = False
        while not solution_found:
            n_presses += 1
            for button_sequence in combinations_with_replacement(buttons, n_presses):
                state = [0 for _ in target_state]
                for button in button_sequence:
                    for ind in button:
                        state[ind] = (state[ind] + 1) % 2
                if state == target_state:
                    solution_found = True
                    break
            
        
        total_presses += n_presses

    return total_presses

def part_2():
    
    puzzle_input = """[.##.] (3) (1,3) (2) (2,3) (0,2) (0,1) {3,5,4,7}
[...#.] (0,2,3,4) (2,3) (0,4) (0,1,2) (1,2,3,4) {7,5,12,7,2}
[.###.#] (0,1,2,3,4) (0,3,4) (0,1,2,4,5) (1,2) {10,11,11,5,10,5}"""

    puzzle_input = get_input(2025, 10)

    rows = puzzle_input.splitlines()

    total_presses = 0
    for row in rows:

        elements = row.split()
        target_state = tuple(map(int, elements[-1][1:-1].split(',')))
        buttons = [list(map(int, x[1:-1].split(','))) for x in elements[1:-1]]

        n_presses = 0
        solution_found = False
        states_achieved = set([tuple([0 for _ in target_state])])
        previous_seen_states = set()
        while not solution_found:
            print(len(previous_seen_states))
            n_presses += 1
            new_states_achieved = set()
            for state in states_achieved:
                for button in buttons:
                    new_state = list(state)
                    for i in button:
                        new_state[i] += 1
                    new_state = tuple(new_state)
                    if new_state == target_state:
                        solution_found = True
                        continue
                    elif new_state in previous_seen_states:
                        continue
                    elif any(new_state[i] > target_state[i] for i in range(len(state))):
                        continue
                    else:
                        new_states_achieved.add(new_state)

            previous_seen_states |= new_states_achieved
            states_achieved = new_states_achieved

        total_presses += n_presses



            
        
        # total_presses += n_presses

    return total_presses