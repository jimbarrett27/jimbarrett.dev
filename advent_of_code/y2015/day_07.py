from advent_of_code.input import get_input

def part_1():
    puzzle_input = get_input(2015, 7)

    node_to_operation = {}
    for instruction in puzzle_input.splitlines():

        operation, node = instruction.split('->')
        node_to_operation[node.strip()] = operation.strip()

    node_to_value = {}
    def get_node_value(node):

        if node.isdigit():
            return int(node)
        
        if node in node_to_value:
            return node_to_value[node]

        operation = node_to_operation[node]
        operation_parts = operation.split()
        if len(operation_parts) == 1:
            val = (get_node_value(operation)) % 65536
        elif len(operation_parts) == 2:
            # this is NOT
            operand = get_node_value(operation_parts[1])
            val = (~operand) % 65536
        elif operation_parts[-1].isdigit():
            # this is LSHIFT or RSHIFT
            shift_value = int(operation_parts[-1])
            operator = operation_parts[1]
            operand = get_node_value(operation_parts[0])
            val = (operand >> shift_value if operator == 'RSHIFT' else operand << shift_value) % 65536
        else:
            # AND or OR
            operator = operation_parts[1]
            operand_1 = get_node_value(operation_parts[0])
            operand_2 = get_node_value(operation_parts[2])
            val = (operand_1 | operand_2 if operator == 'OR' else operand_1 & operand_2) % 65536
        
        node_to_value[node] = val
        return val

    return get_node_value('a') 
            


def part_2():
    puzzle_input = get_input(2015, 7)

    node_to_operation = {}
    for instruction in puzzle_input.splitlines():

        operation, node = instruction.split('->')
        node_to_operation[node.strip()] = operation.strip()

    node_to_operation['b'] = str(part_1())

    node_to_value = {}
    def get_node_value(node):

        if node.isdigit():
            return int(node)
        
        if node in node_to_value:
            return node_to_value[node]

        operation = node_to_operation[node]
        operation_parts = operation.split()
        if len(operation_parts) == 1:
            val = (get_node_value(operation)) % 65536
        elif len(operation_parts) == 2:
            # this is NOT
            operand = get_node_value(operation_parts[1])
            val = (~operand) % 65536
        elif operation_parts[-1].isdigit():
            # this is LSHIFT or RSHIFT
            shift_value = int(operation_parts[-1])
            operator = operation_parts[1]
            operand = get_node_value(operation_parts[0])
            val = (operand >> shift_value if operator == 'RSHIFT' else operand << shift_value) % 65536
        else:
            # AND or OR
            operator = operation_parts[1]
            operand_1 = get_node_value(operation_parts[0])
            operand_2 = get_node_value(operation_parts[2])
            val = (operand_1 | operand_2 if operator == 'OR' else operand_1 & operand_2) % 65536
        
        node_to_value[node] = val
        return val

    return get_node_value('a') 