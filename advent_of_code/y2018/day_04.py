from advent_of_code.input import get_input
from collections import Counter, defaultdict

def part_1():

    puzzle_input = get_input(2018, 4)
#     puzzle_input = """[1518-11-01 00:00] Guard #10 begins shift
# [1518-11-01 00:05] falls asleep
# [1518-11-01 00:25] wakes up
# [1518-11-01 00:30] falls asleep
# [1518-11-01 00:55] wakes up
# [1518-11-01 23:58] Guard #99 begins shift
# [1518-11-02 00:40] falls asleep
# [1518-11-02 00:50] wakes up
# [1518-11-03 00:05] Guard #10 begins shift
# [1518-11-03 00:24] falls asleep
# [1518-11-03 00:29] wakes up
# [1518-11-04 00:02] Guard #99 begins shift
# [1518-11-04 00:36] falls asleep
# [1518-11-04 00:46] wakes up
# [1518-11-05 00:03] Guard #99 begins shift
# [1518-11-05 00:45] falls asleep
# [1518-11-05 00:55] wakes up
# """

    guard_to_total_asleep = Counter()
    guard_to_slept_minutes = defaultdict(Counter)
    guard_id = -1
    minutes_asleep = set()

    for event in sorted(puzzle_input.splitlines()):

        timestamp = event.split(']')[0][1:]
        info = event.split(']')[1]
        date, time = timestamp.split()
        year, month, day = map(int, date.split('-'))
        hour, minute = map(int, time.split(':'))

        if 'Guard' in event:

            guard_to_total_asleep[guard_id] += len(minutes_asleep)
            guard_to_slept_minutes[guard_id] += Counter(minutes_asleep)

            guard_id = int(info.split(' Guard ')[1].split()[0][1:])

            current_minute = 0 if hour == 23 else minute

            minutes_awake = set()
            minutes_asleep = set()

        elif 'asleep' in event:
            minutes_awake.update(set(range(current_minute, minute)))
            current_minute = minute
            
        elif 'wakes' in event:
            minutes_asleep.update(set(range(current_minute, minute)))
            current_minute = minute

    sleepy_guard = guard_to_total_asleep.most_common()[0]
    return sleepy_guard[0] * guard_to_slept_minutes[sleepy_guard[0]].most_common()[0][0]

def part_2():
    puzzle_input = get_input(2018, 4)
#     puzzle_input = """[1518-11-01 00:00] Guard #10 begins shift
# [1518-11-01 00:05] falls asleep
# [1518-11-01 00:25] wakes up
# [1518-11-01 00:30] falls asleep
# [1518-11-01 00:55] wakes up
# [1518-11-01 23:58] Guard #99 begins shift
# [1518-11-02 00:40] falls asleep
# [1518-11-02 00:50] wakes up
# [1518-11-03 00:05] Guard #10 begins shift
# [1518-11-03 00:24] falls asleep
# [1518-11-03 00:29] wakes up
# [1518-11-04 00:02] Guard #99 begins shift
# [1518-11-04 00:36] falls asleep
# [1518-11-04 00:46] wakes up
# [1518-11-05 00:03] Guard #99 begins shift
# [1518-11-05 00:45] falls asleep
# [1518-11-05 00:55] wakes up
# """
    
    guard_to_slept_minutes = defaultdict(Counter)
    guard_id = -1
    minutes_asleep = set()

    for event in sorted(puzzle_input.splitlines()):

        timestamp = event.split(']')[0][1:]
        info = event.split(']')[1]
        date, time = timestamp.split()
        year, month, day = map(int, date.split('-'))
        hour, minute = map(int, time.split(':'))

        if 'Guard' in event:

            if guard_id > 0:
                guard_to_slept_minutes[guard_id] += Counter(minutes_asleep)

            guard_id = int(info.split(' Guard ')[1].split()[0][1:])

            current_minute = 0 if hour == 23 else minute

            minutes_awake = set()
            minutes_asleep = set()

        elif 'asleep' in event:
            minutes_awake.update(set(range(current_minute, minute)))
            current_minute = minute
            
        elif 'wakes' in event:
            minutes_asleep.update(set(range(current_minute, minute)))
            current_minute = minute

    guard_to_slept_minutes[guard_id] += Counter(minutes_asleep)

    max_slept_minute = -1
    max_guard_id = -1
    max_slept_minute_count = -1
    for guard_id, slept_minutes in guard_to_slept_minutes.items():

        if not slept_minutes:
            continue

        slept_minute, slept_count = slept_minutes.most_common()[0]
        if slept_count > max_slept_minute_count:
            max_slept_minute_count = slept_count
            max_guard_id = guard_id
            max_slept_minute = slept_minute

    return max_guard_id * max_slept_minute
