# PuzzlePack System

## Overview

PuzzlePack is Octile's content distribution and trust model for puzzles.

Instead of fetching puzzle data from a backend API at runtime, Octile ships and downloads **signed, immutable puzzle packs** that contain the complete, decoded puzzle universe and its ordering.
This removes runtime network dependency, eliminates backend authority over puzzle semantics, and allows Octile to operate fully offline and in untrusted network environments.

PuzzlePack is not an optimization layer. It is the **source of truth** for puzzle content.

---

## Motivation

### Problems with Runtime Puzzle APIs

Prior to PuzzlePack, Octile fetched puzzle data per puzzle via a backend API (through a Worker proxy). This had several fundamental issues:

- Puzzle availability depended on network reachability
- Backend responses were authoritative at runtime
- CDN / proxy / regional environments (e.g. China) could degrade gameplay correctness
- Offline support was limited to a small, special-cased fallback set
- Puzzle semantics changed implicitly with backend updates

For a puzzle-first game, this is unacceptable.

### Design Goal

> Puzzle correctness must **not** depend on a live backend.

The system must ensure that:
- Puzzle data is verifiable
- Content can be mirrored or cached untrusted
- Runtime gameplay does not require network access
- Offline gameplay is complete, not degraded

PuzzlePack is the solution to this.

---

## Core Philosophy

### 1. Puzzle Truth Is Published, Not Served

PuzzlePack turns puzzle data from a *service output* into a *published artifact*.

- The backend acts as a **publisher**, not a runtime authority
- Puzzle semantics are frozen at pack generation time
- The client verifies and consumes signed content only

At runtime, the client never asks:
> "What is the puzzle?"

Instead, it only asks:
> "Do I already have a verified puzzle pack?"

### 2. Distribution Is Untrusted, Content Is Not

PuzzlePack explicitly assumes:
- CDNs can be hostile
- Mirrors can be altered
- Servers can lie or disappear

This is safe because:
- Every pack is signed with Ed25519
- The client verifies signatures and hashes before use
- Invalid or tampered content is rejected

The client trusts **signatures**, not servers.

### 3. Runtime Network Access Is Optional

With PuzzlePack:

- A full puzzle set is available offline
- Network connectivity is a convenience, not a requirement
- API calls are fallback mechanisms, not core dependencies

Gameplay correctness is preserved even with:
- No network
- Blocked regions
- Failed updates
- Stale mirrors

---

## Architecture

### Control Plane (Trusted)

Responsible for:
- Generating puzzle packs from `octile_puzzle_data.py` + `difficulty_levels.json`
- Defining puzzle ordering and difficulty
- Signing pack payloads with Ed25519
- Producing the signed release manifest

**Private signing keys never leave this plane.**

### Distribution Plane (Untrusted)

Responsible only for:
- Hosting static `.opk` files and `release.json`
- Mirroring content to any CDN or region

This plane is not trusted for correctness.

### Client

Responsible for:
- Verifying signatures and hashes
- Storing packs locally (IndexedDB)
- Serving puzzle data from verified packs
- Falling back safely when verification fails

```
Backend (xsw)                        Client (octile)
─────────────                        ───────────────
octile_puzzle_data.py  ──┐
                         ├─→  generate-pack.py  ──→  packs/*.opk + release.json
difficulty_levels.json ──┘                              │
                                                        │  (deployed to CDN)
                                                        ▼
                                              client downloads .opk
                                              verifies SHA-256 + Ed25519
                                              stores in IndexedDB
                                              ▼
                                    PackReader (src/js/03a-pack.js)
                                              │
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                        getPuzzleCells   levelSlotToPuzzle   getLevelTotal
                        (replaces API)   (replaces API)      (replaces API)
```

---

## PuzzlePack Format (.opk)

PuzzlePack uses a custom binary format optimized for:

- Minimal size (~68 KB for 11,378 puzzles)
- Deterministic parsing
- Zero runtime dependencies
- Easy verification

Key characteristics:
- Single flat binary file
- Fixed header + signed payload
- No embedded JSON or ZIP layers
- Entire pack small enough for silent download (~35 KB gzipped)

PuzzlePack does **not** contain generated variants.
Only base puzzles are stored; D4 transforms are applied client-side.

All integers are little-endian.

### Header (80 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 4 | magic | `OPK1` (ASCII) |
| 4 | 4 | version | YYYYMMDD integer (e.g. 20260409) |
| 8 | 4 | puzzleCount | Number of base puzzles (11378) |
| 12 | 2 | schema | Schema version (1) |
| 14 | 1 | flags | Bit 0: hasOrdering |
| 15 | 1 | reserved | 0 |
| 16 | 64 | signature | Ed25519 signature over bytes[80..EOF] |

### Data Payload (bytes 80+)

| Section | Size | Description |
|---------|------|-------------|
| puzzleData | puzzleCount × 3 | Base-92 encoded puzzle cells (3 chars each) |
| diffLevels | puzzleCount × 1 | Difficulty level per puzzle (1=easy..4=hell) |
| ordering (if flag set) | 8 + Σ(counts×2) | Level ordering for slot-to-puzzle mapping |

