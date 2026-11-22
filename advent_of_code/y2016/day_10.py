from advent_of_code.input import get_input
from collections import defaultdict

def part_1():
    
    data = get_input(2016, 10)
#     data = """value 5 goes to bot 2
# bot 2 gives low to bot 1 and high to bot 0
# value 3 goes to bot 1
# bot 1 gives low to output 1 and high to bot 0
# bot 0 gives low to output 2 and high to output 0
# value 2 goes to bot 2"""


    loc_to_chips = defaultdict(list)
    bot_to_dests = {}
    
    for instruction in data.splitlines():
        if instruction.startswith('value'):
            s = instruction.split()
            loc_name = 'b' + s[-1]
            loc_to_chips[loc_name].append(int(s[1]))

        else:
            s = instruction.split()
            bot = 'b' + s[1]
            low_dest = 'b' + s[6] if s[5] == 'bot' else 'o' + s[6]
            high_dest = 'b' + s[-1] if s[-2] == 'bot' else 'o' + s[-1]

            bot_to_dests[bot] = (low_dest, high_dest)

    all_bots = [bot for bot in bot_to_dests.keys() if bot.startswith('b')]
    while any(len(loc_to_chips[bot]) == 2  for bot in all_bots):

        
        for bot in all_bots:

            chips = loc_to_chips[bot]

            if not bot.startswith('b'):
                continue
            
            if len(chips) == 2:
                low, high = sorted(chips)

                if low == 17 and high == 61:
                    return int(bot[1:])
            
                loc_to_chips[bot] = []
                loc_to_chips[bot_to_dests[bot][0]].append(low)
                loc_to_chips[bot_to_dests[bot][1]].append(high)


def part_2():
    data = get_input(2016, 10)
#     data = """value 5 goes to bot 2
# bot 2 gives low to bot 1 and high to bot 0
# value 3 goes to bot 1
# bot 1 gives low to output 1 and high to bot 0
# bot 0 gives low to output 2 and high to output 0
# value 2 goes to bot 2"""


    loc_to_chips = defaultdict(list)
    bot_to_dests = {}
    
    for instruction in data.splitlines():
        if instruction.startswith('value'):
            s = instruction.split()
            loc_name = 'b' + s[-1]
            loc_to_chips[loc_name].append(int(s[1]))

        else:
            s = instruction.split()
            bot = 'b' + s[1]
            low_dest = 'b' + s[6] if s[5] == 'bot' else 'o' + s[6]
            high_dest = 'b' + s[-1] if s[-2] == 'bot' else 'o' + s[-1]

            bot_to_dests[bot] = (low_dest, high_dest)

    all_bots = [bot for bot in bot_to_dests.keys() if bot.startswith('b')]
    while any(len(loc_to_chips[bot]) == 2  for bot in all_bots):

        
        for bot in all_bots:

            chips = loc_to_chips[bot]

            if not bot.startswith('b'):
                continue
            
            if len(chips) == 2:
                low, high = sorted(chips)
            
                loc_to_chips[bot] = []
                loc_to_chips[bot_to_dests[bot][0]].append(low)
                loc_to_chips[bot_to_dests[bot][1]].append(high)

    return int(loc_to_chips['o0'][0])*int(loc_to_chips['o1'][0])*int(loc_to_chips['o2'][0])