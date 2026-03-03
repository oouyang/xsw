# Bus Bundle Generation - Quick Start Guide

## 🚀 TL;DR - Get Started in 3 Steps

```bash
# 1. Setup multi-day schedule (FREE tier, no rate limits)
./scripts/setup_multiday_cron.sh

# 2. Let it run for a week (automated)
# Monday-Saturday: Generate 1 city each (2:00 AM)
# Sunday: Merge all cities (3:00 AM)

# 3. Done! Your app now has 6 cities with zero rate limit issues
```

## 📊 Quick Comparison

| Strategy | Time to First Bundle | API Usage/Day | Cost | Rate Limit Risk |
|----------|---------------------|---------------|------|-----------------|
| **Single Day** | 30 min | 1,806 | Free | Medium ⚠️ |
| **Multi-Day** | 7 days | 301 | Free | Zero ✅ |
| **Basic Tier** | 85 min | 5,106 | $16/mo | Zero ✅ |

**Recommendation**: Start with Multi-Day (FREE + SAFE)

## 🎯 Three Approaches

### Approach 1: Multi-Day Schedule (RECOMMENDED for Free Tier)

**When**: You want full coverage with zero risk

```bash
# Setup once
./scripts/setup_multiday_cron.sh

# That's it! Cron handles everything:
# Mon: Taoyuan    → 301 requests
# Tue: Taipei     → 301 requests
# Wed: Kaohsiung  → 301 requests
# Thu: Taichung   → 301 requests
# Fri: Tainan     → 301 requests
# Sat: NewTaipei  → 301 requests
# Sun: Merge all  → 0 requests (local)
```

**Result**: 6 cities, 1,806 requests/week, well within 2,000/day limit

### Approach 2: Single Day (for Testing/Basic Tier)

**When**: You have Basic tier or just testing

```bash
# Generate all cities at once
python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --city Taipei --city Kaohsiung \
  --max-routes 100 --delay 1.0

# Takes: ~15 minutes
# Uses: ~900 requests
```

**Result**: All cities immediately, may hit rate limit on Free tier

### Approach 3: Priority Routes (Smart)

**When**: You want daily updates for popular routes

```bash
# Daily: Top 20 routes (popular lines)
0 2 * * * python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 20 \
  --output static/bus/bundle_daily.json.gz

# Weekly: Full refresh
0 3 * * 0 python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 400 --delay 3.0 \
  --output static/bus/bundle_full.json.gz
```

**Result**: Popular routes always fresh, full coverage weekly

## 🛠️ Commands Reference

### Setup

```bash
# Multi-day schedule (recommended)
./scripts/setup_multiday_cron.sh

# Single-day schedule
./scripts/setup_bundle_cron.sh
```

### Manual Generation

```bash
# Check API usage before generating
python3 scripts/generate_bus_bundle.py --check-limits

# Single city
python3 scripts/generate_bus_bundle.py --city Taoyuan

# Multiple cities
python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --city Taipei --max-routes 100

# All cities (requires Basic tier)
python3 scripts/generate_bus_bundle.py --all --delay 0.6
```

### Merge City Bundles

```bash
# Merge all city bundles into one
python3 scripts/merge_bus_bundles.py

# Custom paths
python3 scripts/merge_bus_bundles.py \
  --input-dir static/bus \
  --output static/bus/bundle.json.gz
```

### Monitoring

```bash
# View schedule
crontab -l

# Watch logs
tail -f logs/bus_bundle.log

# Check today's run
grep "$(date +%Y-%m-%d)" logs/bus_bundle.log

# List bundles
ls -lh static/bus/bundle_*.json.gz
```

## 📋 Rate Limit Cheat Sheet

### Free Tier (2,000 req/day, 20 req/min)

| Scenario | Max Routes | Delay | Time | Requests | Safe? |
|----------|-----------|-------|------|----------|-------|
| 1 city | 50 | 1.0s | 2.5 min | 151 | ✅ |
| 1 city | 100 | 1.0s | 5 min | 301 | ✅ |
| 1 city | 400 | 3.0s | 60 min | 1,201 | ✅ |
| 6 cities | 100 | 1.0s | 30 min | 1,806 | ⚠️ OK but tight |
| 6 cities | 100 | Multi-day | 7 days | 301/day | ✅ Perfect! |

