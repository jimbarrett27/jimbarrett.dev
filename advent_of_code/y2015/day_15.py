from advent_of_code.input import get_input
from dataclasses import dataclass
from itertools import combinations_with_replacement
from math import prod

@dataclass
class Ingredient:

    name: str

    capacity: int
    durability: int
    flavour: int
    texture: int
    calories: int

def part_1():
    
    puzzle_input = get_input(2015, 15)

    ingredients = []
    for line in puzzle_input.splitlines():
        words = line.replace(',','').split()
        ingredients.append(Ingredient(
            name=words[0].replace(':', ''),
            capacity=int(words[2]),
            durability=int(words[4]),
            flavour=int(words[6]),
            texture=int(words[8]),
            calories=int(words[-1])
        ))

    

    scores = []
    for combo in combinations_with_replacement(ingredients, 100):

        components = [0,0,0,0]
        for ingredient in combo:
            components[0] += ingredient.capacity
            components[1] += ingredient.durability
            components[2] += ingredient.flavour
            components[3] += ingredient.texture

        if any(c < 0 for c in components):
            scores.append(0)
        else:
            scores.append(prod(components))

    return max(scores)

def part_2():
    puzzle_input = get_input(2015, 15)

    ingredients = []
    for line in puzzle_input.splitlines():
        words = line.replace(',','').split()
        ingredients.append(Ingredient(
            name=words[0].replace(':', ''),
            capacity=int(words[2]),
            durability=int(words[4]),
            flavour=int(words[6]),
            texture=int(words[8]),
            calories=int(words[-1])
        ))

    

    scores = []
    for combo in combinations_with_replacement(ingredients, 100):

        components = [0,0,0,0]
        calories = 0
        for ingredient in combo:
            components[0] += ingredient.capacity
            components[1] += ingredient.durability
            components[2] += ingredient.flavour
            components[3] += ingredient.texture

            calories += ingredient.calories
            if calories > 500:
                break

        if calories != 500:
            scores.append(0)

        elif any(c < 0 for c in components):
            scores.append(0)
        else:
            scores.append(prod(components))

    return max(scores)