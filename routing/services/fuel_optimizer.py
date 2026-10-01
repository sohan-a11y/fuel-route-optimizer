import logging
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
from shapely.geometry import LineString, Point
from django.conf import settings
from routing.models import FuelStation
from routing.services.data_loader import ensure_fuel_stations_loaded

logger = logging.getLogger(__name__)

# Standard Vehicle Profiles
VEHICLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "truck": {
        "name": "Commercial Truck / Semi",
        "description": "Heavy commercial truck (Assessment Default)",
        "max_range_miles": 500.0,
        "fuel_efficiency_mpg": 10.0,
        "tank_capacity_gallons": 50.0,
    },
    "car": {
        "name": "Passenger Car (Sedan)",
        "description": "Standard gasoline passenger sedan",
        "max_range_miles": 420.0,
        "fuel_efficiency_mpg": 30.0,
        "tank_capacity_gallons": 14.0,
    },
    "suv": {
        "name": "SUV / Light Truck",
        "description": "Full-size SUV or pickup truck",
        "max_range_miles": 440.0,
        "fuel_efficiency_mpg": 20.0,
        "tank_capacity_gallons": 22.0,
    },
    "bike": {
        "name": "Motorcycle / Bike",
        "description": "Standard highway touring motorcycle",
        "max_range_miles": 200.0,
        "fuel_efficiency_mpg": 45.0,
        "tank_capacity_gallons": 4.5,
    },
}

MAX_DETOUR_DEG = 0.15  # ~10 miles in degrees
BBOX_BUFFER_DEG = 0.30  # ~20 miles bounding box margin


