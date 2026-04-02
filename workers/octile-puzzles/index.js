import { PUZZLE_DATA, PUZZLE_COUNT, TOTAL_PUZZLE_COUNT } from "./puzzle-data.js";
import { LEVELS, ATTEMPTS, DIFFICULTY_LABELS } from "./difficulty-data.js";

// Base-92 alphabet: printable ASCII 33-126, excluding ' (39) and \ (92)
const P92 = '!"#$%&()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{|}~';
const P92_MAP = Object.fromEntries([...P92].map((c, i) => [c, i]));

// --- Puzzle decoding ---

function decodePuzzle(index) {
  const o = index * 3;
  const n = P92_MAP[PUZZLE_DATA[o]] + P92_MAP[PUZZLE_DATA[o + 1]] * 92 + P92_MAP[PUZZLE_DATA[o + 2]] * 92 * 92;

  const g3Idx = n % 96;
  const g2Idx = Math.floor(n / 96) % 112;
  const g1 = Math.floor(n / 10752);

  let g2a, g2b;
  if (g2Idx < 56) {
    const r = Math.floor(g2Idx / 7);
    const c = g2Idx % 7;
    g2a = r * 8 + c;
    g2b = g2a + 1;
  } else {
    const i = g2Idx - 56;
    const r = Math.floor(i / 8);
    const c = i % 8;
    g2a = r * 8 + c;
    g2b = g2a + 8;
  }

  let g3a, g3b, g3c;
  if (g3Idx < 48) {
    const r = Math.floor(g3Idx / 6);
    const c = g3Idx % 6;
    g3a = r * 8 + c;
    g3b = g3a + 1;
    g3c = g3a + 2;
  } else {
    const i = g3Idx - 48;
    const r = Math.floor(i / 8);
    const c = i % 8;
    g3a = r * 8 + c;
    g3b = g3a + 8;
    g3c = g3a + 16;
  }

  return [g1, g2a, g2b, g3a, g3b, g3c];
}

function transformCell(cell, transform) {
  let r = Math.floor(cell / 8);
  let c = cell % 8;
  switch (transform) {
    case 1: [r, c] = [c, 7 - r]; break;
    case 2: [r, c] = [7 - r, 7 - c]; break;
    case 3: [r, c] = [7 - c, r]; break;
    case 4: [r, c] = [r, 7 - c]; break;
    case 5: [r, c] = [7 - c, 7 - r]; break;
    case 6: [r, c] = [7 - r, c]; break;
    case 7: [r, c] = [c, r]; break;
  }
  return r * 8 + c;
}

function decomposePuzzleNumber(puzzleNumber) {
  const idx = puzzleNumber - 1;
  return [idx % PUZZLE_COUNT, Math.floor(idx / PUZZLE_COUNT)];
}

function decodePuzzleExtended(puzzleNumber) {
  const [base, transform] = decomposePuzzleNumber(puzzleNumber);
  const cells = decodePuzzle(base);
  if (transform === 0) return cells;
  return cells.map((c) => transformCell(c, transform));
}

function getPuzzleDifficulty(puzzleNumber) {
  const [base] = decomposePuzzleNumber(puzzleNumber);
  return LEVELS[base];
}

// --- Level bases (sorted by attempts ascending) ---

let _levelBases = null;

function getLevelBases() {
  if (_levelBases) return _levelBases;
  _levelBases = { 1: [], 2: [], 3: [], 4: [] };
  const items = { 1: [], 2: [], 3: [], 4: [] };
  for (let i = 0; i < LEVELS.length; i++) {
    items[LEVELS[i]].push([ATTEMPTS[i], i]);
  }
  for (const level of [1, 2, 3, 4]) {
    items[level].sort((a, b) => a[0] - b[0]);
    _levelBases[level] = items[level].map(([, idx]) => idx);
  }
  return _levelBases;
}

// --- Response helpers ---

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
  });
}

function jsonError(detail, status) {
  return json({ detail }, status);
}

// --- Route handlers ---

function handlePuzzle(number) {
  if (number < 1 || number > TOTAL_PUZZLE_COUNT) {
    return jsonError(`puzzle_number must be 1–${TOTAL_PUZZLE_COUNT}`, 400);
  }
  const [base, transform] = decomposePuzzleNumber(number);
  const cells = decodePuzzleExtended(number);
  const level = getPuzzleDifficulty(number);
  return json({
    puzzle_number: number,
    base_puzzle: base + 1,
    transform,
    cells,
    difficulty: level,
    difficulty_label: DIFFICULTY_LABELS[level],
  });
}

function handleLevels(transforms) {
  const t = Math.max(1, Math.min(8, transforms));
  const bases = getLevelBases();
  const result = {};
  for (const [levelNum, levelName] of Object.entries(DIFFICULTY_LABELS)) {
    result[levelName] = (bases[levelNum] || []).length * t;
  }
  return json(result);
}

function handleLevelPuzzle(level, slot, transforms) {
  const levelNum = Object.entries(DIFFICULTY_LABELS).find(([, v]) => v === level)?.[0];
  if (!levelNum) {
    return jsonError("level must be easy, medium, hard, or hell", 400);
  }

  const t = Math.max(1, Math.min(8, transforms));
  const bases = getLevelBases()[levelNum] || [];
  const numBases = bases.length;
  const total = numBases * t;

  if (slot < 1 || slot > total) {
    return jsonError(`slot must be 1–${total}`, 400);
  }

  const slot0 = slot - 1;
  const basePos = slot0 % numBases;
  const transform = Math.floor(slot0 / numBases);
  const baseIdx = bases[basePos];
  const puzzleNumber = transform * PUZZLE_COUNT + baseIdx + 1;
  const cells = decodePuzzleExtended(puzzleNumber);

  return json({ puzzle_number: puzzleNumber, level, slot, total, cells });
}

// --- Router ---

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    // GET /puzzle/:number
    let match = path.match(/^\/puzzle\/(\d+)$/);
    if (match) return handlePuzzle(parseInt(match[1], 10));

    // GET /levels?transforms=8
    if (path === "/levels") {
      const t = parseInt(url.searchParams.get("transforms") || "8", 10);
      return handleLevels(t);
    }

    // GET /level/:level/puzzle/:slot?transforms=8
    match = path.match(/^\/level\/([a-z]+)\/puzzle\/(\d+)$/);
    if (match) {
      const t = parseInt(url.searchParams.get("transforms") || "8", 10);
      return handleLevelPuzzle(match[1], parseInt(match[2], 10), t);
    }

    return jsonError("Not Found", 404);
  },
};
