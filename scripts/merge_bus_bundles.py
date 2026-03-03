#!/usr/bin/env python3
"""
Merge multiple city bundles into one unified bundle

This script combines individual city bundles (generated on different days)
into a single bundle that can be served to the frontend.

Usage:
    python3 scripts/merge_bus_bundles.py
    python3 scripts/merge_bus_bundles.py --input-dir static/bus --output static/bus/bundle.json.gz
"""
import sys
import os
import json
import gzip
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import List
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_city_bundles(input_dir: Path) -> List[Path]:
    """
    Find all city bundle files in the input directory

    Args:
        input_dir: Directory containing city bundles

    Returns:
        List of paths to bundle files
    """
    # Look for files matching pattern: bundle_*.json.gz
    # but exclude the main bundle.json.gz
    bundles = []
    for file_path in input_dir.glob("bundle_*.json.gz"):
        if file_path.name != "bundle.json.gz":
            bundles.append(file_path)

    return sorted(bundles)


def merge_bundles(bundle_paths: List[Path], output_path: Path):
    """
    Merge multiple city bundles into one

    Args:
        bundle_paths: List of paths to individual city bundles
        output_path: Path to save merged bundle
    """
    if not bundle_paths:
        logger.warning("No city bundles found to merge")
        return

    logger.info(f"Merging {len(bundle_paths)} city bundles...")

    merged_bundle = {
        "version": datetime.now().strftime('%Y-%m-%d-%H%M'),
        "generated_at": datetime.now().isoformat(),
        "cities": {}
    }

    total_routes = 0
    total_stops = 0
    merged_count = 0

    for bundle_path in bundle_paths:
        if not bundle_path.exists():
            logger.warning(f"Bundle not found: {bundle_path}")
            continue

        try:
            logger.info(f"Processing: {bundle_path.name}")

            with gzip.open(bundle_path, 'rt', encoding='utf-8') as f:
                bundle = json.load(f)

            # Merge cities
            cities_in_bundle = bundle.get("cities", {})
            for city, city_data in cities_in_bundle.items():
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
                    merged_count += 1

                    logger.info(f"  ✓ {city}: {route_count} routes, {stop_count} stops")
                else:
                    logger.warning(f"  ⚠ {city} already exists, skipping")

        except Exception as e:
            logger.error(f"  ✗ Failed to load {bundle_path.name}: {e}")
            continue

    if merged_count == 0:
        logger.error("No cities were successfully merged!")
        return

    # Add stats
    merged_bundle["stats"] = {
        "total_cities": len(merged_bundle["cities"]),
        "total_routes": total_routes,
        "total_stops": total_stops
    }

    # Save merged bundle
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculate sizes
    json_str = json.dumps(merged_bundle, ensure_ascii=False, indent=2)
    uncompressed_size = len(json_str.encode('utf-8'))

    # Write compressed
    with gzip.open(output_path, 'wt', encoding='utf-8') as f:
        json.dump(merged_bundle, f, ensure_ascii=False, indent=2)

    compressed_size = output_path.stat().st_size
    compression_ratio = (1 - compressed_size / uncompressed_size) * 100

    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ Bundle merge completed successfully!")
    logger.info("=" * 60)
    logger.info(f"Output: {output_path}")
    logger.info(f"  Version: {merged_bundle['version']}")
    logger.info(f"  Cities: {len(merged_bundle['cities'])}")
    logger.info(f"  Routes: {total_routes}")
    logger.info(f"  Stops: {total_stops}")
    logger.info(f"  Uncompressed: {uncompressed_size / 1024:.1f} KB")
    logger.info(f"  Compressed: {compressed_size / 1024:.1f} KB")
    logger.info(f"  Compression: {compression_ratio:.1f}%")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Merge multiple city bundles into one unified bundle'
    )
    parser.add_argument(
        '--input-dir',
        default='static/bus',
        help='Directory containing city bundles (default: static/bus)'
    )
    parser.add_argument(
        '--output',
        default='static/bus/bundle.json.gz',
        help='Output path for merged bundle (default: static/bus/bundle.json.gz)'
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        sys.exit(1)

    logger.info("Starting bundle merge...")
    logger.info(f"Input directory: {input_dir}")
    logger.info(f"Output: {output_path}")
    logger.info("")

    # Find all city bundles
    city_bundles = find_city_bundles(input_dir)

    if not city_bundles:
        logger.error(f"No city bundles found in {input_dir}")
        logger.info("Expected files like: bundle_taoyuan.json.gz, bundle_taipei.json.gz")
        sys.exit(1)

    logger.info(f"Found {len(city_bundles)} city bundles:")
    for bundle in city_bundles:
        logger.info(f"  - {bundle.name}")
    logger.info("")

    # Merge bundles
    merge_bundles(city_bundles, output_path)

    logger.info("Done!")


if __name__ == "__main__":
    main()
