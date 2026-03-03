# Bus Bundle Generation - Multi-Day Scheduling

## Overview

This guide shows how to spread bundle generation across multiple days to avoid hitting TDX's daily rate limits (2,000 requests/day for Free tier).

## Strategies

### Strategy 1: Rotate Cities (Recommended for Free Tier)

Generate one city per day on a weekly rotation.

#### Weekly Schedule

```bash
# Monday: Taoyuan
0 2 * * 1 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py --city Taoyuan --output static/bus/bundle_taoyuan.json.gz

# Tuesday: Taipei
0 2 * * 2 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py --city Taipei --output static/bus/bundle_taipei.json.gz

# Wednesday: Kaohsiung
0 2 * * 3 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py --city Kaohsiung --output static/bus/bundle_kaohsiung.json.gz

# Thursday: Taichung
0 2 * * 4 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py --city Taichung --output static/bus/bundle_taichung.json.gz

# Friday: Tainan
0 2 * * 5 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py --city Tainan --output static/bus/bundle_tainan.json.gz

# Saturday: NewTaipei
0 2 * * 6 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py --city NewTaipei --output static/bus/bundle_newtaipei.json.gz

# Sunday: Merge all city bundles
0 3 * * 0 cd /opt/ws/xsw && python3 scripts/merge_bus_bundles.py
```

**Benefits**:
- Each city: ~1,200 requests (fits in Free tier)
- Fresh data every week
- No rate limit issues

### Strategy 2: Split Routes Within One City

Generate a large city (like Taoyuan with 400 routes) over multiple days.

#### Implementation

```bash
# Monday: Routes 1-100
0 2 * * 1 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 100 --route-offset 0 \
  --output static/bus/partial/taoyuan_part1.json.gz

# Tuesday: Routes 101-200
0 2 * * 2 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 100 --route-offset 100 \
  --output static/bus/partial/taoyuan_part2.json.gz

# Wednesday: Routes 201-300
0 2 * * 3 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 100 --route-offset 200 \
  --output static/bus/partial/taoyuan_part3.json.gz

# Thursday: Routes 301-400
0 2 * * 4 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 100 --route-offset 300 \
  --output static/bus/partial/taoyuan_part4.json.gz

# Friday: Merge all parts
0 3 * * 5 cd /opt/ws/xsw && python3 scripts/merge_partial_bundles.py \
  --city Taoyuan \
  --output static/bus/bundle.json.gz
```

**Benefits**:
- Full city coverage without hitting limits
- Predictable daily load (~300 requests/day)

### Strategy 3: Priority-Based Generation

Generate popular/important routes daily, full refresh weekly.

#### Implementation

```bash
# Daily: Top 20 popular routes (fast refresh)
0 2 * * * cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 20 \
  --output static/bus/bundle_daily.json.gz

# Weekly: Full refresh (all routes)
0 3 * * 0 cd /opt/ws/xsw && python3 scripts/generate_bus_bundle.py \
  --city Taoyuan --max-routes 400 --delay 3.0 \
  --output static/bus/bundle_full.json.gz
```

**Benefits**:
- Popular routes always fresh
- Full coverage once per week
- Minimal API usage daily (~60 requests)

## Automated Setup Scripts

### 1. Create Multi-Day Cron Setup Script

Create `scripts/setup_multiday_cron.sh`:

