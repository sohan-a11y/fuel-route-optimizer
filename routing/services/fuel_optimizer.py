import logging
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from shapely.geometry import LineString, Point
from django.conf import settings
from routing.models import FuelStation
from routing.services.data_loader import ensure_fuel_stations_loaded

logger = logging.getLogger(__name__)

# Constants
DEFAULT_MAX_RANGE = getattr(settings, "VEHICLE_MAX_RANGE_MILES", 500.0)  # 500 miles
DEFAULT_MPG = getattr(settings, "VEHICLE_FUEL_EFFICIENCY_MPG", 10.0)  # 10 mpg
MAX_DETOUR_DEG = 0.15  # ~10 miles in degrees
BBOX_BUFFER_DEG = 0.30  # ~20 miles bounding box margin


def optimize_fuel_stops(
    route_data: Dict[str, Any],
    max_range: float = DEFAULT_MAX_RANGE,
    mpg: float = DEFAULT_MPG,
) -> Dict[str, Any]:
    """
    Optimizes fuel stops along a route to minimize fuel costs.
    
    Args:
        route_data: Output dictionary from OSRM containing 'total_distance_miles',
                    'coordinates', and 'geojson_geometry'.
        max_range: Maximum vehicle driving range on a full tank (default: 500 miles).
        mpg: Fuel efficiency in miles per gallon (default: 10 mpg).

    Returns:
        Structured dictionary containing:
        - route summary & geojson geometry
        - optimal fuel stops list with station details, gallons refueled, and cost
        - total fuel consumed (gallons)
        - total money spent on fuel
    """
    ensure_fuel_stations_loaded()

    total_miles = float(route_data["total_distance_miles"])
    coordinates = route_data["coordinates"]

    if not coordinates or len(coordinates) < 2:
        raise ValueError("Invalid route coordinates provided.")

    total_gallons_needed = round(total_miles / mpg, 2)

    # If the trip is within single-tank range (<= 500 miles)
    if total_miles <= max_range:
        # Check cheapest station along the route for reference fuel cost
        candidate_stations = _find_candidate_stations_along_route(coordinates, total_miles)
        reference_price = (
            min(s["retail_price"] for s in candidate_stations)
            if candidate_stations
            else Decimal("3.250")
        )
        total_cost = round(Decimal(str(total_gallons_needed)) * reference_price, 2)

        return {
            "total_distance_miles": total_miles,
            "total_duration_hours": route_data["total_duration_hours"],
            "duration_formatted": route_data["duration_formatted"],
            "fuel_efficiency_mpg": mpg,
            "vehicle_max_range_miles": max_range,
            "total_gallons_consumed": total_gallons_needed,
            "total_fuel_cost": float(total_cost),
            "fuel_stops_count": 0,
            "fuel_stops": [],
            "note": (
                f"Trip distance of {total_miles:.1f} miles is within the vehicle's 500-mile "
                "range. No mid-route refueling stops are strictly required. "
                f"Total fuel cost calculated at ${reference_price:.3f}/gal."
            ),
            "route_geometry": route_data["geojson_geometry"],
        }

    # Step 1: Find all candidate stations along the route geometry
    candidate_stations = _find_candidate_stations_along_route(coordinates, total_miles)

    if not candidate_stations:
        logger.warning("No gas stations found within buffer of route. Expanding search radius...")
        candidate_stations = _find_candidate_stations_along_route(
            coordinates, total_miles, max_detour_deg=0.30
        )

    # Step 2: Deduplicate close stations (keep lowest price within 2-mile window)
    deduped_stations = _deduplicate_nearby_stations(candidate_stations, min_gap_miles=2.0)

    # Step 3: Run the Optimal Refueling Algorithm
    stops, total_cost = _calculate_optimal_stops(
        stations=deduped_stations,
        total_miles=total_miles,
        max_range=max_range,
        mpg=mpg,
    )

    return {
        "total_distance_miles": total_miles,
        "total_duration_hours": route_data["total_duration_hours"],
        "duration_formatted": route_data["duration_formatted"],
        "fuel_efficiency_mpg": mpg,
        "vehicle_max_range_miles": max_range,
        "total_gallons_consumed": total_gallons_needed,
        "total_fuel_cost": float(round(total_cost, 2)),
        "fuel_stops_count": len(stops),
        "fuel_stops": stops,
        "route_geometry": route_data["geojson_geometry"],
    }


