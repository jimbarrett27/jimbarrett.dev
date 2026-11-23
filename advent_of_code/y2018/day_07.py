from advent_of_code.input import get_input
from collections import defaultdict

def part_1():

    puzzle_input = get_input(2018, 7)

    step_to_deps = defaultdict(set)
    all_steps = set()
    for line in puzzle_input.splitlines():
        words = line.split()

        dep = words[1]
        step = words[-3]

        step_to_deps[step].add(dep)
        all_steps.add(step)
        all_steps.add(dep)

    step_to_deps.update({step: set() for step in all_steps if step not in step_to_deps})

    completed_steps = []
    while len(completed_steps) < len(all_steps):

        available_steps = []
        for step, deps in step_to_deps.items(): 
            if (step not in completed_steps) and all(dep in completed_steps for dep in deps):
                available_steps.append(step)

        completed_steps.append(sorted(available_steps)[0])

    return ''.join(completed_steps)


def part_2():

    puzzle_input = get_input(2018, 7)

    n_workers = 5

    step_to_deps = defaultdict(set)
    all_steps = set()
    for line in puzzle_input.splitlines():
        words = line.split()

        dep = words[1]
        step = words[-3]

        step_to_deps[step].add(dep)
        all_steps.add(step)
        all_steps.add(dep)

    step_to_deps.update({step: set() for step in all_steps if step not in step_to_deps})

    step_to_cost = {step: 60 + i + 1 for i, step in enumerate(sorted(all_steps))}

    completed_steps = []
    ongoing_steps = []
    time = -1

    while len(completed_steps) < len(all_steps):

        time += 1

        new_ongoing_steps = []
        for step, progress in ongoing_steps:
            new_progress = progress + 1

            if new_progress == step_to_cost[step]:
                completed_steps.append(step)
            else:
                new_ongoing_steps.append((step, new_progress))

        ongoing_steps = new_ongoing_steps


        if len(ongoing_steps) >= n_workers:
            continue

        available_steps = []
        for step, deps in step_to_deps.items(): 
            if (
                (step not in completed_steps) 
                and all(dep in completed_steps for dep in deps) 
                and (step not in {x[0] for x in ongoing_steps})
            ):
                available_steps.append(step)

        available_workers = n_workers - len(ongoing_steps)

        sorted_available_steps = sorted(available_steps)

        for i in range(min(available_workers, len(available_steps))):
            ongoing_steps.append((sorted_available_steps[i], 0))

        
    return time