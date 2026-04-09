#!/usr/bin/env python3
"""Generate Ed25519 keypair for pack signing.

Outputs:
  keys/pack-private.key  (base64, 64 bytes)
  keys/pack-public.key   (base64, 32 bytes)

The public key goes into config.json and 03a-pack.js.
The private key is used by generate-pack.py and stored as a GitHub Actions secret.
"""
import base64
import os
import sys

try:
    from nacl.signing import SigningKey
except ImportError:
    print("pip install pynacl", file=sys.stderr)
    sys.exit(1)

os.makedirs("keys", exist_ok=True)

sk = SigningKey.generate()
vk = sk.verify_key

priv_b64 = base64.b64encode(sk.encode() + vk.encode()).decode()
pub_b64 = base64.b64encode(vk.encode()).decode()

with open("keys/pack-private.key", "w") as f:
    f.write(priv_b64 + "\n")
with open("keys/pack-public.key", "w") as f:
    f.write(pub_b64 + "\n")

print("Private key: keys/pack-private.key")
print("Public key:  keys/pack-public.key")
print()
print("Public key (for config.json):")
print(f"  {pub_b64}")
