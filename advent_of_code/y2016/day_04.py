from advent_of_code.input import get_input
from collections import Counter, defaultdict

test_input = """aaaaa-bbb-z-y-x-123[abxyz]
a-b-c-d-e-f-g-h-987[abcde]
not-a-real-room-404[oarel]
totally-real-room-200[decoy]
"""

def part_1():
    
    puzzle_input = get_input(2016, 4)

    sector_sum = 0
    for line in puzzle_input.splitlines():
        name_and_sector, checksum = line[:-1].split('[')
        
        sector = name_and_sector[-3:]
        name = name_and_sector[:-4]

        counts = Counter(name.replace('-', ''))

        count_to_letters = defaultdict(list)
        for l, c in counts.most_common():
            count_to_letters[c].append(l)

        computed_checksum = ''
        for c, ls in sorted(count_to_letters.items(), key=lambda x: x[0], reverse=True):
            for l in sorted(ls):
                if len(computed_checksum) == 5:
                    break
                computed_checksum += l
                        
        if computed_checksum == checksum:
            sector_sum += int(sector)

    return sector_sum
        

def part_2():
    
    puzzle_input = get_input(2016, 4)

    alphabet = list('abcdefghijklmnopqrstuvwxyz')

    sector_sum = 0
    for line in puzzle_input.splitlines():
        name_and_sector, checksum = line[:-1].split('[')
        
        sector = name_and_sector[-3:]
        name = name_and_sector[:-4]

        new_words = []
        for word in name.split('-'):
            new_word = []
            for letter in word:
                new_word.append(alphabet[(alphabet.index(letter) + int(sector)) % 26])
            new_words.append(''.join(new_word))

        if ' '.join(new_words) == 'northpole object storage':
            return sector
