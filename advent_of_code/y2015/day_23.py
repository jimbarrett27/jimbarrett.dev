from advent_of_code.input import get_input

def part_1():
    
    puzzle_input = get_input(2015, 23)

    instructions = []
    for line in puzzle_input.splitlines():
        instructions.append(line)

    i=0
    registers = {'a': 0, 'b': 0}
    while i < len(instructions):

        instruction = instructions[i]

        if instruction.startswith('hlf'):
            register = instruction.split()[1]
            registers[register] /= 2
            i+=1
        elif instruction.startswith('tpl'):
            register = instruction.split()[1]
            registers[register] *= 3
            i+=1
        elif instruction.startswith('inc'):
            register = instruction.split()[1]
            registers[register] += 1
            i += 1
        elif instruction.startswith('jmp'):
            offset = instruction.split()[1]
            numb = int(offset[1:]) 
            if offset.startswith('-'):
                numb *= -1
            i += numb
        elif instruction.startswith('jie'):
            _, register,offset = instruction.split()
            register = register.replace(',','')
            if registers[register] % 2 == 0:
                numb = int(offset[1:]) 
                if offset.startswith('-'):
                    numb *= -1
                i += numb
            else:
                i += 1
        elif instruction.startswith('jio'):
            _, register,offset = instruction.split()
            register = register.replace(',','')
            if registers[register] == 1:
                numb = int(offset[1:]) 
                if offset.startswith('-'):
                    numb *= -1
                i += numb
            else:
                i += 1

    return  registers['b']

def part_2():
    
    puzzle_input = get_input(2015, 23)

    instructions = []
    for line in puzzle_input.splitlines():
        instructions.append(line)

    i=0
    registers = {'a': 1, 'b': 0}
    while i < len(instructions):

        instruction = instructions[i]

        if instruction.startswith('hlf'):
            register = instruction.split()[1]
            registers[register] /= 2
            i+=1
        elif instruction.startswith('tpl'):
            register = instruction.split()[1]
            registers[register] *= 3
            i+=1
        elif instruction.startswith('inc'):
            register = instruction.split()[1]
            registers[register] += 1
            i += 1
        elif instruction.startswith('jmp'):
            offset = instruction.split()[1]
            numb = int(offset[1:]) 
            if offset.startswith('-'):
                numb *= -1
            i += numb
        elif instruction.startswith('jie'):
            _, register,offset = instruction.split()
            register = register.replace(',','')
            if registers[register] % 2 == 0:
                numb = int(offset[1:]) 
                if offset.startswith('-'):
                    numb *= -1
                i += numb
            else:
                i += 1
        elif instruction.startswith('jio'):
            _, register,offset = instruction.split()
            register = register.replace(',','')
            if registers[register] == 1:
                numb = int(offset[1:]) 
                if offset.startswith('-'):
                    numb *= -1
                i += numb
            else:
                i += 1

    return registers['b']