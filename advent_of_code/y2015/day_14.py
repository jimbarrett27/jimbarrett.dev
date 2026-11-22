from advent_of_code.input import get_input
from dataclasses import dataclass

@dataclass
class Reindeer:

    name: str
    speed: int
    stamina: int
    recovery: int

    pos: int = 0
    time_in_phase: int = 0
    currently_running: bool = True

def part_1():
    
    puzzle_input = get_input(2015, 14)

    MAX_TIME = 2503

    reindeers: list[Reindeer] = []
    for line in puzzle_input.splitlines():
        words = line.split()
        reindeers.append(Reindeer(
            name=words[0],
            speed=int(words[3]),
            stamina=int(words[6]),
            recovery=int(words[-2])
        ))

    current_time = 0
    while current_time < MAX_TIME:

        for reindeer in reindeers:

            if reindeer.currently_running and reindeer.time_in_phase == reindeer.stamina:
                reindeer.currently_running = False
                reindeer.time_in_phase = 0

            elif not reindeer.currently_running and reindeer.time_in_phase == reindeer.recovery:
                reindeer.currently_running = True
                reindeer.time_in_phase = 0

            reindeer.pos += reindeer.currently_running * reindeer.speed
            reindeer.time_in_phase += 1

        current_time += 1

    return max(reindeers, key=lambda x: x.pos).pos

def part_2():
    puzzle_input = get_input(2015, 14)

    MAX_TIME = 2503

    reindeers: list[Reindeer] = []
    for line in puzzle_input.splitlines():
        words = line.split()
        reindeers.append(Reindeer(
            name=words[0],
            speed=int(words[3]),
            stamina=int(words[6]),
            recovery=int(words[-2])
        ))


    reindeer_to_score = {r.name: 0 for r in reindeers}

    current_time = 0
    while current_time < MAX_TIME:

        for reindeer in reindeers:

            if reindeer.currently_running and reindeer.time_in_phase == reindeer.stamina:
                reindeer.currently_running = False
                reindeer.time_in_phase = 0

            elif not reindeer.currently_running and reindeer.time_in_phase == reindeer.recovery:
                reindeer.currently_running = True
                reindeer.time_in_phase = 0

            reindeer.pos += reindeer.currently_running * reindeer.speed
            reindeer.time_in_phase += 1

        current_time += 1

        furthest_pos = max(reindeers, key=lambda x: x.pos).pos

        for reindeer in reindeers:
            if reindeer.pos == furthest_pos:
                reindeer_to_score[reindeer.name] += 1

    return max(reindeer_to_score.values())
