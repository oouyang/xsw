#!/bin/bash
#
# Setup weekly cron job for bus bundle generation
#
# Usage:
#   ./scripts/setup_bundle_cron.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Bus Bundle Cron Job Setup ==="
echo "Project dir: $PROJECT_DIR"

# Create cron job entry
CRON_CMD="cd $PROJECT_DIR && /usr/bin/python3 $PROJECT_DIR/scripts/generate_bus_bundle.py --city Taoyuan >> $PROJECT_DIR/logs/bus_bundle.log 2>&1"

# Run every Sunday at 2 AM
CRON_SCHEDULE="0 2 * * 0"

CRON_ENTRY="$CRON_SCHEDULE $CRON_CMD"

echo ""
echo "Cron entry:"
echo "  $CRON_ENTRY"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -F "$CRON_CMD" > /dev/null; then
    echo "✓ Cron job already exists"
else
    echo "Adding cron job..."
    # Add to existing crontab
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo "✓ Cron job added successfully"
fi

echo ""
echo "Cron job will run:"
echo "  - Every Sunday at 2:00 AM"
echo "  - Logs: $PROJECT_DIR/logs/bus_bundle.log"
echo ""
echo "To view current crontab:"
echo "  crontab -l"
echo ""
echo "To remove the cron job:"
echo "  crontab -e  # then delete the line"
echo ""
echo "To test the script manually:"
echo "  cd $PROJECT_DIR"
echo "  python3 scripts/generate_bus_bundle.py --city Taoyuan"
echo ""