### Basic Tier (20,000 req/day, 100 req/min)

| Scenario | Max Routes | Delay | Time | Requests | Cost |
|----------|-----------|-------|------|----------|------|
| 6 cities | 400 | 0.6s | 85 min | 5,106 | $16/mo |
| All 22 cities | 100 | 0.6s | 45 min | 6,622 | $16/mo |

### Delay Guide

```bash
# Free tier (20 req/min)
--delay 3.0    # Safe: 20 req/min

# Proxy/Basic tier (100 req/min)
--delay 1.0    # Safe: 60 req/min (default)
--delay 0.6    # Max: 100 req/min

# Premium tier (500 req/min)
--delay 0.12   # Max: 500 req/min
```

## 🔍 Troubleshooting

### Getting 429 Errors

```bash
# Increase delay
python3 scripts/generate_bus_bundle.py --delay 3.0

# Or reduce routes
python3 scripts/generate_bus_bundle.py --max-routes 30
```

### Bundle Not Merging

```bash
# Check for city bundles
ls -lh static/bus/bundle_*.json.gz

# Manual merge
python3 scripts/merge_bus_bundles.py

# Check logs
grep "merge" logs/bus_bundle.log
```

### Cron Not Running

```bash
# Check cron service
systemctl status cron  # or crond

# Check crontab
crontab -l | grep bus_bundle

# Test manually
cd /opt/ws/xsw
python3 scripts/generate_bus_bundle.py --city Taoyuan --max-routes 10
```

## 📁 File Locations

```
/opt/ws/xsw/
├── scripts/
│   ├── generate_bus_bundle.py       # Main generator
│   ├── merge_bus_bundles.py         # Bundle merger
│   ├── setup_bundle_cron.sh         # Single-day setup
│   └── setup_multiday_cron.sh       # Multi-day setup
├── static/bus/
│   ├── bundle.json.gz               # Main bundle (merged)
│   ├── bundle_taoyuan.json.gz       # Individual city bundles
│   ├── bundle_taipei.json.gz
│   └── ...
├── logs/
│   └── bus_bundle.log               # Generation logs
└── docs/
    ├── BUS_BUNDLE_QUICKSTART.md     # This file
    ├── BUS_BUNDLE_SCHEDULING.md     # Detailed scheduling guide
    ├── BUS_BUNDLE_RATE_LIMITS.md    # Rate limit analysis
    └── BUS_OTA_GUIDE.md             # OTA system overview
```

## 🎓 Learn More

- **[BUS_BUNDLE_SCHEDULING.md](BUS_BUNDLE_SCHEDULING.md)** - Complete scheduling guide with examples
- **[BUS_BUNDLE_RATE_LIMITS.md](BUS_BUNDLE_RATE_LIMITS.md)** - Rate limit deep dive
- **[BUS_OTA_GUIDE.md](BUS_OTA_GUIDE.md)** - Frontend integration

## ✅ Quick Decision Tree

```
Need bundle generation?
│
├─ Have Basic tier ($16/mo)?
│  └─ Yes → Single day approach
│     └─ python3 scripts/generate_bus_bundle.py --all --delay 0.6
│
└─ Using Free tier?
   │
   ├─ Need it TODAY?
   │  └─ Single city only
   │     └─ python3 scripts/generate_bus_bundle.py --city Taoyuan
   │
   └─ Can wait 1 week?
      └─ Multi-day schedule (RECOMMENDED)
         └─ ./scripts/setup_multiday_cron.sh
```

## 🚦 Status Check

After setup, check everything is working:

```bash
# 1. Verify cron schedule
crontab -l | grep -A 10 "Bus Bundle"

# 2. Check logs directory exists
ls -la logs/

# 3. Test generation (10 routes)
python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 10 --check-limits

# 4. If all good, let it run!
echo "✅ All set! Bundle generation will run automatically"
```

---

**Quick Start**: `./scripts/setup_multiday_cron.sh` → Done! 🎉
