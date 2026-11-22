from advent_of_code.input import get_input
from itertools import combinations
from math import prod

def part_1():
    
    puzzle_input = get_input(2015, 24)

    weights = list(map(int, puzzle_input.splitlines()))

    for group_1_size in range(len(weights)):

        valid_configurations = []
        for group_1 in combinations(weights, group_1_size):

            remaining_weights = set(weights) - set(group_1)
            group_1_weight = sum(group_1)

            if sum(remaining_weights) != 2*group_1_weight:
                continue

            target_sum = group_1_weight
            
            dp = [False] * (target_sum + 1)
            dp[0] = True

            for weight in remaining_weights:
                for i in range(target_sum, weight-1, -1):
                    dp[i] = dp[i] or dp[i-weight]

            if dp[target_sum]:
                valid_configurations.append(group_1)
            


        if len(valid_configurations) > 0:
            entanglements = [prod(g) for g in valid_configurations]
            return min(entanglements)
        
    

def part_2():
    
    puzzle_input = get_input(2015, 24)

    weights = list(map(int, puzzle_input.splitlines()))

    for group_1_size in range(len(weights)):

        valid_configurations = []
        for group_1 in combinations(weights, group_1_size):

            remaining_weights = set(weights) - set(group_1)
            group_1_weight = sum(group_1)

            if sum(remaining_weights) != 3*group_1_weight:
                continue

            target_sum = group_1_weight
            
            dp = [False] * (target_sum + 1)
            dp[0] = True

            for weight in remaining_weights:
                for i in range(target_sum, weight-1, -1):
                    dp[i] = dp[i] or dp[i-weight]

            if dp[target_sum]:
                valid_configurations.append(group_1)
            


        if len(valid_configurations) > 0:
            entanglements = [prod(g) for g in valid_configurations]
            return min(entanglements)