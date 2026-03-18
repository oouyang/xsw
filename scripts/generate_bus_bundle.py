#!/usr/bin/env python3
"""
Generate static bus data bundle for OTA distribution

This script fetches all routes, stops, and shapes from TDX
and packages them into a compressed JSON bundle.

Usage:
    python3 scripts/generate_bus_bundle.py
    python3 scripts/generate_bus_bundle.py --city Taipei --city Taoyuan
"""

import sys
import os
import json
import gzip
import logging
import argparse
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables before importing modules that depend on them
load_dotenv()

from tdx_client import TDXClient  # noqa: E402
from bus_transformer import BusTransformer  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BundleGenerator:
    """Generate static bus data bundle"""

    # All Taiwan cities
    ALL_CITIES = [
        "Taipei",
        "NewTaipei",
        "Taoyuan",
        "Taichung",
        "Tainan",
        "Kaohsiung",
        "Keelung",
        "Hsinchu",
        "HsinchuCounty",
        "MiaoliCounty",
        "ChanghuaCounty",
        "NantouCounty",
        "YunlinCounty",
        "ChiayiCounty",
        "Chiayi",
        "PingtungCounty",
        "YilanCounty",
        "HualienCounty",
        "TaitungCounty",
        "KinmenCounty",
        "PenghuCounty",
        "LienchiangCounty",
    ]

    def __init__(self, cities: List[str] = None, rate_limit_delay: float = None):
        self.client = TDXClient()
        self.transformer = BusTransformer()
        self.cities = cities or ["Taoyuan"]  # Default to Taoyuan only

        # Rate limiting: delay between requests (in seconds)
        # Free tier: 20 req/min = 3.0s delay
        # Basic tier: 100 req/min = 0.6s delay
        # Premium tier: 500 req/min = 0.12s delay
        self.rate_limit_delay = rate_limit_delay or float(
            os.getenv("TDX_RATE_LIMIT_DELAY", "1.0")
        )

        # Request counter
        self.request_count = 0

    def generate_bundle(self, output_path: str = None) -> Dict[str, Any]:
        """
        Generate complete static bundle

        Returns:
            Bundle dictionary with all static data
        """
        if output_path is None:
            output_path = os.getenv("BUS_BUNDLE_PATH", "static/bus/bundle.json.gz")

        bundle = {
            "version": datetime.now().strftime("%Y-%m-%d-%H%M"),
            "generated_at": datetime.now().isoformat(),
            "cities": {},
        }

        total_routes = 0
        total_stops = 0

        for city in self.cities:
            logger.info(f"Processing city: {city}")

            try:
                city_data = self._generate_city_data(city)
                bundle["cities"][city] = city_data

                route_count = len(city_data.get("routes", {}))
                stop_count = sum(
                    len(route_data.get("stops", {}).get("0", []))
                    + len(route_data.get("stops", {}).get("1", []))
                    for route_data in city_data.get("routes", {}).values()
                )

                total_routes += route_count
                total_stops += stop_count

                logger.info(f"  {city}: {route_count} routes, {stop_count} stops")

            except Exception as e:
                logger.error(f"Failed to process {city}: {e}")
                # Continue with other cities
                bundle["cities"][city] = {"error": str(e), "routes": {}}

        bundle["stats"] = {
            "total_cities": len(self.cities),
            "total_routes": total_routes,
            "total_stops": total_stops,
        }

        # Save bundle
        self._save_bundle(bundle, output_path)

        logger.info("Bundle generated successfully!")
        logger.info(f"  Version: {bundle['version']}")
        logger.info(f"  Cities: {len(self.cities)}")
        logger.info(f"  Routes: {total_routes}")
        logger.info(f"  Stops: {total_stops}")
        logger.info(f"  Total API requests: {self.request_count}")

        return bundle

    def _rate_limit(self):
        """Apply rate limiting delay between requests"""
        if self.rate_limit_delay > 0:
            time.sleep(self.rate_limit_delay)
        self.request_count += 1

    def _generate_city_data(self, city: str) -> Dict[str, Any]:
        """
        Generate data for a single city

        Returns:
            {
                "routes": {
                    "709": {
                        "name": "709",
                        "from": "起點",
                        "to": "終點",
                        "stops": {...},
                        "shapes": {...}
                    }
                }
            }
        """
        city_data = {"routes": {}}

        # Get all routes in city
        routes = self.client.get_routes(city)
        self._rate_limit()
        logger.info(f"  Found {len(routes)} routes")

        # Process each route (limit to avoid timeout)
        max_routes = int(os.getenv("BUS_BUNDLE_MAX_ROUTES_PER_CITY", "50"))
        for idx, route in enumerate(routes[:max_routes]):
            route_id = route.get("RouteID", "")

            if not route_id:
                continue

            try:
                route_data = self._generate_route_data(city, route_id, route)
                city_data["routes"][route_id] = route_data

                if (idx + 1) % 10 == 0:
                    logger.info(
                        f"  Processed {idx + 1}/{min(len(routes), max_routes)} routes"
                    )

            except Exception as e:
                logger.warning(f"  Failed to process route {route_id}: {e}")
                # Continue with other routes
                continue

        return city_data

    def _generate_route_data(
        self, city: str, route_id: str, route_info: Dict
    ) -> Dict[str, Any]:
        """
        Generate data for a single route
        """
        route_name = route_info.get("RouteName", {}).get("Zh_tw", route_id)

        # Get from/to from SubRoutes
        sub_routes = route_info.get("SubRoutes", [])
        from_stop = ""
        to_stop = ""
        if sub_routes:
            sub = sub_routes[0]
            from_stop = sub.get("DepartureStopNameZh", "")
            to_stop = sub.get("DestinationStopNameZh", "")

        route_data = {
            "name": route_name,
            "from": from_stop,
            "to": to_stop,
            "stops": {},
            "shapes": {},
        }

        # Get stops with sequence
        try:
            stops = self.client.get_bus_stops(city, route_id)
            self._rate_limit()

            stop_of_route = self.client.get_route_stops_of_route(city, route_id)
            self._rate_limit()

            stop_json = self.transformer.tdx_to_stop_json(stops, stop_of_route)
            route_data["stops"] = stop_json.get("stops", {})

            # Add coordinates to stops
            mapstop_json = self.transformer.tdx_to_mapstop_json(stops, stop_of_route)
            stop_coords = {
                s["id"]: {"lat": s["lat"], "lng": s["lng"]}
                for s in mapstop_json.get("stops", [])
            }

            # Merge coordinates into stops
            for direction in route_data["stops"]:
                for stop in route_data["stops"][direction]:
                    if stop["id"] in stop_coords:
                        stop["lat"] = stop_coords[stop["id"]]["lat"]
                        stop["lng"] = stop_coords[stop["id"]]["lng"]

        except Exception as e:
            logger.warning(f"    Failed to get stops for {route_id}: {e}")

        # Get route shapes
        try:
            shapes = self.client.get_bus_route_shape(city, route_id)
            self._rate_limit()

            shape_json = self.transformer.tdx_to_mapshape_json(shapes)
            route_data["shapes"] = shape_json.get("shapes", {})
        except Exception as e:
            logger.warning(f"    Failed to get shapes for {route_id}: {e}")

        return route_data

    def _save_bundle(self, bundle: Dict, output_path: str):
        """
        Save bundle as compressed JSON
        """
        # Create directory if needed
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Save uncompressed JSON (for debugging)
        json_path = output_file.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)

        json_size = json_path.stat().st_size

        # Save compressed version
        with gzip.open(output_path, "wt", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False)

        gz_size = Path(output_path).stat().st_size

        logger.info(f"Saved to: {output_path}")
        logger.info(f"  Uncompressed: {json_size / 1024:.1f} KB")
        logger.info(f"  Compressed: {gz_size / 1024:.1f} KB")
        logger.info(f"  Compression: {(1 - gz_size / json_size) * 100:.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Generate bus data bundle",
        epilog="""
Rate Limit Examples:
  Free tier (20 req/min):   --delay 3.0
  Basic tier (100 req/min): --delay 0.6
  Premium (500 req/min):    --delay 0.12
  Proxy (100 req/min):      --delay 1.0 (default)

Estimated Time:
  Taoyuan (400 routes): ~27 min at 1.0s delay
  All 6 cities (1700 routes): ~115 min at 1.0s delay
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--city",
        action="append",
        dest="cities",
        help="City to include (can be specified multiple times)",
    )
    parser.add_argument("--all", action="store_true", help="Include all Taiwan cities")
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: static/bus/bundle.json.gz)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Delay between API requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--max-routes",
        type=int,
        default=None,
        help="Maximum routes per city (default: 50, set BUS_BUNDLE_MAX_ROUTES_PER_CITY)",
    )
    parser.add_argument(
        "--check-limits",
        action="store_true",
        help="Calculate API requests needed without generating",
    )

    args = parser.parse_args()

    # Set environment variables if specified
    if args.max_routes:
        os.environ["BUS_BUNDLE_MAX_ROUTES_PER_CITY"] = str(args.max_routes)

    # Determine which cities to process
    if args.all:
        cities = BundleGenerator.ALL_CITIES
        logger.info(f"Processing ALL {len(cities)} cities")
    elif args.cities:
        cities = args.cities
        logger.info(f"Processing {len(cities)} cities: {', '.join(cities)}")
    else:
        # Default: Taoyuan only
        cities = ["Taoyuan"]
        logger.info("Processing default city: Taoyuan")

    # Check limits mode
    if args.check_limits:
        max_routes = int(os.getenv("BUS_BUNDLE_MAX_ROUTES_PER_CITY", "50"))
        total_requests = len(cities) + (
            len(cities) * max_routes * 3
        )  # 3 API calls per route
        delay = args.delay or 1.0
        estimated_time = (total_requests * delay) / 60

        logger.info("=" * 60)
        logger.info("API Request Estimation")
        logger.info("=" * 60)
        logger.info(f"Cities: {len(cities)}")
        logger.info(f"Max routes per city: {max_routes}")
        logger.info(f"Total requests: ~{total_requests:,}")
        logger.info(f"Rate limit delay: {delay}s")
        logger.info(f"Estimated time: ~{estimated_time:.1f} minutes")
        logger.info("=" * 60)
        return

    # Generate bundle
    generator = BundleGenerator(cities=cities, rate_limit_delay=args.delay)
    generator.generate_bundle(output_path=args.output)

    logger.info("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