### Ordering Section

| Offset | Size | Field |
|--------|------|-------|
| 0 | 8 | 4 × uint16: level counts [easy, medium, hard, hell] |
| 8 | variable | Concatenated uint16 arrays of base indices per level |

Each level's array lists base puzzle indices in display order (themed chapters + difficulty curves; see `puzzle-ordering-v2.md`).

---

## Puzzle Encoding

Each puzzle is 3 bytes of base-92 ASCII. The base-92 alphabet is printable ASCII 33–126 excluding `'` (39) and `\` (92).

Decoding a 3-char triplet `(c0, c1, c2)`:

```
n = p92[c0] + p92[c1] × 92 + p92[c2] × 92²

g3_idx = n % 96          → grey-3 piece position
g2_idx = (n / 96) % 112  → grey-2 piece position
g1     = n / 10752        → grey-1 piece position (single cell 0–63)
```

Grey-2 decoding (g2_idx → two adjacent cells):
- 0–55: horizontal pair → row = idx/7, col = idx%7, cells = (r×8+c, r×8+c+1)
- 56–111: vertical pair → idx' = idx-56, row = idx'/8, col = idx'%8, cells = (r×8+c, r×8+c+8)

Grey-3 decoding (g3_idx → three adjacent cells):
- 0–47: horizontal triple → row = idx/6, col = idx%6, cells = (r×8+c, r×8+c+1, r×8+c+2)
- 48–95: vertical triple → idx' = idx-48, row = idx'/8, col = idx'%8, cells = (r×8+c, r×8+c+8, r×8+c+16)

Result: 6 cell indices `[g1, g2a, g2b, g3a, g3b, g3c]` on the 8×8 board.

---

## Extended Puzzle Numbers

The 11,378 base puzzles are extended to 91,024 via D4 symmetry transforms:

```
puzzleNumber = transform × 11378 + baseIndex + 1    (1-based)
```

- transform 0: identity
- transform 1–7: rotations and reflections on the 8×8 board

Decomposition: `baseIndex = (puzzleNumber - 1) % 11378`, `transform = (puzzleNumber - 1) / 11378`

---

## Level Slot Mapping

With ordering, each level has `numBases` base puzzles × 8 transforms = total slots.

```
slot (1-based) → basePos = (slot-1) % numBases
                 transform = (slot-1) / numBases
                 puzzleNumber = transform × 11378 + bases[basePos] + 1
```

This interleaving ensures players see all base positions before encountering transforms.

---

## MiniPack (Built-in Pack)

Every Octile build ships with a **built-in MiniPack** (99 base puzzles = 792 extended). Embedded as base64 in `03a-pack.js`.

- Verified using the same PackReader logic
- Treated as a regular PuzzlePack (no special-cased offline fallback)
- Guarantees first-run and offline play without network
- No ordering (flags = 0) — cannot map level/slot, only direct puzzle numbers
- No signature (unsigned) — trusted by virtue of being compiled into the app
- Base index mapping stored separately as `MINIPACK_BASE_INDICES` array

The MiniPack establishes a **root of trust** even when no network is available.

---

## Security

### Ed25519 Signing

- **Pack binary**: signature in header covers all bytes after offset 80
- **Release manifest**: signature covers canonical JSON of `current` object (sorted keys, no whitespace)
- Uses `tweetnacl` (nacl-fast.min.js) for client-side verification
- Key generation: `scripts/generate-keypair.py` (PyNaCl)

### SHA-256 Integrity

Downloaded packs are verified against the SHA-256 hash in `release.json` using Web Crypto API before parsing.

### Verification Chain

```
release.json (signed manifest)
  → SHA-256 check on .opk bytes
  → Ed25519 signature check on .opk data payload
  → Pack activated in client
