#!/usr/bin/env python3
"""Fix Chinese quotation marks by replacing the ENTIRE generator script with corner brackets 「」."""
import re

path = '/home/jennifer07/agent_eval/scripts/generate_whitepaper_v35.py'

with open(path, 'r', encoding='utf-8') as f:
    src = f.read()

cjk_char = re.compile(r'[一-鿿　-〿＀-￯]')

# We need to identify which " are Chinese quotation marks (adjacent to CJK text)
# vs which are Python string delimiters.
#
# Heuristic: a " in a Python string literal that is followed/preceded by CJK
# chars within the SAME string is a Chinese quotation mark.
#
# But the tricky part is the file is already corrupted — Python can't parse it.
#
# Strategy: work line-by-line. On each line:
# 1. Find all " positions
# 2. If a " has CJK on either side AND the line is not just a docstring,
#    replace it with 「 (if followed by CJK) or 」 (if preceded by CJK)
#
# We need to be careful about docstrings and Python string delimiters.

lines = src.split('\n')
fixed_lines = []
in_triple_quote = False

for i, line in enumerate(lines):
    stripped = line.strip()

    # Track if we're inside a triple-quoted string
    if stripped.startswith('"""') or stripped.startswith("'''"):
        in_triple_quote = not in_triple_quote

    # Check if this line is a docstring definition (like """...""" or ''...''')
    is_docstring_line = bool(re.match(r'^\s*"""', line) or re.match(r"^\s*'''", line))

    if is_docstring_line:
        fixed_lines.append(line)
        continue

    # Build new line char by char
    new_chars = []
    for j, ch in enumerate(line):
        if ch != '"':
            new_chars.append(ch)
            continue

        # Check context
        prev_char = line[j-1] if j > 0 else ''
        next_char = line[j+1] if j+1 < len(line) else ''

        prev_is_cjk = bool(cjk_char.match(prev_char))
        next_is_cjk = bool(cjk_char.match(next_char))

        if prev_is_cjk and next_is_cjk:
            # " sandwiched between two CJK chars — ambiguous, treat as closing + opening
            new_chars.append('」')
        elif prev_is_cjk:
            # CJK before " → this was a closing Chinese quote
            new_chars.append('」')
        elif next_is_cjk:
            # " before CJK → this was an opening Chinese quote
            new_chars.append('「')
        else:
            # Regular Python quote
            new_chars.append(ch)

    fixed_lines.append(''.join(new_chars))

new_src = '\n'.join(fixed_lines)

# Also handle the case where " appears within angle brackets or other CJK context
# e.g. the ""empty string"" pattern
# Additional fix: "word" patterns within Chinese text
# Pattern: 「word」(already fine after above fix)
# Pattern: 的"word"的 → where " is between ASCII and CJK

# Verify
try:
    compile(new_src, path, 'exec')
    print('Syntax OK!')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_src)
    print(f'Wrote fixed file ({len(new_src)} bytes)')
except SyntaxError as e:
    print(f'Still broken at line {e.lineno}: {e.msg}')
    err_lines = new_src.split('\n')
    for i in range(max(0, e.lineno-3), min(len(err_lines), e.lineno+2)):
        marker = '>>>' if i+1 == e.lineno else '   '
        print(f'{marker} {i+1}: {err_lines[i][:200]}')