def _find_candidate_stations_along_route(
    coordinates: List[List[float]],
    total_miles: float,
    max_detour_deg: float = MAX_DETOUR_DEG,
) -> List[Dict[str, Any]]:
    """
    Projects all fuel stations within spatial proximity onto the route polyline.
    Returns a sorted list of candidate stations with their mile marker.
    """
    line = LineString(coordinates)
    min_lon, min_lat, max_lon, max_lat = line.bounds

    # Database spatial bounding box query
    stations_qs = FuelStation.objects.filter(
        latitude__gte=min_lat - BBOX_BUFFER_DEG,
        latitude__lte=max_lat + BBOX_BUFFER_DEG,
        longitude__gte=min_lon - BBOX_BUFFER_DEG,
        longitude__lte=max_lon + BBOX_BUFFER_DEG,
    ).values(
        "opis_id", "name", "address", "city", "state", "rack_id",
        "retail_price", "latitude", "longitude"
    )

    candidates = []
    for st in stations_qs:
        pt = Point(st["longitude"], st["latitude"])
        dist_deg = line.distance(pt)
        if dist_deg <= max_detour_deg:
            norm_pos = line.project(pt, normalized=True)
            mile = norm_pos * total_miles
            if 0 < mile < total_miles:
                candidates.append({
                    "station_id": st["opis_id"],
                    "name": st["name"],
                    "address": st["address"],
                    "city": st["city"],
                    "state": st["state"],
                    "rack_id": st["rack_id"],
                    "retail_price": st["retail_price"],
                    "latitude": st["latitude"],
                    "longitude": st["longitude"],
                    "mile_marker": round(mile, 2),
                    "off_route_distance_miles": round(dist_deg * 69.0, 2),
                })

    candidates.sort(key=lambda s: s["mile_marker"])
    return candidates


def _deduplicate_nearby_stations(
    stations: List[Dict[str, Any]], min_gap_miles: float = 2.0
) -> List[Dict[str, Any]]:
    """Clusters stations that are very close (same exit) and picks the cheapest one."""
    if not stations:
        return []

    filtered = []
    for s in stations:
        if not filtered or s["mile_marker"] - filtered[-1]["mile_marker"] > min_gap_miles:
            filtered.append(s)
        else:
            if s["retail_price"] < filtered[-1]["retail_price"]:
                filtered[-1] = s
    return filtered


def _calculate_optimal_stops(
    stations: List[Dict[str, Any]],
    total_miles: float,
    max_range: float = 500.0,
    mpg: float = 10.0,
) -> Tuple[List[Dict[str, Any]], Decimal]:
    """
    Selects optimal fuel stops such that:
    1. Distance between any consecutive stops (or start/finish) is <= max_range (500 miles).
    2. Selected stations have the lowest retail prices in each driving segment.
    3. Calculates exact gallons refueled and cost per stop.
    """
    curr_mile = 0.0
    tank_miles = max_range
    stops = []
    total_cost = Decimal("0.00")

    while curr_mile + tank_miles < total_miles:
        # All reachable stations within tank range
        reachable = [s for s in stations if curr_mile < s["mile_marker"] <= curr_mile + tank_miles]
        if not reachable:
            # Fallback: station at maximum reach
            logger.warning(f"No fuel station found within {tank_miles} miles of mile {curr_mile:.1f}")
            break

        # Practical refueling window: stop between 250 miles and (max_range - 10) miles
        # to prevent unnecessary frequent stopping while maintaining safety margin
        safe_max = curr_mile + tank_miles - 10.0
        preferred_min = curr_mile + 250.0

        window = [s for s in reachable if s["mile_marker"] >= preferred_min and s["mile_marker"] <= safe_max]
        if not window:
            # If no station in preferred window, pick from any reachable station
            window = [s for s in reachable if s["mile_marker"] <= safe_max]
            if not window:
                window = reachable

        # Choose the cheapest station in the reachable window
        best_station = min(window, key=lambda s: s["retail_price"])

        leg_distance = best_station["mile_marker"] - curr_mile
        gallons = round(leg_distance / mpg, 2)
        price = best_station["retail_price"]
        cost = round(Decimal(str(gallons)) * price, 2)
        total_cost += cost

        stop_entry = {
            "stop_number": len(stops) + 1,
            "station_id": best_station["station_id"],
            "truckstop_name": best_station["name"],
            "address": best_station["address"],
            "city": best_station["city"],
            "state": best_station["state"],
            "retail_price_per_gallon": float(price),
            "mile_marker": best_station["mile_marker"],
            "distance_from_previous_stop_miles": round(leg_distance, 1),
            "gallons_refueled": gallons,
            "cost_at_stop": float(cost),
            "coordinates": {
                "latitude": best_station["latitude"],
                "longitude": best_station["longitude"],
            },
        }
        stops.append(stop_entry)
        curr_mile = best_station["mile_marker"]
        tank_miles = max_range

    # Account for the final leg from last stop to destination
    if stops:
        final_leg_distance = total_miles - curr_mile
        final_gallons = round(final_leg_distance / mpg, 2)
        last_price = Decimal(str(stops[-1]["retail_price_per_gallon"]))
        final_cost = round(Decimal(str(final_gallons)) * last_price, 2)

        total_cost += final_cost
        # The fuel to complete the trip was topped off at the final stop
        stops[-1]["gallons_refueled"] = round(stops[-1]["gallons_refueled"] + final_gallons, 2)
        stops[-1]["cost_at_stop"] = round(float(Decimal(str(stops[-1]["cost_at_stop"])) + final_cost), 2)
        stops[-1]["note"] = (
            f"Includes {final_gallons} gallons to cover the final {final_leg_distance:.1f}-mile "
            "leg to the destination."
        )

    return stops, total_cost