```bash
#!/bin/bash
#
# Setup multi-day bundle generation schedule
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Multi-Day Bus Bundle Cron Setup ==="
echo "Project dir: $PROJECT_DIR"
echo ""

# Remove existing bus bundle cron jobs
echo "Removing existing bus bundle cron jobs..."
crontab -l 2>/dev/null | grep -v "generate_bus_bundle.py" | crontab - 2>/dev/null || true

# Add multi-day schedule
echo "Adding multi-day schedule..."

(crontab -l 2>/dev/null; cat << EOF

# Bus Bundle Generation - Multi-Day Schedule
# Monday: Taoyuan
0 2 * * 1 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/generate_bus_bundle.py --city Taoyuan --max-routes 100 --output static/bus/bundle_taoyuan.json.gz >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

# Tuesday: Taipei
0 2 * * 2 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/generate_bus_bundle.py --city Taipei --max-routes 100 --output static/bus/bundle_taipei.json.gz >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

# Wednesday: Kaohsiung
0 2 * * 3 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/generate_bus_bundle.py --city Kaohsiung --max-routes 100 --output static/bus/bundle_kaohsiung.json.gz >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

# Thursday: Taichung
0 2 * * 4 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/generate_bus_bundle.py --city Taichung --max-routes 100 --output static/bus/bundle_taichung.json.gz >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

# Friday: Tainan
0 2 * * 5 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/generate_bus_bundle.py --city Tainan --max-routes 100 --output static/bus/bundle_tainan.json.gz >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

# Saturday: NewTaipei
0 2 * * 6 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/generate_bus_bundle.py --city NewTaipei --max-routes 100 --output static/bus/bundle_newtaipei.json.gz >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

# Sunday: Merge all city bundles
0 3 * * 0 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/merge_bus_bundles.py >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

EOF
) | crontab -

echo ""
echo "✓ Multi-day cron schedule added successfully"
echo ""
echo "Schedule:"
echo "  Monday:    Taoyuan (2:00 AM)"
echo "  Tuesday:   Taipei (2:00 AM)"
echo "  Wednesday: Kaohsiung (2:00 AM)"
echo "  Thursday:  Taichung (2:00 AM)"
echo "  Friday:    Tainan (2:00 AM)"
echo "  Saturday:  NewTaipei (2:00 AM)"
echo "  Sunday:    Merge bundles (3:00 AM)"
echo ""
echo "Logs: $PROJECT_DIR/logs/bus_bundle.log"
echo ""
echo "To view crontab:"
echo "  crontab -l"
echo ""
echo "To remove:"
echo "  crontab -e  # then delete the lines"
echo ""
```

### 2. Create Bundle Merge Script

Create `scripts/merge_bus_bundles.py`:

```python
#!/usr/bin/env python3
"""
Merge multiple city bundles into one unified bundle
"""
import sys
import os
import json
import gzip
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def merge_bundles(bundle_paths, output_path):
    """
    Merge multiple city bundles into one

    Args:
        bundle_paths: List of paths to individual city bundles
        output_path: Path to save merged bundle
    """
    merged_bundle = {
        "version": datetime.now().strftime('%Y-%m-%d-%H%M'),
        "generated_at": datetime.now().isoformat(),
        "cities": {}
    }

    total_routes = 0
    total_stops = 0

    for bundle_path in bundle_paths:
        if not Path(bundle_path).exists():
            logger.warning(f"Bundle not found: {bundle_path}")
            continue

        try:
            with gzip.open(bundle_path, 'rt', encoding='utf-8') as f:
                bundle = json.load(f)

            # Merge cities
            for city, city_data in bundle.get("cities", {}).items():
                if city not in merged_bundle["cities"]:
                    merged_bundle["cities"][city] = city_data

                    # Count stats
                    route_count = len(city_data.get("routes", {}))
                    stop_count = sum(
                        len(route_data.get("stops", {}).get("0", [])) +
                        len(route_data.get("stops", {}).get("1", []))
                        for route_data in city_data.get("routes", {}).values()
                    )

                    total_routes += route_count
                    total_stops += stop_count

                    logger.info(f"  Merged {city}: {route_count} routes, {stop_count} stops")
                else:
                    logger.warning(f"  Duplicate city {city}, skipping")

        except Exception as e:
            logger.error(f"Failed to load {bundle_path}: {e}")
            continue

    # Add stats
    merged_bundle["stats"] = {
        "total_cities": len(merged_bundle["cities"]),
        "total_routes": total_routes,
        "total_stops": total_stops
    }

    # Save merged bundle
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Calculate sizes
    json_str = json.dumps(merged_bundle, ensure_ascii=False, indent=2)
    uncompressed_size = len(json_str.encode('utf-8'))

    # Write compressed
    with gzip.open(output_path, 'wt', encoding='utf-8') as f:
        json.dump(merged_bundle, f, ensure_ascii=False, indent=2)

    compressed_size = output_file.stat().st_size

    logger.info(f"Merged bundle saved to: {output_path}")
    logger.info(f"  Version: {merged_bundle['version']}")
    logger.info(f"  Cities: {len(merged_bundle['cities'])}")
    logger.info(f"  Routes: {total_routes}")
    logger.info(f"  Stops: {total_stops}")
    logger.info(f"  Uncompressed: {uncompressed_size / 1024:.1f} KB")
    logger.info(f"  Compressed: {compressed_size / 1024:.1f} KB")
    logger.info(f"  Compression: {(1 - compressed_size/uncompressed_size) * 100:.1f}%")


def main():
    logger.info("Starting bundle merge...")

    # Define bundle paths
    bundle_dir = Path("static/bus")
    city_bundles = [
        bundle_dir / "bundle_taoyuan.json.gz",
        bundle_dir / "bundle_taipei.json.gz",
        bundle_dir / "bundle_kaohsiung.json.gz",
        bundle_dir / "bundle_taichung.json.gz",
        bundle_dir / "bundle_tainan.json.gz",
        bundle_dir / "bundle_newtaipei.json.gz",
    ]

    output_path = bundle_dir / "bundle.json.gz"

    merge_bundles(city_bundles, output_path)
    logger.info("Done!")


if __name__ == "__main__":
    main()
```

