"""
Bus API Endpoints - yunbus-style with TDX backend
"""
import logging
import json
import gzip
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse, Response
import os

from tdx_client import TDXClient
from bus_transformer import BusTransformer
from bus_cache import BusCache

logger = logging.getLogger(__name__)

# Initialize components
tdx_client = TDXClient()
transformer = BusTransformer()
bus_cache = BusCache()

# Create router
bus_router = APIRouter(prefix="/bus/api")

# Bundle configuration
BUNDLE_PATH = os.getenv('BUS_BUNDLE_PATH', 'static/bus/bundle.json.gz')
BUNDLE_VERSION_CACHE_KEY = 'bundle:version'


def parse_bus_query(query_string: str):
    """
    Parse yunbus-style query string
    Examples:
      - ?estime&709 → {"action": "estime", "route": "709"}
      - ?plate&709 → {"action": "plate", "route": "709"}
      - ?route&Taoyuan → {"action": "route", "city": "Taoyuan"}
    """
    if not query_string or query_string == '?':
        raise HTTPException(status_code=400, detail="Missing query parameters")

    query_string = query_string.lstrip('?')
    parts = query_string.split('&')

    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid query format")

    action = parts[0]
    param = parts[1] if len(parts) > 1 else ""

    return {"action": action, "param": param}


@bus_router.get("", response_class=PlainTextResponse)
async def bus_api_endpoint(request: Request):
    """
    Main bus API endpoint - yunbus compatible

    Query formats:
      - ?estime&{route_id}  → Estimated arrival times
      - ?plate&{route_id}   → Bus plate numbers
      - ?stop&{route_id}    → Stop list (JSON)
      - ?mapstop&{route_id} → Stop coordinates (JSON)
      - ?mapshape&{route_id} → Route shape (JSON)
      - ?mapbus&{route_id}  → Real-time bus positions (JSON)
      - ?stopes&{route_id}  → Alias for estime
      - ?route&{city}       → List routes in city (JSON)
    """
    query_str = str(request.url.query)

    try:
        parsed = parse_bus_query(query_str)
        action = parsed["action"]
        param = parsed["param"]

        # Default city (can be extracted from route_id prefix)
        city = os.getenv('BUS_DEFAULT_CITY', 'Taoyuan')

        # Handle different actions
        if action == "estime" or action == "stopes":
            return await handle_estime(param, city)

        elif action == "plate":
            return await handle_plate(param, city)

        elif action == "stop":
            return await handle_stop(param, city)

        elif action == "mapstop":
            return await handle_mapstop(param, city)

        elif action == "mapshape":
            return await handle_mapshape(param, city)

        elif action == "mapbus":
            return await handle_mapbus(param, city)

        elif action == "route":
            return await handle_route(param)  # param is city name

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    except Exception as e:
        logger.error(f"Bus API error: {e}", exc_info=True)
        return PlainTextResponse(f"ERROR: {str(e)}", status_code=500)


async def handle_estime(route_id: str, city: str) -> PlainTextResponse:
    """
    Handle ?estime&{route_id}
    Returns: route_id,200,OK,1\ndirection_stopId_time_plate|...
    """
    try:
        # Check cache first (30s TTL)
        cache_key = f"estime:{city}:{route_id}"
        cached = bus_cache.get(cache_key)
        if cached:
            return PlainTextResponse(cached)

        # Fetch from TDX
        arrivals = tdx_client.get_estimated_arrival(city, route_id)
        positions = tdx_client.get_bus_realtime_position(city, route_id)

        # Transform to yunbus format
        data_str = transformer.tdx_to_estime(arrivals, positions)

        # Build response
        response = f"{route_id},200,OK,1\n{data_str}"

        # Cache result
        bus_cache.set(cache_key, response, ttl=30)

        return PlainTextResponse(response)

    except Exception as e:
        logger.error(f"Error fetching estime for {route_id}: {e}")
        return PlainTextResponse(f"{route_id},500,ERROR\n")


