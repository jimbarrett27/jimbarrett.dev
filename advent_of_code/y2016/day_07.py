from advent_of_code.input import get_input



def part_1():
    

    def contains_abba(s):

        if len(s) < 4:
            return False
        
        for i in range(len(s)-4 +1):
            if s[i] == s[i+3] and s[i+1] == s[i+2] and s[i] != s[i+1]:
                return True

        return False

    puzzle_input = get_input(2016, 7)

    n_tls = 0
    for line in puzzle_input.splitlines():
        inside_brackets = []
        outside_brackets = []

        current_str = ''
        for c in line:
            if c == '[':
                outside_brackets.append(current_str)
                current_str = ''
            elif c == ']':
                inside_brackets.append(current_str)
                current_str = ''
            else:
                current_str += c
        
        outside_brackets.append(current_str)

        if any(map(contains_abba, outside_brackets)) and not any(map(contains_abba, inside_brackets)):
            n_tls += 1


    return n_tls

def part_2():

    def get_abas(s):
        if len(s) < 3:
            return []
        
        abas = []
        for i in range(len(s)-3 +1):
            if s[i] == s[i+2] and s[i] != s[i+1]:
                abas.append(s[i:i+3])
        
        return abas
    
    def contains_bab(s, aba):
        if len(s) < 3:
            False

        bab = aba[1] + aba [0] + aba[1]

        return bab in s

    
    puzzle_input = get_input(2016, 7)

    n_ssl = 0
    for line in puzzle_input.splitlines():
        inside_brackets = []
        outside_brackets = []

        current_str = ''
        for c in line:
            if c == '[':
                outside_brackets.append(current_str)
                current_str = ''
            elif c == ']':
                inside_brackets.append(current_str)
                current_str = ''
            else:
                current_str += c
        
        outside_brackets.append(current_str)

        abas = []
        for s in outside_brackets:
            abas += get_abas(s)

        found_one = False
        for s in inside_brackets:
            for aba in abas:
                if found_one:
                    continue
                if contains_bab(s, aba):
                    found_one = True
                    n_ssl += 1

    return n_ssl
