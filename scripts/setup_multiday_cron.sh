#!/bin/bash
#
# Setup multi-day bundle generation schedule
# Generates one city per day to stay within Free tier limits
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Multi-Day Bus Bundle Cron Setup ==="
echo "Project dir: $PROJECT_DIR"
echo ""

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"

# Remove existing bus bundle cron jobs
echo "Removing existing bus bundle cron jobs..."
crontab -l 2>/dev/null | grep -v "generate_bus_bundle.py" | grep -v "merge_bus_bundles.py" | crontab - 2>/dev/null || true

# Add multi-day schedule
echo "Adding multi-day schedule..."

(crontab -l 2>/dev/null; cat << EOF

# Bus Bundle Generation - Multi-Day Schedule (Free Tier Safe)
# Each city: ~300 requests/day (well within 2,000 limit)

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

# Sunday: Merge all city bundles into one
0 3 * * 0 cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/merge_bus_bundles.py >> $PROJECT_DIR/logs/bus_bundle.log 2>&1

EOF
) | crontab -

echo ""
echo "✓ Multi-day cron schedule added successfully"
echo ""
echo "Schedule (all times server local):"
echo "  Monday:    Taoyuan (2:00 AM)"
echo "  Tuesday:   Taipei (2:00 AM)"
echo "  Wednesday: Kaohsiung (2:00 AM)"
echo "  Thursday:  Taichung (2:00 AM)"
echo "  Friday:    Tainan (2:00 AM)"
echo "  Saturday:  NewTaipei (2:00 AM)"
echo "  Sunday:    Merge all bundles (3:00 AM)"
echo ""
echo "API Usage:"
echo "  Per day: ~300 requests (6 cities × ~300 req)"
echo "  Per week: ~1,800 requests total"
echo "  Well within Free tier (2,000 req/day)"
echo ""
echo "Logs: $PROJECT_DIR/logs/bus_bundle.log"
echo ""
echo "Commands:"
echo "  View crontab:    crontab -l"
echo "  View logs:       tail -f $PROJECT_DIR/logs/bus_bundle.log"
echo "  Remove schedule: crontab -e  # then delete the lines"
echo ""
echo "Test manually:"
echo "  cd $PROJECT_DIR"
echo "  python3 scripts/generate_bus_bundle.py --city Taoyuan --max-routes 10 --check-limits"
echo ""
