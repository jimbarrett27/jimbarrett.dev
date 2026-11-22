from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2024, 4)

    grid = [list(row) for row in puzzle_input.splitlines()]
    height = len(grid)
    width = len(grid[0])

    total_xmas = 0
    for y in range(height):
        for x in range(width):
            
            if grid[y][x] != 'X':
                continue

            # left to right
            if (x < width - 3
                and grid[y][x+1] == 'M'
                and grid[y][x+2] == 'A'
                and grid[y][x+3] == 'S'
            ):
                total_xmas += 1

            # right to left
            if (x >= 3
                and grid[y][x-1] == 'M'
                and grid[y][x-2] == 'A'
                and grid[y][x-3] == 'S'
            ):
                total_xmas += 1

            # top to bottom
            if (y < height - 3
                and grid[y+1][x] == 'M'
                and grid[y+2][x] == 'A'
                and grid[y+3][x] == 'S'
            ):
                total_xmas += 1

            # bottom to top
            if (y >= 3
                and grid[y-1][x] == 'M'
                and grid[y-2][x] == 'A'
                and grid[y-3][x] == 'S'
            ):
                total_xmas += 1

            # LL to UR
            if (y >= 3 and x < width - 3
                and grid[y-1][x+1] == 'M'
                and grid[y-2][x+2] == 'A'
                and grid[y-3][x+3] == 'S'
            ):
                total_xmas += 1

            # UL to LR
            if (y < height - 3 and x < width - 3
                and grid[y+1][x+1] == 'M'
                and grid[y+2][x+2] == 'A'
                and grid[y+3][x+3] == 'S'
            ):
                total_xmas += 1

            # LR to UL
            if (y >= 3 and x >= 3
                and grid[y-1][x-1] == 'M'
                and grid[y-2][x-2] == 'A'
                and grid[y-3][x-3] == 'S'
            ):
                total_xmas += 1

            # UR to LL
            if (y < height - 3 and x >= 3
                and grid[y+1][x-1] == 'M'
                and grid[y+2][x-2] == 'A'
                and grid[y+3][x-3] == 'S'
            ):
                total_xmas += 1

    return total_xmas

def part_2():
    
    puzzle_input = get_input(2024, 4)

    grid = [list(row) for row in puzzle_input.splitlines()]
    height = len(grid)
    width = len(grid[0])

    total_x_mas = 0
    for y in range(1,height-1):
        for x in range(1,width-1):
            
            if grid[y][x] != 'A':
                continue

            if (
                grid[y-1][x-1] == 'M'
                and  grid[y+1][x+1] == 'S'
                and grid[y-1][x+1] == 'M'
                and grid[y+1][x-1] == 'S'
            ):
                total_x_mas += 1
            
            if (
                grid[y-1][x-1] == 'M'
                and  grid[y+1][x+1] == 'S'
                and grid[y-1][x+1] == 'S'
                and grid[y+1][x-1] == 'M'
            ):
                total_x_mas += 1
                
            if (
                grid[y-1][x-1] == 'S'
                and  grid[y+1][x+1] == 'M'
                and grid[y-1][x+1] == 'M'
                and grid[y+1][x-1] == 'S'
            ):
                total_x_mas += 1

            if (
                grid[y-1][x-1] == 'S'
                and  grid[y+1][x+1] == 'M'
                and grid[y-1][x+1] == 'S'
                and grid[y+1][x-1] == 'M'
            ):
                total_x_mas += 1

    return total_x_mas