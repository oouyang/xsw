# Bus Bundle Generation - Rate Limit Management

## Overview

This guide explains how to generate bus data bundles while respecting TDX API rate limits.

## Rate Limit Source

**IMPORTANT**: The rate limits are from **TDX API**, NOT your Cloudflare Worker!

Your proxy worker at `tdx-proxy.owen-ouyang.workers.dev`:
- ✅ Has NO explicit rate limiting
- ✅ Implements smart caching (24h for static data)
- ✅ Can handle 100K requests/day (Cloudflare limit)
- ✅ Just passes through TDX's rate limits

The 429 errors come from TDX itself:

| Tier | Daily Limit | Per Minute | Cost |
|------|------------|------------|------|
| Free | 2,000 | 20 | Free |
| Basic | 20,000 | 100 | ~$500 TWD/month |
| Premium | 200,000 | 500 | ~$5000 TWD/month |

## Bundle Generation Requirements

### API Requests Per Route
Each route requires **3 API calls**:
1. Get stops (`/Bus/Stop/City/{City}/{RouteID}`)
2. Get stop sequences (`/Bus/StopOfRoute/City/{City}/{RouteID}`)
3. Get route shapes (`/Bus/Shape/City/{City}/{RouteID}`)

### Example Calculations

**Taoyuan (50 routes)**:
- Requests: 1 (route list) + (50 × 3) = 151 requests
- Time at 1.0s delay: ~2.5 minutes
- ✅ Fits in Free tier (2,000/day)

**Taoyuan (400 routes, full)**:
- Requests: 1 + (400 × 3) = 1,201 requests
- Time at 1.0s delay: ~20 minutes
- ✅ Fits in Free tier

**All 6 major cities (50 routes each)**:
- Requests: 6 + (6 × 50 × 3) = 906 requests
- Time at 1.0s delay: ~15 minutes
- ✅ Fits in Free tier

**All 6 major cities (full, ~1700 routes)**:
- Requests: 6 + (1700 × 3) = 5,106 requests
- Time at 1.0s delay: ~85 minutes
- ⚠️ Needs Basic tier (exceeds 2,000)

## Usage

### Quick Start

```bash
# Generate Taoyuan bundle (50 routes, safe for free tier)
python3 scripts/generate_bus_bundle.py --city Taoyuan

# Check how many requests will be made
python3 scripts/generate_bus_bundle.py --city Taoyuan --check-limits

# Generate with all routes (may hit rate limit)
python3 scripts/generate_bus_bundle.py --city Taoyuan --max-routes 400
```

### Command Line Options

```bash
# Basic usage
python3 scripts/generate_bus_bundle.py [OPTIONS]

Options:
  --city CITY             City to include (can repeat for multiple)
  --all                   Include all 22 Taiwan cities
  --max-routes N          Max routes per city (default: 50)
  --delay SECONDS         Delay between requests (default: 1.0)
  --output PATH           Output file (default: static/bus/bundle.json.gz)
  --check-limits          Estimate API usage without generating

Examples:
  # Single city with rate limit check
  python3 scripts/generate_bus_bundle.py --city Taoyuan --check-limits

  # Multiple cities with custom delay
  python3 scripts/generate_bus_bundle.py \
    --city Taoyuan --city Taipei --city Kaohsiung \
    --delay 0.6 \
    --max-routes 100

  # All cities (requires Basic tier)
  python3 scripts/generate_bus_bundle.py --all --delay 0.6
```

### Rate Limit Strategies

#### Free Tier (20 req/min, 2,000 req/day)

```bash
# Safe: 50 routes per city, 1.0s delay
python3 scripts/generate_bus_bundle.py --city Taoyuan --max-routes 50 --delay 1.0
# Time: ~2.5 min, Requests: ~151

# Max: Full Taoyuan
python3 scripts/generate_bus_bundle.py --city Taoyuan --max-routes 400 --delay 3.0
# Time: ~60 min, Requests: ~1,201

# Can do multiple small cities per day
python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --city Keelung \
  --max-routes 50 \
  --delay 1.0
# Time: ~5 min, Requests: ~302
```

#### Basic Tier (100 req/min, 20,000 req/day)

