"""
Transform TDX API responses to yunbus-compatible format
"""
import logging
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class BusTransformer:
    """Transform TDX responses to yunbus pipe-separated format"""

    @staticmethod
    def tdx_to_estime(arrivals: List[Dict], positions: List[Dict] = None) -> str:
        """
        Transform TDX EstimatedTimeOfArrival to yunbus ?estime format

        Args:
            arrivals: TDX EstimatedTimeOfArrival response
            positions: Optional TDX RealTimeByFrequency response for plate matching

        Returns:
            Pipe-separated string: direction_stopId_time_plate|...
        """
        if not arrivals:
            return ""

        # Build plate lookup by direction
        plate_by_stop = {}
        if positions:
            for bus in positions:
                # Approximate: use closest stop or sequence
                plate = bus.get('PlateNumb', '')
                direction = bus.get('Direction', 0)
                # Note: TDX doesn't directly provide which stop the bus is at
                # We'd need additional logic to match positions to stops
                # For now, store plates by direction
                key = f"{direction}"
                if key not in plate_by_stop:
                    plate_by_stop[key] = []
                plate_by_stop[key].append(plate)

        # Group by direction and stop
        records = []
        for arrival in arrivals:
            direction = arrival.get('Direction', 0)
            stop_uid = arrival.get('StopUID', '')
            estimate_time = arrival.get('EstimateTime')
            plate = arrival.get('PlateNumb', '')

            # Convert estimate time
            if estimate_time is not None and estimate_time >= 0:
                time_str = str(estimate_time)  # seconds
            else:
                # No real-time data, use schedule time or empty
                time_str = arrival.get('NextBusTime', '')
                if time_str:
                    # Convert ISO time to HH:MM
                    try:
                        dt = datetime.fromisoformat(time_str.replace('+08:00', ''))
                        time_str = dt.strftime('%H:%M')
                    except (ValueError, AttributeError):
                        time_str = ''

            # Build record
            record = f"{direction}_{stop_uid}_{time_str}_{plate}"
            records.append(record)

        return '|'.join(records)

    @staticmethod
    def tdx_to_plate(arrivals: List[Dict], positions: List[Dict] = None) -> str:
        """
        Transform TDX data to yunbus ?plate format

        Returns:
            Pipe-separated: direction_stopId_plate_atStopFlag_0|...
        """
        if not arrivals:
            return ""

        records = []
        for arrival in arrivals:
            direction = arrival.get('Direction', 0)
            stop_uid = arrival.get('StopUID', '')
            plate = arrival.get('PlateNumb', '')
            estimate_time = arrival.get('EstimateTime', -1)

            # atStopFlag: 1 if arriving now (EstimateTime == 0), else 0
            at_stop_flag = 1 if estimate_time == 0 else 0

            if plate:  # Only include if plate number exists
                record = f"{direction}_{stop_uid}_{plate}_{at_stop_flag}_0"
                records.append(record)

        return '|'.join(records)

    @staticmethod
    def tdx_to_stop_json(stops: List[Dict], stop_of_route: List[Dict] = None) -> Dict:
        """
        Transform TDX stops to JSON format

        Args:
            stops: TDX Stop response
            stop_of_route: TDX StopOfRoute response (includes sequence)

        Returns:
            {
                "routeId": "709",
                "stops": {
                    "0": [...],
                    "1": [...]
                }
            }
        """
        if not stops:
            return {"routeId": "", "stops": {}}

        # Build sequence lookup
        seq_lookup = {}
        if stop_of_route:
            for item in stop_of_route:
                stop_uid = item.get('StopUID', '')
                direction = item.get('Direction', 0)
                sequence = item.get('StopSequence', 0)
                seq_lookup[f"{stop_uid}_{direction}"] = sequence

        # Group by direction
        by_direction = {}
        route_id = ""

        for stop in stops:
            stop_uid = stop.get('StopUID', '')
            stop_name = stop.get('StopName', {}).get('Zh_tw', '')
            direction = 0  # Default direction

            # Try to find direction from stop_of_route
            for d in [0, 1]:
                if f"{stop_uid}_{d}" in seq_lookup:
                    direction = d
                    break

            seq = seq_lookup.get(f"{stop_uid}_{direction}", 0)

            if direction not in by_direction:
                by_direction[direction] = []

            by_direction[direction].append({
                "id": stop_uid,
                "name": stop_name,
                "seq": seq
            })

        # Sort by sequence
        for direction in by_direction:
            by_direction[direction].sort(key=lambda x: x['seq'])

        return {
            "routeId": route_id,
            "stops": {str(k): v for k, v in by_direction.items()}
        }

    @staticmethod
    def tdx_to_mapstop_json(stops: List[Dict], stop_of_route: List[Dict] = None) -> Dict:
        """
        Transform TDX stops to map coordinates format
        """
        if not stops:
            return {"routeId": "", "stops": []}

        # Find directions from stop_of_route
        stop_directions = {}
        if stop_of_route:
            for item in stop_of_route:
                stop_uid = item.get('StopUID', '')
                direction = item.get('Direction', 0)
                stop_directions[stop_uid] = direction

        result_stops = []
        for stop in stops:
            stop_uid = stop.get('StopUID', '')
            position = stop.get('StopPosition', {})
            lat = position.get('PositionLat')
            lng = position.get('PositionLon')
            direction = stop_directions.get(stop_uid, 0)

            if lat and lng:
                result_stops.append({
                    "id": stop_uid,
                    "lat": lat,
                    "lng": lng,
                    "dir": direction
                })

        return {
            "routeId": "",
            "stops": result_stops
        }

    @staticmethod
    def tdx_to_mapshape_json(shapes: List[Dict]) -> Dict:
        """
        Transform TDX route shape to map path format
        """
        if not shapes:
            return {"routeId": "", "shapes": {}}

        result = {}
        route_id = ""

        for shape in shapes:
            direction = shape.get('Direction', 0)
            geometry = shape.get('Geometry', '')

            if not geometry:
                continue

            # Parse LINESTRING(121.123 24.456, 121.124 24.457, ...)
            if geometry.startswith('LINESTRING('):
                coords_str = geometry[11:-1]  # Remove "LINESTRING(" and ")"
                points = []
                for coord_pair in coords_str.split(', '):
                    parts = coord_pair.split(' ')
                    if len(parts) == 2:
                        lng, lat = float(parts[0]), float(parts[1])
                        points.append([lng, lat])

                result[str(direction)] = points

        return {
            "routeId": route_id,
            "shapes": result
        }

    @staticmethod
    def tdx_to_mapbus_json(positions: List[Dict]) -> Dict:
        """
        Transform TDX real-time positions to map bus format
        """
        if not positions:
            return {"routeId": "", "buses": []}

        buses = []
        for pos in positions:
            plate = pos.get('PlateNumb', '')
            direction = pos.get('Direction', 0)
            bus_pos = pos.get('BusPosition', {})
            lat = bus_pos.get('PositionLat')
            lng = bus_pos.get('PositionLon')
            speed = pos.get('Speed', 0)
            azimuth = pos.get('Azimuth', 0)
            update_time = pos.get('UpdateTime', '')

            if lat and lng:
                buses.append({
                    "plate": plate,
                    "dir": direction,
                    "lat": lat,
                    "lng": lng,
                    "speed": speed,
                    "azimuth": azimuth,
                    "updateTime": update_time
                })

        return {
            "routeId": "",
            "buses": buses
        }

    @staticmethod
    def tdx_to_route_list_json(routes: List[Dict], city: str) -> Dict:
        """
        Transform TDX routes to route list format
        """
        if not routes:
            return {"city": city, "routes": []}

        result_routes = []
        for route in routes:
            route_id = route.get('RouteID', '')
            route_name = route.get('RouteName', {}).get('Zh_tw', '')

            # Get departure/destination from SubRoutes
            sub_routes = route.get('SubRoutes', [])
            from_stop = ""
            to_stop = ""
            if sub_routes:
                sub = sub_routes[0]
                from_stop = sub.get('DepartureStopNameZh', '')
                to_stop = sub.get('DestinationStopNameZh', '')

            result_routes.append({
                "id": route_id,
                "name": route_name,
                "from": from_stop,
                "to": to_stop
            })

        return {
            "city": city,
            "routes": result_routes
        }
