#!/usr/bin/env python3
"""Generate MiniPack v0 from the current offline puzzle data.

Reads puzzle data and difficulty levels from the backend modules,
maps them to base puzzle indices, deduplicates, and builds an .opk binary.

Output: prints base64 of the MiniPack .opk to stdout (for embedding in JS).
Also writes minipack-v0.opk to disk for inspection.
"""
import base64
import json
import struct
import sys
import os

# Add backend root for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from octile_api import decode_puzzle, _decompose_puzzle_number, PUZZLE_COUNT
from octile_puzzle_data import PUZZLE_DATA

# Base-92 alphabet
P92 = '!"#$%&()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{|}~'

# Load difficulty levels
with open(os.path.join(os.path.dirname(__file__), '..', 'difficulty_levels.json')) as f:
    diff_data = json.load(f)
DIFF_LEVELS = diff_data['levels']  # list of 11378 values (1-4)

# Collect all puzzle numbers from the offline data
OFFLINE_PUZZLE_NUMS = [1,1035,2069,3104,4138,5172,6207,7241,8275,9310,10344,11379,12413,13447,14482,15516,16550,17585,18619,19653,20688,21722,22757,23791,24825,25860,26894,27928,28963,29997,31031,32066,33100,34135,35169,36203,37238,38272,39306,40341,41375,42409,43444,44478,45513,46547,47581,48616,49650,50684,51719,52753,53787,54822,55856,56891,57925,58959,59994,61028,62062,63097,64131,65165,66200,67234,68269,69303,70337,71372,72406,73440,74475,75509,76543,77578,78612,79647,80681,81715,82750,83784,84818,85853,86887,87921,88956,89990]

OFFLINE_LEVEL_NUMS = {
    'easy': [2,10,11,16,58,61,65,66,87,89,94,95,232,235,239,240,279,282,290,295,297,309],
    'medium': [99,558,668,671,1684,1878,2100,2123,2168,2232,2450,2462,2749,2920,2975,3054,4752,4766,4772,4985,5142,5197],
    'hard': [73,334,383,1017,2874,3206,3223,3971,4603,4905,4961,5013,5200,5463,6359,6674,7225,8359,9231,9332,10317,10513],
    'hell': [953,3531,6634,6838,6868,7090,8364,9389,9861,4346,5441,5699,6731,7900,10541,1540,1562,6861,7498,11256,6413,7576],
}

# Collect unique base indices
base_indices = set()

for pnum in OFFLINE_PUZZLE_NUMS:
    base, transform = _decompose_puzzle_number(pnum)
    base_indices.add(base)

for level, nums in OFFLINE_LEVEL_NUMS.items():
    for pnum in nums:
        base, transform = _decompose_puzzle_number(pnum)
        base_indices.add(base)

base_indices = sorted(base_indices)
print(f"Unique base indices: {len(base_indices)}", file=sys.stderr)
print(f"Extended coverage: {len(base_indices) * 8} puzzles", file=sys.stderr)

# Build the .opk binary
# Header: 80 bytes
magic = b'OPK1'
version = 0  # MiniPack v0
puzzle_count = len(base_indices)
schema_version = 1
flags = 0  # no ordering
reserved = 0
signature = b'\x00' * 64  # unsigned

header = struct.pack('<4sIIHBB', magic, version, puzzle_count, schema_version, flags, reserved)
header += signature
assert len(header) == 80

# Puzzle data: 3 bytes per puzzle (raw base-92 chars from PUZZLE_DATA)
puzzle_bytes = bytearray()
for base_idx in base_indices:
    o = base_idx * 3
    chunk = PUZZLE_DATA[o:o+3]
    puzzle_bytes.extend(chunk.encode('ascii'))

# Difficulty levels: 1 byte per puzzle
diff_bytes = bytearray()
for base_idx in base_indices:
    diff_bytes.append(DIFF_LEVELS[base_idx])

# Combine
opk = header + bytes(puzzle_bytes) + bytes(diff_bytes)

# Write to file
out_dir = os.path.join(os.path.dirname(__file__), '..')
out_path = os.path.join(out_dir, 'minipack-v0.opk')
with open(out_path, 'wb') as f:
    f.write(opk)
print(f"Written: {out_path} ({len(opk)} bytes)", file=sys.stderr)

# Also build a mapping file for verification
mapping_path = os.path.join(out_dir, 'minipack-v0-mapping.json')
with open(mapping_path, 'w') as f:
    json.dump({'base_indices': base_indices}, f)
print(f"Mapping: {mapping_path}", file=sys.stderr)

# Output base64 to stdout
b64 = base64.b64encode(opk).decode()
print(b64)