```bash
# All 6 major cities, full routes
python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --city Taipei --city NewTaipei \
  --city Taichung --city Tainan --city Kaohsiung \
  --max-routes 400 \
  --delay 0.6

# Time: ~85 min, Requests: ~5,106

# Or all 22 cities with 50 routes each
python3 scripts/generate_bus_bundle.py --all --max-routes 50 --delay 0.6
# Time: ~25 min, Requests: ~3,322
```

#### Premium Tier (500 req/min, 200,000 req/day)

```bash
# All 22 cities, all routes (expensive but fast)
python3 scripts/generate_bus_bundle.py --all --max-routes 1000 --delay 0.12
# Time: ~132 min, Requests: ~66,022
```

## Environment Configuration

Add to your `.env`:

```bash
# Rate limiting (default: 1.0 second between requests)
TDX_RATE_LIMIT_DELAY=1.0

# Max routes per city (default: 50)
BUS_BUNDLE_MAX_ROUTES_PER_CITY=50
```

## Optimization Tips

### 1. Use Incremental Generation

Generate popular routes first, then expand:

```bash
# Day 1: Major cities, limited routes
python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --city Taipei \
  --max-routes 30

# Day 2: Add more cities
python3 scripts/generate_bus_bundle.py \
  --city Taichung --city Kaohsiung \
  --max-routes 30

# Merge bundles later
```

### 2. Leverage Caching

The Cloudflare Worker caches static data for 24 hours:
- First run: Hits TDX rate limits
- Subsequent runs within 24h: Served from cache (no TDX hits!)

This means you can run the script multiple times per day for testing without consuming TDX quota.

### 3. Run During Off-Peak Hours

Schedule cron job during low traffic:

```bash
# Setup weekly generation (Sunday 2 AM)
./scripts/setup_bundle_cron.sh

# Cron entry added:
0 2 * * 0 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py --city Taoyuan
```

### 4. Monitor Request Count

The script now logs total API requests:

```
2026-03-03 14:32:00,000 - INFO - Bundle generated successfully!
2026-03-03 14:32:00,000 - INFO -   Version: 2026-03-03-1432
2026-03-03 14:32:00,000 - INFO -   Cities: 1
2026-03-03 14:32:00,000 - INFO -   Routes: 50
2026-03-03 14:32:00,000 - INFO -   Stops: 1234
2026-03-03 14:32:00,000 - INFO -   Total API requests: 151
```

## Troubleshooting

### Getting 429 Errors

```
HTTPError: 429 Too Many Requests
```

**Solution**: Increase delay or reduce max routes:

```bash
# Slower but safer
python3 scripts/generate_bus_bundle.py --city Taoyuan --delay 3.0 --max-routes 30
```

### Generation Takes Too Long

**Solution**: Use Basic tier or generate fewer routes:

```bash
# Quick test bundle (10 routes, 30 seconds)
python3 scripts/generate_bus_bundle.py --city Taoyuan --max-routes 10 --delay 1.0

# Or upgrade to Basic tier and use --delay 0.6
```

### Want Full Coverage

**Options**:
1. Upgrade to Basic tier ($500 TWD/month)
2. Generate incrementally over multiple days (Free tier)
3. Use your existing proxy's cache for repeated runs

## Cost Analysis

### Free Tier Strategy
- Generate 1 city/day with full routes
- Monthly cost: **$0**
- Total coverage: 30 cities/month (enough for all Taiwan)

### Basic Tier Strategy
- Generate all major cities daily
- Monthly cost: **~$500 TWD** (~$16 USD)
- Total coverage: Unlimited daily refreshes

### Recommended Approach

**For production**: Start with Free tier + smart caching
1. Generate Taoyuan bundle (your primary city)
2. Use 24h edge cache on Cloudflare
3. Real-time APIs still work (not cached)
4. Upgrade to Basic only if you need daily full refreshes

## Summary

| Scenario | Tier | Time | Cost |
|----------|------|------|------|
| Taoyuan (50 routes) | Free | 2.5 min | $0 |
| Taoyuan (full 400) | Free | 20 min | $0 |
| 6 cities (50 each) | Free | 15 min | $0 |
| 6 cities (full) | Basic | 85 min | $16/mo |
| All Taiwan | Basic | 132 min | $16/mo |

**The rate limits are from TDX, not your worker. Your proxy is working perfectly!** ✅
