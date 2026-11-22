from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2024, 11)

    stones = list(map(int, puzzle_input.split()))

    for _ in range(25):

        new_stones = []

        for stone in stones:
            if stone == 0:
                new_stones.append(1)
            elif (len(str(stone)) % 2) == 0:
                str_stone = str(stone)
                new_stones.append(int(str_stone[:len(str_stone)//2]))
                new_stones.append(int(str_stone[len(str_stone)//2:]))
            else:
                new_stones.append(stone * 2024)
    
        stones = new_stones

    return len(stones)

def part_2():
    
    puzzle_input = get_input(2024, 11)

    stones = list(map(int, puzzle_input.split()))

    def expand_stone(stone, depth, stone_cache):

        if depth == 75:
            return 1

        new_stones = []
        if stone == 0:
            new_stones.append(1)
        elif (len(str(stone)) % 2) == 0:
            str_stone = str(stone)
            new_stones.append(int(str_stone[:len(str_stone)//2]))
            new_stones.append(int(str_stone[len(str_stone)//2:]))
        else:
            new_stones.append(stone * 2024)

        tot = 0
        for new_stone in new_stones:
            if (new_stone, depth) in stone_cache:
                tot += stone_cache[(new_stone, depth)]
                continue

            final_length = expand_stone(new_stone, depth + 1, stone_cache)
            stone_cache[(new_stone, depth)] = final_length
            tot += final_length
        
        return tot

    stone_cache = {}
    tot = 0
    for stone in stones:
        tot += expand_stone(stone, 0, stone_cache)

    return tot