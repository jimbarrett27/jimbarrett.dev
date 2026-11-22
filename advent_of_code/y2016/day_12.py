from advent_of_code.input import get_input

def part_1():
    
    instructions = get_input(2016, 12).splitlines()

#     instructions = """cpy 41 a
# inc a
# inc a
# dec a
# jnz a 2
# dec a""".splitlines()

    registers = {'a': 0, 'b':0, 'c': 0, 'd':0}

    ins_ind = 0
    while ins_ind < len(instructions):

        instruction = instructions[ins_ind].split()

        match instruction[0]:
            case 'cpy':
                val = int(instruction[1]) if instruction[1].isnumeric() else registers[instruction[1]]
                registers[instruction[2]] = val 
                ins_ind += 1
            case 'inc':
                registers[instruction[1]] += 1
                ins_ind += 1
            case 'dec':
                registers[instruction[1]] -= 1
                ins_ind += 1
            case 'jnz':
                jmp = 1
                if instruction[1].isdigit() or registers[instruction[1]] !=0:
                    jmp = int(instruction[2])
                ins_ind += jmp

    return registers['a']



def part_2():
    
    instructions = get_input(2016, 12).splitlines()

#     instructions = """cpy 41 a
# inc a
# inc a
# dec a
# jnz a 2
# dec a""".splitlines()

    registers = {'a': 0, 'b':0, 'c': 1, 'd':0}

    ins_ind = 0
    while ins_ind < len(instructions):

        instruction = instructions[ins_ind].split()

        match instruction[0]:
            case 'cpy':
                val = int(instruction[1]) if instruction[1].isnumeric() else registers[instruction[1]]
                registers[instruction[2]] = val 
                ins_ind += 1
            case 'inc':
                registers[instruction[1]] += 1
                ins_ind += 1
            case 'dec':
                registers[instruction[1]] -= 1
                ins_ind += 1
            case 'jnz':
                jmp = 1
                if instruction[1].isdigit() or registers[instruction[1]] !=0:
                    jmp = int(instruction[2])
                ins_ind += jmp

    return registers['a']