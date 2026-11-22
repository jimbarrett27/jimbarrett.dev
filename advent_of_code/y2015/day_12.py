from advent_of_code.input import get_input
import json

def part_1():
    
    data = json.loads(get_input(2015, 12))

    def sum_numbers(node):
        if isinstance(node, dict):
            return sum(sum_numbers(n) for n in node.values())
        elif isinstance(node, list):
            return sum(sum_numbers(n) for n in node)
        elif isinstance(node, int):
            return int(node)
        elif isinstance(node, str):
            return 0
        
    return sum_numbers(data)

def part_2():
    
    data = json.loads(get_input(2015, 12))

    def sum_numbers(node):
        if isinstance(node, dict):
            if any(n == 'red' for n in node.values()):
                return 0
            else:
                return sum(sum_numbers(n) for n in node.values())
        elif isinstance(node, list):
            return sum(sum_numbers(n) for n in node)
        elif isinstance(node, int):
            return int(node)
        elif isinstance(node, str):
            return 0
        
    return sum_numbers(data)