## Usage

### Setup Multi-Day Schedule

```bash
# Make scripts executable
chmod +x scripts/setup_multiday_cron.sh
chmod +x scripts/merge_bus_bundles.py

# Setup the schedule
./scripts/setup_multiday_cron.sh
```

### Manual Testing

```bash
# Test individual city generation
python3 scripts/generate_bus_bundle.py --city Taoyuan --output static/bus/bundle_taoyuan.json.gz

python3 scripts/generate_bus_bundle.py --city Taipei --output static/bus/bundle_taipei.json.gz

# Test merge
python3 scripts/merge_bus_bundles.py
```

### Check Progress

```bash
# View cron jobs
crontab -l

# View logs
tail -f logs/bus_bundle.log

# Check generated bundles
ls -lh static/bus/bundle_*.json.gz
```

## API Usage Per Schedule

### City Rotation (Recommended)

| Day | City | Routes | Requests | Time @ 1.0s |
|-----|------|--------|----------|-------------|
| Mon | Taoyuan | 100 | ~301 | ~5 min |
| Tue | Taipei | 100 | ~301 | ~5 min |
| Wed | Kaohsiung | 100 | ~301 | ~5 min |
| Thu | Taichung | 100 | ~301 | ~5 min |
| Fri | Tainan | 100 | ~301 | ~5 min |
| Sat | NewTaipei | 100 | ~301 | ~5 min |
| Sun | Merge | 0 | 0 | ~1 sec |

**Total per week**: 1,806 requests (within Free tier daily limit)

### Route Split (Alternative)

| Day | Batch | Routes | Requests | Time @ 1.0s |
|-----|-------|--------|----------|-------------|
| Mon | Part 1 | 100 | ~301 | ~5 min |
| Tue | Part 2 | 100 | ~301 | ~5 min |
| Wed | Part 3 | 100 | ~301 | ~5 min |
| Thu | Part 4 | 100 | ~301 | ~5 min |
| Fri | Merge | 0 | 0 | ~1 sec |

**Total per week**: 1,204 requests (well within limits)

## Frontend Integration

The merged bundle works exactly like a single bundle:

```typescript
// No changes needed to frontend code
const response = await fetch('/bus/api/bundle/version');
const bundle = await fetch('/bus/api/bundle/download');

// Works with merged data from multiple cities
const taoyuanRoutes = bundle.cities.Taoyuan.routes;
const taipeiRoutes = bundle.cities.Taipei.routes;
```

## Monitoring

### Check Daily Usage

```bash
# View today's bundle generation
grep "$(date +%Y-%m-%d)" logs/bus_bundle.log | grep "Total API requests"

# Output:
# 2026-03-03 02:05:00 - INFO - Total API requests: 301
```

### Alert on Failures

Add to your monitoring:

```bash
# Check for errors in last 24 hours
if grep -q "ERROR" logs/bus_bundle.log | grep "$(date +%Y-%m-%d)"; then
    echo "Bundle generation failed!"
    # Send alert
fi
```

## Best Practices

1. **Start Small**: Test with 2-3 cities before full schedule
2. **Monitor Logs**: Check logs daily for first week
3. **Adjust Delays**: Increase `--delay` if you see 429 errors
4. **Cache Leverage**: Cloudflare caches static data for 24h
5. **Backup Bundles**: Keep previous week's bundles as backup

## Summary

**For Free Tier Users**:
- Use city rotation strategy
- Generate 100 routes per city per day
- Merge on Sunday
- Total: ~300 requests/day (well within 2,000 limit)

**For Basic Tier Users**:
- Generate all cities daily if needed
- No need for multi-day scheduling
- Use `--delay 0.6` for full speed

**Result**: Complete Taiwan coverage with zero rate limit issues! 🎉