```

If any check fails, the pack is silently discarded and the client falls back to API.

---

## Release Manifest

The release manifest (`release.json`) is a signed advisory document that tells the client:

- Which pack version is current
- Where packs can be downloaded
- Minimum compatible app version
- Optional mirrors
- Revocations (if any)

Important:
- The release manifest does **not override puzzle truth**
- The `.opk` payload signature is authoritative
- The client may ignore the manifest entirely and still function

```json
{
  "schemaVersion": 1,
  "updatedAt": "2026-04-09T06:04:19.267022+00:00",
  "current": {
    "version": 20260409,
    "url": "https://app.octile.eu.cc/packs/octile-pack-20260409.opk",
    "sha256": "d337...",
    "size": 68356,
    "mirrors": [],
    "minAppVersionCode": 23
  },
  "revoked": [],
  "signature": "<base64 Ed25519 signature of canonical current JSON>"
}
```

---

## Client Behavior

### Startup Sequence

1. MiniPack is decoded from embedded base64 (synchronous, immediate)
2. `_initPacks()` loads FullPack from IndexedDB (async, non-blocking)
3. `checkPackUpdate()` fetches `release.json` in background
4. If newer version available: download, verify, store, activate

Gameplay never blocks on pack availability.

### Fallback Order

For `getPuzzleCells(puzzleNumber)`:

1. **FullPack** — instant, offline
2. **API** — `GET /puzzle/{number}`, 3s timeout
3. **MiniPack** — if puzzle's base index is in the 99-puzzle set
4. **Random MiniPack puzzle** — last resort, substitutes a random available puzzle

For `fetchLevelPuzzle(level, slot)`:

1. **FullPack** — uses ordering for slot-to-puzzle mapping
2. **API** — `GET /level/{level}/puzzle/{slot}`
3. **Error** — MiniPack has no ordering, cannot map slots

---

## Configuration

`config.json`:

```json
{
  "pack": {
    "releaseUrl": "https://app.octile.eu.cc/packs/release.json",
    "publicKey": "<base64 Ed25519 public key>"
  }
}
```

---

## Backend Compatibility

The pack system is purely additive. The backend API endpoints (`/puzzle/{n}`, `/level/{level}/puzzle/{slot}`, `/levels`) remain unchanged and serve as the online fallback. The pack's puzzle encoding and ordering are derived from the same source data (`octile_puzzle_data.py`, `difficulty_levels.json`), ensuring consistency.

| Backend (`octile_api.py`) | Pack equivalent |
|---------------------------|-----------------|
| `decode_puzzle(base)` | `PackReader.decodePuzzle(packIndex)` |
| `decode_puzzle_extended(num)` | `PackReader.getPuzzleCells(puzzleNumber)` |
| `level_slot_to_puzzle(level, slot)` | `PackReader.levelSlotToPuzzle(level, slot)` |
| `get_level_total(level)` | `PackReader.getLevelTotal(level)` |
| `_decompose_puzzle_number(num)` | `PackReader.decompose(puzzleNumber)` |

---

## Scripts

| Script | Input | Output |
|--------|-------|--------|
| `scripts/generate-keypair.py` | — | `keys/pack-private.key`, `keys/pack-public.key` |
| `scripts/generate-minipack.py` | `octile_puzzle_data.py`, `difficulty_levels.json` | `minipack-v0.opk` + base64 to stdout |
| `scripts/generate-pack.py` | `octile_puzzle_data.py`, `difficulty_levels.json`, private key | `packs/*.opk`, `packs/release.json` |

### Generating a New Pack

```bash
# First time: generate keypair
python scripts/generate-keypair.py

# Generate full pack (requires xsw repo alongside octile)
python scripts/generate-pack.py --key keys/pack-private.key

# Output: packs/octile-pack-YYYYMMDD.opk + packs/release.json
```

### Regenerating MiniPack

```bash
python scripts/generate-minipack.py > /dev/null
# Copy base64 output and MINIPACK_BASE_INDICES into src/js/03a-pack.js
```

---

## Deployment

1. Run `generate-pack.py` to produce `.opk` + `release.json`
2. Copy both to `dist/web/packs/` (or deploy to CDN)
3. Clients auto-download on next startup via `checkPackUpdate()`

The `.opk` files and `release.json` are static — they can be served from any CDN or static hosting alongside the web app.

---

## Non-Goals

PuzzlePack intentionally does **not** attempt to:

- Prevent reverse engineering
- Obfuscate puzzle logic
- Block copying or redistribution
- Provide DRM
- Predict player behavior

The goal is **correctness, not secrecy**.

---

## Future Evolution

Possible future optimizations (not required for MVP):

- Transport-layer segmentation (e.g. by difficulty)
- Preloading based on progression signals
- Multiple signing keys per channel
- Differential updates

These optimizations **must never split puzzle truth** or weaken the trust model.

---

## Ordering Consistency Policy

- **Identity**: puzzle identity is always `puzzle_number` (baseIndex / puzzleNumber), never `(level, slot)`.
- **Slot**: slot is a UI navigation coordinate only; it is not stored and not transmitted to the backend.
- **Authority**: PuzzlePack is the sole authority for ordering semantics. Backend ordering is diagnostic only.
- **Detection**: `ordering_id` is a content-derived fingerprint (32-bit, first 8 hex of SHA-256) computed from canonical ordering bytes, enabling mismatch detection. It is not a security boundary; pack signature remains the security boundary.
- **CI Gate**: pack generation and backend must compute the same `ordering_id` from the same ordering source. If they differ, the release is invalid.
- **Canonical bytes**: `[4×u16 LE counts][easy bases u16 LE][medium bases u16 LE][hard bases u16 LE][hell bases u16 LE]` — the ordering section of the .opk, no more, no less.

---

## Summary

PuzzlePack makes Octile:

- Fully offline-capable
- Resilient to unreliable or hostile networks
- Independent from runtime backend authority
- Architecturally aligned with a puzzle-first philosophy

PuzzlePack is not a download feature.
It is the foundation of puzzle correctness.