def get_vehicle_specs(
    vehicle_type: str = "truck",
    custom_range: Optional[float] = None,
    custom_mpg: Optional[float] = None,
    custom_capacity: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolves vehicle profile and allows selective custom overrides."""
    v_type = (vehicle_type or "truck").strip().lower()
    profile = VEHICLE_PROFILES.get(v_type, VEHICLE_PROFILES["truck"]).copy()

    if custom_range is not None and custom_range > 0:
        profile["max_range_miles"] = float(custom_range)
    if custom_mpg is not None and custom_mpg > 0:
        profile["fuel_efficiency_mpg"] = float(custom_mpg)
    if custom_capacity is not None and custom_capacity > 0:
        profile["tank_capacity_gallons"] = float(custom_capacity)
    elif custom_range and custom_mpg:
        profile["tank_capacity_gallons"] = round(profile["max_range_miles"] / profile["fuel_efficiency_mpg"], 1)

    profile["vehicle_type"] = v_type if v_type in VEHICLE_PROFILES else "custom"
    return profile


def optimize_fuel_stops(
    route_data: Dict[str, Any],
    vehicle_type: str = "truck",
    custom_range: Optional[float] = None,
    custom_mpg: Optional[float] = None,
    custom_capacity: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Optimizes fuel stops along a route tailored to the vehicle profile
    (Truck, Car, SUV, Bike, or Custom).
    Ensures that refuel amounts never exceed the physical tank capacity.
    """
    ensure_fuel_stations_loaded()

    specs = get_vehicle_specs(vehicle_type, custom_range, custom_mpg, custom_capacity)
    max_range = specs["max_range_miles"]
    mpg = specs["fuel_efficiency_mpg"]
    tank_capacity = specs["tank_capacity_gallons"]

    total_miles = float(route_data["total_distance_miles"])
    coordinates = route_data["coordinates"]

    if not coordinates or len(coordinates) < 2:
        raise ValueError("Invalid route coordinates provided.")

    total_gallons_needed = round(total_miles / mpg, 2)

    # Trip within single-tank range
    if total_miles <= max_range:
        candidate_stations = _find_candidate_stations_along_route(coordinates, total_miles)
        reference_price = (
            min(s["retail_price"] for s in candidate_stations)
            if candidate_stations
            else Decimal("3.250")
        )
        total_cost = round(Decimal(str(total_gallons_needed)) * reference_price, 2)

        return {
            "vehicle": specs,
            "total_distance_miles": total_miles,
            "total_duration_hours": route_data["total_duration_hours"],
            "duration_formatted": route_data["duration_formatted"],
            "fuel_efficiency_mpg": mpg,
            "vehicle_max_range_miles": max_range,
            "tank_capacity_gallons": tank_capacity,
            "total_gallons_consumed": total_gallons_needed,
            "total_fuel_cost": float(total_cost),
            "fuel_stops_count": 0,
            "fuel_stops": [],
            "note": (
                f"Trip distance of {total_miles:.1f} miles is within the vehicle's {max_range:.0f}-mile "
                f"range ({specs['name']}). No mid-route refueling stops are strictly required. "
                f"Total fuel cost calculated at ${reference_price:.3f}/gal."
            ),
            "route_geometry": route_data["geojson_geometry"],
        }

    # Step 1: Candidate stations along the route
    candidate_stations = _find_candidate_stations_along_route(coordinates, total_miles)

    if not candidate_stations:
        logger.warning("No gas stations found within buffer of route. Expanding search radius...")
        candidate_stations = _find_candidate_stations_along_route(
            coordinates, total_miles, max_detour_deg=0.30
        )

    # Step 2: Deduplicate close stations (keep lowest price within 2-mile window)
    deduped_stations = _deduplicate_nearby_stations(candidate_stations, min_gap_miles=2.0)

    # Step 3: Run Refueling Algorithm constrained by vehicle tank capacity
    stops, total_cost = _calculate_optimal_stops(
        stations=deduped_stations,
        total_miles=total_miles,
        max_range=max_range,
        mpg=mpg,
        tank_capacity=tank_capacity,
    )

    return {
        "vehicle": specs,
        "total_distance_miles": total_miles,
        "total_duration_hours": route_data["total_duration_hours"],
        "duration_formatted": route_data["duration_formatted"],
        "fuel_efficiency_mpg": mpg,
        "vehicle_max_range_miles": max_range,
        "tank_capacity_gallons": tank_capacity,
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
    """Projects fuel stations within spatial proximity onto route polyline."""
    line = LineString(coordinates)
    min_lon, min_lat, max_lon, max_lat = line.bounds

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
    tank_capacity: float = 50.0,
) -> Tuple[List[Dict[str, Any]], Decimal]:
    """
    Selects optimal fuel stops such that:
    1. Distance between any consecutive stops (or start/finish) is <= max_range.
    2. Gallons refueled at any single stop is strictly capped at tank_capacity.
    3. Selects the most cost-effective stations in each driving segment.
    """
    curr_mile = 0.0
    tank_miles = max_range
    stops = []
    total_cost = Decimal("0.00")

    # Safety buffer before running completely empty
    safety_margin = min(20.0, max_range * 0.08)
    preferred_min_fraction = 0.50  # Start looking after half tank is consumed

    while curr_mile + tank_miles < total_miles:
        # All reachable stations within tank range
        reachable = [s for s in stations if curr_mile < s["mile_marker"] <= curr_mile + tank_miles]
        if not reachable:
            logger.warning(f"No fuel station found within {tank_miles} miles of mile {curr_mile:.1f}")
            break

        safe_max = curr_mile + tank_miles - safety_margin
        preferred_min = curr_mile + (max_range * preferred_min_fraction)

        window = [s for s in reachable if preferred_min <= s["mile_marker"] <= safe_max]
        if not window:
            window = [s for s in reachable if s["mile_marker"] <= safe_max] or reachable

        best_station = min(window, key=lambda s: s["retail_price"])

        leg_distance = best_station["mile_marker"] - curr_mile
        # Gallons needed to fill tank back up to full
        gallons_needed = min(tank_capacity, leg_distance / mpg)
        gallons = round(gallons_needed, 2)
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

    # Account for the fuel consumed on the final leg to the destination
    if stops:
        final_leg_distance = total_miles - curr_mile
        final_leg_gallons = round(final_leg_distance / mpg, 2)
        last_price = Decimal(str(stops[-1]["retail_price_per_gallon"]))
        final_leg_cost = round(Decimal(str(final_leg_gallons)) * last_price, 2)

        # Total fuel cost for the trip covers every gallon burned
        total_cost += final_leg_cost

        # Document final leg clearly without exceeding tank capacity at the last stop
        remaining_fuel_at_dest = round(tank_capacity - final_leg_gallons, 2)
        stops[-1]["final_leg"] = {
            "distance_to_destination_miles": round(final_leg_distance, 1),
            "fuel_consumed_to_destination_gallons": final_leg_gallons,
            "final_leg_fuel_cost": float(final_leg_cost),
            "remaining_fuel_at_destination_gallons": max(0.0, remaining_fuel_at_dest),
        }

    return stops, total_cost
