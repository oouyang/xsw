# XSW Log Analysis — Pending TODOs

All items from the `xsw_app.log` analysis completed or verified. Remaining actionable items:

## Low Priority

### 1. Integrate `bot_protection.py` (dead code)
- **File**: `~/Documents/ws/xsw/bot_protection.py` (420 lines, never imported)
- **Status**: DDoSProtection class exists, comprehensive (IP reputation, path analysis, auto-block), but zero imports in the running app
- **Action**: Either wire it in as middleware in `main_optimized.py`, or delete it
- **Relevance**: Probes like `/.env`, `/.git/config` currently return 404 by FastAPI routing, which is fine — but integration would provide auto-blocking for repeat offenders

### 2. Fix missing timestamps in log output
- **File**: `~/Documents/ws/xsw/main_optimized.py`, lines 109-160 (LOGGING_CONFIG)
- **Status**: `dictConfig` defines `%(asctime)s` with ISO8601 `datefmt` for both `default` and `access` formatters, but actual log lines show timestamps as blank (lines start with ` - INFO - ...`)
- **Action**: Investigate why `%(asctime)s` resolves to empty string. Possible causes: `dictConfig` not applying to root logger correctly, or `logging.basicConfig` in `main.py` overriding it

### 3. Clean up `bot_protection.py`
- **File**: `~/Documents/ws/xsw/bot_protection.py`
- **Status**: 420-line file that is dead code since creation
- **Action**: Either integrate or remove to reduce maintenance burden

## Completed Items (no action needed)

| Item | Finding |
|---|---|
| India traffic (82%) | Legitimate single player `32901dcd`, confirmed normal |
| tpwa_* game IDs | **FIXED** — added 10 games (bus, etf, rail, thsr, mrt, oil, earthquake, youbike, weather, stock) to `game_contracts.json` + validators dict + `calc_game_rewards()` |
| Sync 401s (64×) | By design — both endpoints require JWT auth. Not a bug. |
| 429 rate limits (15×) | From score submission limiter (1/3s/game/user), not rate_limiter.py. 15 hits in 16K lines = fine. |
| player_uuid truncation | By design (privacy, `[:8] + '…'`). Binary chars = UTF-8 ellipsis in Latin-1 terminal. Not a bug. |
| Feedback from 167.103.160.83 | ✅ Sent successfully to octileapp@googlegroups.com with screenshot attachment. Real TW player. |
| rate_limiter.py | Working as designed (progressive delays in middleware, no 429s returned) |
