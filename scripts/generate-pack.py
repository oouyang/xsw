#!/usr/bin/env python3
"""Generate FullPack .opk from backend puzzle data + sign + release.json.

Usage:
  python scripts/generate-pack.py --key keys/pack-private.key [--version YYYYMMDD]

Reads:
  octile_puzzle_data.py    — PUZZLE_DATA (11378 puzzles × 3 base-92 chars)
  difficulty_levels.json   — levels[] (1-4), ordering{} (per-level base indices)

Outputs:
  packs/octile-pack-{version}.opk  — signed binary
  packs/release.json               — manifest with SHA-256 + Ed25519 signature
"""
import argparse
import base64
import hashlib
import json
import os
import struct
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from octile_puzzle_data import PUZZLE_DATA

try:
    from nacl.signing import SigningKey
except ImportError:
    print("pip install pynacl", file=sys.stderr)
    sys.exit(1)

parser = argparse.ArgumentParser()
parser.add_argument('--key', required=True, help='Path to Ed25519 private key (base64)')
parser.add_argument('--version', type=int, default=None, help='Pack version (YYYYMMDD)')
parser.add_argument('--out-dir', default='packs', help='Output directory')
args = parser.parse_args()

# Load key
with open(args.key) as f:
    key_b64 = f.read().strip()
key_bytes = base64.b64decode(key_b64)
sk = SigningKey(key_bytes[:32])

# Version
version = args.version or int(datetime.now(timezone.utc).strftime('%Y%m%d'))

# Load difficulty data
diff_path = os.path.join(os.path.dirname(__file__), '..', 'difficulty_levels.json')
with open(diff_path) as f:
    diff_data = json.load(f)

levels_list = diff_data['levels']      # [1,1,3,2,...] length 11378
ordering = diff_data['ordering']       # {"1": [...], "2": [...], "3": [...], "4": [...]}

puzzle_count = len(PUZZLE_DATA) // 3
assert puzzle_count == 11378
assert len(levels_list) == puzzle_count

# Build header
magic = b'OPK1'
schema_version = 1
flags = 1  # has_ordering
reserved = 0

header_no_sig = struct.pack('<4sIIHBB', magic, version, puzzle_count, schema_version, flags, reserved)
# Signature placeholder (filled after building data)
header = header_no_sig + b'\x00' * 64
assert len(header) == 80

# Puzzle data (raw base-92 ASCII)
puzzle_bytes = PUZZLE_DATA.encode('ascii')
assert len(puzzle_bytes) == puzzle_count * 3

# Difficulty levels
diff_bytes = bytes(levels_list)

# Ordering section
level_keys = ['1', '2', '3', '4']
level_counts = [len(ordering[k]) for k in level_keys]
ordering_header = struct.pack('<4H', *level_counts)

ordering_data = bytearray()
for k in level_keys:
    for base_idx in ordering[k]:
        ordering_data.extend(struct.pack('<H', base_idx))

# Compute ordering_id (SHA-256 of canonical ordering bytes)
ordering_bytes = ordering_header + bytes(ordering_data)
ordering_sha256 = hashlib.sha256(ordering_bytes).hexdigest()
ordering_id = ordering_sha256[:8]

# Combine data (everything after header)
data_payload = puzzle_bytes + diff_bytes + ordering_header + bytes(ordering_data)

# Sign bytes[80..EOF] (data_payload)
signed = sk.sign(data_payload)
signature = signed.signature
assert len(signature) == 64

# Rebuild header with signature
header = header_no_sig + signature
opk = header + data_payload

# Output
os.makedirs(args.out_dir, exist_ok=True)
opk_path = os.path.join(args.out_dir, f'octile-pack-{version}.opk')
with open(opk_path, 'wb') as f:
    f.write(opk)
print(f"Pack: {opk_path} ({len(opk)} bytes)")

# SHA-256
sha256 = hashlib.sha256(opk).hexdigest()

# Sign the release manifest
release_data = {
    'schemaVersion': 1,
    'updatedAt': datetime.now(timezone.utc).isoformat(),
    'current': {
        'version': version,
        'url': f'https://app.octile.eu.cc/packs/octile-pack-{version}.opk',
        'sha256': sha256,
        'size': len(opk),
        'mirrors': [],
        'minAppVersionCode': 23,
        'orderingId': ordering_id,
        'orderingVersion': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'orderingAuthority': 'pack',
    },
    'revoked': [],
}

# Sign the canonical JSON of 'current'
manifest_bytes = json.dumps(release_data['current'], sort_keys=True, separators=(',', ':')).encode()
manifest_signed = sk.sign(manifest_bytes)
release_data['signature'] = base64.b64encode(manifest_signed.signature).decode()

release_path = os.path.join(args.out_dir, 'release.json')
with open(release_path, 'w') as f:
    json.dump(release_data, f, indent=2)
    f.write('\n')
print(f"Release: {release_path}")
print(f"SHA-256: {sha256}")
print(f"Ordering ID: {ordering_id}")
print(f"Ordering SHA-256: {ordering_sha256}")
print(f"Public key: {base64.b64encode(sk.verify_key.encode()).decode()}")