async def handle_plate(route_id: str, city: str) -> PlainTextResponse:
    """
    Handle ?plate&{route_id}
    Returns: route_id,200,OK\ndirection_stopId_plate_atStopFlag_0|...
    """
    try:
        cache_key = f"plate:{city}:{route_id}"
        cached = bus_cache.get(cache_key)
        if cached:
            return PlainTextResponse(cached)

        arrivals = tdx_client.get_estimated_arrival(city, route_id)
        positions = tdx_client.get_bus_realtime_position(city, route_id)

        data_str = transformer.tdx_to_plate(arrivals, positions)
        response = f"{route_id},200,OK\n{data_str}"

        bus_cache.set(cache_key, response, ttl=30)
        return PlainTextResponse(response)

    except Exception as e:
        logger.error(f"Error fetching plate for {route_id}: {e}")
        return PlainTextResponse(f"{route_id},500,ERROR\n")


async def handle_stop(route_id: str, city: str) -> JSONResponse:
    """
    Handle ?stop&{route_id}
    Returns JSON with stop list grouped by direction
    """
    try:
        cache_key = f"stop:{city}:{route_id}"
        cached = bus_cache.get(cache_key)
        if cached:
            import json
            return JSONResponse(json.loads(cached))

        stops = tdx_client.get_bus_stops(city, route_id)
        stop_of_route = tdx_client.get_route_stops_of_route(city, route_id)

        result = transformer.tdx_to_stop_json(stops, stop_of_route)
        result["routeId"] = route_id

        # Cache for 24 hours (static data)
        import json
        bus_cache.set(cache_key, json.dumps(result), ttl=86400)
        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Error fetching stops for {route_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_mapstop(route_id: str, city: str) -> JSONResponse:
    """
    Handle ?mapstop&{route_id}
    Returns JSON with stop coordinates
    """
    try:
        cache_key = f"mapstop:{city}:{route_id}"
        cached = bus_cache.get(cache_key)
        if cached:
            import json
            return JSONResponse(json.loads(cached))

        stops = tdx_client.get_bus_stops(city, route_id)
        stop_of_route = tdx_client.get_route_stops_of_route(city, route_id)

        result = transformer.tdx_to_mapstop_json(stops, stop_of_route)
        result["routeId"] = route_id

        import json
        bus_cache.set(cache_key, json.dumps(result), ttl=86400)
        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Error fetching mapstop for {route_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_mapshape(route_id: str, city: str) -> JSONResponse:
    """
    Handle ?mapshape&{route_id}
    Returns JSON with route path geometry
    """
    try:
        cache_key = f"mapshape:{city}:{route_id}"
        cached = bus_cache.get(cache_key)
        if cached:
            import json
            return JSONResponse(json.loads(cached))

        shapes = tdx_client.get_bus_route_shape(city, route_id)

        result = transformer.tdx_to_mapshape_json(shapes)
        result["routeId"] = route_id

        import json
        bus_cache.set(cache_key, json.dumps(result), ttl=86400)
        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Error fetching mapshape for {route_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_mapbus(route_id: str, city: str) -> JSONResponse:
    """
    Handle ?mapbus&{route_id}
    Returns JSON with real-time bus positions
    """
    try:
        cache_key = f"mapbus:{city}:{route_id}"
        cached = bus_cache.get(cache_key)
        if cached:
            import json
            return JSONResponse(json.loads(cached))

        positions = tdx_client.get_bus_realtime_position(city, route_id)

        result = transformer.tdx_to_mapbus_json(positions)
        result["routeId"] = route_id

        import json
        bus_cache.set(cache_key, json.dumps(result), ttl=15)  # 15s for real-time
        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Error fetching mapbus for {route_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_route(city: str) -> JSONResponse:
    """
    Handle ?route&{city}
    Returns JSON with route list for a city
    """
    try:
        cache_key = f"route:{city}"
        cached = bus_cache.get(cache_key)
        if cached:
            import json
            return JSONResponse(json.loads(cached))

        routes = tdx_client.get_routes(city)

        result = transformer.tdx_to_route_list_json(routes, city)

        import json
        bus_cache.set(cache_key, json.dumps(result), ttl=86400)
        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Error fetching routes for {city}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Static Bundle OTA Endpoints =====

@bus_router.get("/bundle/version")
async def get_bundle_version() -> JSONResponse:
    """
    Get current bundle version

    Returns:
        {
            "version": "2026-03-03-1200",
            "generated_at": "2026-03-03T12:00:00",
            "size": 1234567,
            "cities": ["Taoyuan", "Taipei"],
            "available": true
        }
    """
    bundle_file = Path(BUNDLE_PATH)

    if not bundle_file.exists():
        return JSONResponse({
            "version": None,
            "available": False,
            "error": "Bundle not generated yet"
        })

    try:
        # Try to get cached version info
        cached_version = bus_cache.get(BUNDLE_VERSION_CACHE_KEY)
        if cached_version:
            return JSONResponse(json.loads(cached_version))

        # Read bundle metadata
        with gzip.open(bundle_file, 'rt', encoding='utf-8') as f:
            bundle = json.load(f)

        version_info = {
            "version": bundle.get("version"),
            "generated_at": bundle.get("generated_at"),
            "size": bundle_file.stat().st_size,
            "cities": list(bundle.get("cities", {}).keys()),
            "stats": bundle.get("stats", {}),
            "available": True
        }

        # Cache for 1 hour
        bus_cache.set(BUNDLE_VERSION_CACHE_KEY, json.dumps(version_info), ttl=3600)

        return JSONResponse(version_info)

    except Exception as e:
        logger.error(f"Error reading bundle version: {e}")
        return JSONResponse({
            "version": None,
            "available": False,
            "error": str(e)
        })


@bus_router.get("/bundle/download")
async def download_bundle() -> Response:
    """
    Download compressed bundle

    Returns:
        Gzipped JSON bundle (~2-5MB)

    Headers:
        - Content-Encoding: gzip
        - Content-Type: application/json
        - ETag: {version}
    """
    bundle_file = Path(BUNDLE_PATH)

    if not bundle_file.exists():
        raise HTTPException(status_code=404, detail="Bundle not available")

    try:
        # Read bundle to get version for ETag
        with gzip.open(bundle_file, 'rt', encoding='utf-8') as f:
            bundle = json.load(f)

        version = bundle.get("version", "unknown")

        # Return compressed file
        with open(bundle_file, 'rb') as f:
            content = f.read()

        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Encoding": "gzip",
                "ETag": f'"{version}"',
                "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
            }
        )

    except Exception as e:
        logger.error(f"Error serving bundle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bus_router.get("/bundle/city/{city}")
async def get_city_bundle(city: str) -> JSONResponse:
    """
    Get bundle data for a specific city (uncompressed)

    This allows downloading only specific city data
    instead of the entire bundle.

    Args:
        city: City name (e.g., "Taoyuan", "Taipei")

    Returns:
        {
            "city": "Taoyuan",
            "version": "2026-03-03-1200",
            "routes": {...}
        }
    """
    bundle_file = Path(BUNDLE_PATH)

    if not bundle_file.exists():
        raise HTTPException(status_code=404, detail="Bundle not available")

    try:
        # Check cache first
        cache_key = f"bundle:city:{city}"
        cached = bus_cache.get(cache_key)
        if cached:
            return JSONResponse(json.loads(cached))

        # Read bundle
        with gzip.open(bundle_file, 'rt', encoding='utf-8') as f:
            bundle = json.load(f)

        if city not in bundle.get("cities", {}):
            raise HTTPException(status_code=404, detail=f"City '{city}' not found in bundle")

        city_data = {
            "city": city,
            "version": bundle.get("version"),
            "routes": bundle["cities"][city].get("routes", {})
        }

        # Cache for 24 hours
        bus_cache.set(cache_key, json.dumps(city_data), ttl=86400)

        return JSONResponse(city_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving city bundle for {city}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
