import re
from advent_of_code.input import get_input

def part_1():

    data = get_input(2016, 9)

    decompressed = ''
    ind = 0
    while True:
        c = data[ind]

        if c == '(':
            marker_text = ''
            while c != ')':
                ind += 1
                c = data[ind]
                marker_text += c
            
            n_chars, n_repeats = map(int, marker_text[:-1].split('x'))
            text_to_repeat = ''
            for _ in range(n_chars):
                ind += 1
                text_to_repeat += data[ind]
            
            decompressed += text_to_repeat * n_repeats


        else:
            decompressed += c    

        ind += 1

        if ind == len(data):
            break

    return len(decompressed)

def _decompressed_length(data):

    if '(' not in data:
        return len(data)

    decompressed_length = 0
    ind = 0
    while True:
        c = data[ind]

        if c == '(':
            marker_text = ''
            while c != ')':
                ind += 1
                c = data[ind]
                marker_text += c
            
            n_chars, n_repeats = map(int, marker_text[:-1].split('x'))
            
            text_to_decompress = ''
            for _ in range(n_chars):
                ind += 1
                text_to_decompress += data[ind]
            
            decompressed_length += _decompressed_length(text_to_decompress) * n_repeats


        else:
            decompressed_length += 1    

        ind += 1

        if ind == len(data):
            break

    return decompressed_length

def part_2():
    
    data = get_input(2016, 9)

    return _decompressed_length(data)