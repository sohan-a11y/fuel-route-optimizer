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
        "fuel_grade": "diesel",
        "stop_duration_mins": 15,
        "icon": "🚛",
    },
    "car": {
        "name": "Passenger Car (Sedan)",
        "description": "Standard gasoline passenger sedan",
        "max_range_miles": 420.0,
        "fuel_efficiency_mpg": 30.0,
        "tank_capacity_gallons": 14.0,
        "fuel_grade": "regular",
        "stop_duration_mins": 8,
        "icon": "🚗",
    },
    "suv": {
        "name": "SUV / Light Truck",
        "description": "Full-size SUV or pickup truck",
        "max_range_miles": 440.0,
        "fuel_efficiency_mpg": 20.0,
        "tank_capacity_gallons": 22.0,
        "fuel_grade": "regular",
        "stop_duration_mins": 8,
        "icon": "🚙",
    },
    "bike": {
        "name": "Motorcycle / Bike",
        "description": "Standard highway touring motorcycle",
        "max_range_miles": 200.0,
        "fuel_efficiency_mpg": 45.0,
        "tank_capacity_gallons": 4.5,
        "fuel_grade": "regular",
        "stop_duration_mins": 5,
        "icon": "🏍️",
    },
}

# Fuel Grade Multipliers relative to OPIS Wholesale Diesel Base
FUEL_GRADE_MULTIPLIERS: Dict[str, Decimal] = {
    "diesel": Decimal("1.000"),
    "regular": Decimal("0.920"),  # ~8% lower than commercial diesel
    "premium": Decimal("1.080"),  # ~8% higher than commercial diesel
}

# EPA Carbon Emission Factors (kg CO2 per gallon)
EMISSION_FACTORS: Dict[str, float] = {
    "diesel": 10.180,
    "regular": 8.887,
    "premium": 8.887,
}

HIGH_TAX_STATES = {"CA", "PA", "WA", "IL", "NY", "CT"}
LOW_TAX_STATES = {"MO", "MS", "TX", "OK", "AZ", "VA", "SC", "TN"}

DEFAULT_MAX_RANGE = getattr(settings, "VEHICLE_MAX_RANGE_MILES", 500.0)
DEFAULT_MPG = getattr(settings, "VEHICLE_FUEL_EFFICIENCY_MPG", 10.0)
BBOX_BUFFER_DEG = 0.35  # ~25 miles bounding box query margin


def get_vehicle_specs(
    vehicle_type: str = "truck",
    custom_range: Optional[float] = None,
    custom_mpg: Optional[float] = None,
    custom_capacity: Optional[float] = None,
    custom_fuel_grade: Optional[str] = None,
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

    if custom_fuel_grade and custom_fuel_grade.lower() in FUEL_GRADE_MULTIPLIERS:
        profile["fuel_grade"] = custom_fuel_grade.lower()

    profile["vehicle_type"] = v_type if v_type in VEHICLE_PROFILES else "custom"
    return profile


def optimize_fuel_stops(
    route_data: Dict[str, Any],
    vehicle_type: str = "truck",
    optimization_strategy: str = "lowest_cost",
    initial_fuel_percent: float = 100.0,
    reserve_fuel_percent: float = 8.0,
    max_detour_miles: float = 5.0,
    include_detour_cost: bool = True,
    preferred_brands: Optional[List[str]] = None,
    fleet_discount_cents: float = 0.0,
    fuel_grade: Optional[str] = None,
    compare_strategies: bool = False,
    custom_range: Optional[float] = None,
    custom_mpg: Optional[float] = None,
    custom_capacity: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Comprehensive Fuel Route Optimization Engine supporting:
    - Multi-Vehicle Profiles (Truck, Car, SUV, Bike, Custom)
    - Optimization Strategies ('lowest_cost', 'minimum_stops', 'balanced', 'conservative')
    - Departure Fuel Level (% of full tank)
    - Safety Reserve Fuel Buffer (% reserve)
    - Off-Highway Detour limits and detour fuel cost penalty
    - Preferred Brand loyalty/fleet discounts
    - State Fuel Tax Border Arbitrage
    - Physical Tank Capacity constraint enforcement (never overflows tank)
    - Carbon Footprint (CO2 kg & lbs) and Tree Offset Estimation
    - DOT Hours of Service (HOS) 30-min Rest Break Alignment
    - Multi-Strategy Comparison Matrix
    """
    ensure_fuel_stations_loaded()

    specs = get_vehicle_specs(vehicle_type, custom_range, custom_mpg, custom_capacity, fuel_grade)
    max_range = specs["max_range_miles"]
    mpg = specs["fuel_efficiency_mpg"]
    tank_capacity = specs["tank_capacity_gallons"]
    active_fuel_grade = specs.get("fuel_grade", "diesel")
    stop_duration_mins = specs.get("stop_duration_mins", 10)

    total_miles = float(route_data["total_distance_miles"])
    driving_duration_hours = float(route_data.get("total_duration_hours", 0.0))
    avg_speed_mph = (total_miles / driving_duration_hours) if driving_duration_hours > 0 else 60.0
    coordinates = route_data["coordinates"]

    if not coordinates or len(coordinates) < 2:
        raise ValueError("Invalid route coordinates provided.")

    total_gallons_needed = round(total_miles / mpg, 2)

    # Initial fuel state
    initial_pct = max(10.0, min(100.0, float(initial_fuel_percent)))
    initial_range = round(max_range * (initial_pct / 100.0), 1)
    initial_gallons = round(tank_capacity * (initial_pct / 100.0), 2)

    # Reserve buffer
    reserve_pct = max(5.0, min(25.0, float(reserve_fuel_percent)))
    reserve_buffer_miles = round(max_range * (reserve_pct / 100.0), 1)

    # Normalize strategy
    strategy = (optimization_strategy or "lowest_cost").strip().lower()
    if strategy not in ["lowest_cost", "minimum_stops", "balanced", "conservative"]:
        strategy = "lowest_cost"

    # Environmental ESG Metrics
    co2_factor = EMISSION_FACTORS.get(active_fuel_grade, 10.180)
    carbon_kg = round(total_gallons_needed * co2_factor, 1)
    carbon_lbs = round(carbon_kg * 2.20462, 1)
    trees_needed = round(carbon_kg / 21.77, 1)

    # Step 1: Candidate stations along highway corridor
    grade_multiplier = FUEL_GRADE_MULTIPLIERS.get(active_fuel_grade, Decimal("1.000"))
    candidate_stations = _find_candidate_stations_along_route(
        coordinates=coordinates,
        total_miles=total_miles,
        max_detour_miles=max_detour_miles,
        mpg=mpg,
        include_detour_cost=include_detour_cost,
        preferred_brands=preferred_brands,
        fleet_discount_cents=fleet_discount_cents,
        grade_multiplier=grade_multiplier,
    )

    if not candidate_stations and max_detour_miles < 10.0:
        logger.warning("No stations found within initial corridor. Expanding to 10 miles...")
        candidate_stations = _find_candidate_stations_along_route(
            coordinates=coordinates,
            total_miles=total_miles,
            max_detour_miles=10.0,
            mpg=mpg,
            include_detour_cost=include_detour_cost,
            preferred_brands=preferred_brands,
            fleet_discount_cents=fleet_discount_cents,
            grade_multiplier=grade_multiplier,
        )

    # Step 2: Deduplicate close stations (keep best score within 2-mile window)
    deduped_stations = _deduplicate_nearby_stations(candidate_stations, min_gap_miles=2.0)

    # Check if trip completes within initial starting range
    if total_miles <= initial_range:
        reference_price = (
            min(s["retail_price"] for s in candidate_stations)
            if candidate_stations
            else Decimal("3.250") * grade_multiplier
        )
        total_cost = round(Decimal(str(total_gallons_needed)) * reference_price, 2)

        return {
            "vehicle": specs,
            "strategy": strategy,
            "initial_fuel_state": {
                "initial_fuel_percent": initial_pct,
                "initial_fuel_gallons": initial_gallons,
                "initial_range_miles": initial_range,
            },
            "parameters": {
                "max_range_miles": max_range,
                "fuel_efficiency_mpg": mpg,
                "tank_capacity_gallons": tank_capacity,
                "fuel_grade": active_fuel_grade,
                "reserve_fuel_percent": reserve_pct,
                "reserve_buffer_miles": reserve_buffer_miles,
                "max_detour_miles": max_detour_miles,
                "include_detour_cost": include_detour_cost,
            },
            "environmental_impact": {
                "carbon_emissions_kg": carbon_kg,
                "carbon_emissions_lbs": carbon_lbs,
                "trees_offset_per_year": trees_needed,
                "fuel_grade": active_fuel_grade,
            },
            "trip_duration": {
                "driving_hours": driving_duration_hours,
                "refueling_hours": 0.0,
                "total_hours": driving_duration_hours,
                "duration_formatted": route_data.get("duration_formatted", ""),
            },
            "total_distance_miles": total_miles,
            "total_duration_hours": driving_duration_hours,
            "duration_formatted": route_data["duration_formatted"],
            "fuel_efficiency_mpg": mpg,
            "vehicle_max_range_miles": max_range,
            "tank_capacity_gallons": tank_capacity,
            "total_gallons_consumed": total_gallons_needed,
            "total_fuel_cost": float(total_cost),
            "fuel_stops_count": 0,
            "fuel_stops": [],
            "note": (
                f"Trip distance of {total_miles:.1f} miles is within the vehicle's departure range "
                f"of {initial_range:.1f} miles ({initial_pct:.0f}% fuel tank on {specs['name']}). "
                f"No mid-route refueling stops required. Fuel cost calculated at ${reference_price:.3f}/gal."
            ),
            "route_geometry": route_data["geojson_geometry"],
        }

    # Step 3: Run Multi-Option Refueling Algorithm for chosen strategy
    stops, total_cost = _calculate_optimal_stops(
        stations=deduped_stations,
        total_miles=total_miles,
        max_range=max_range,
        mpg=mpg,
        tank_capacity=tank_capacity,
        initial_range=initial_range,
        reserve_buffer=reserve_buffer_miles,
        strategy=strategy,
        avg_speed_mph=avg_speed_mph,
        stop_duration_mins=stop_duration_mins,
    )

    total_refuel_mins = len(stops) * stop_duration_mins
    total_trip_hours = round(driving_duration_hours + (total_refuel_mins / 60.0), 2)

    result_dict: Dict[str, Any] = {
        "vehicle": specs,
        "strategy": strategy,
        "initial_fuel_state": {
            "initial_fuel_percent": initial_pct,
            "initial_fuel_gallons": initial_gallons,
            "initial_range_miles": initial_range,
        },
        "parameters": {
            "max_range_miles": max_range,
            "fuel_efficiency_mpg": mpg,
            "tank_capacity_gallons": tank_capacity,
            "fuel_grade": active_fuel_grade,
            "reserve_fuel_percent": reserve_pct,
            "reserve_buffer_miles": reserve_buffer_miles,
            "max_detour_miles": max_detour_miles,
            "include_detour_cost": include_detour_cost,
            "preferred_brands": preferred_brands or [],
            "fleet_discount_cents": fleet_discount_cents,
        },
        "environmental_impact": {
            "carbon_emissions_kg": carbon_kg,
            "carbon_emissions_lbs": carbon_lbs,
            "trees_offset_per_year": trees_needed,
            "fuel_grade": active_fuel_grade,
        },
        "trip_duration": {
            "driving_hours": driving_duration_hours,
            "refueling_hours": round(total_refuel_mins / 60.0, 2),
            "total_hours": total_trip_hours,
            "duration_formatted": route_data.get("duration_formatted", ""),
        },
        "total_distance_miles": total_miles,
        "total_duration_hours": total_trip_hours,
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

    # Step 4: Multi-Strategy Comparison Matrix (if requested)
    if compare_strategies:
        comparison_matrix = []
        for strat_name in ["lowest_cost", "minimum_stops", "balanced", "conservative"]:
            c_stops, c_cost = _calculate_optimal_stops(
                stations=deduped_stations,
                total_miles=total_miles,
                max_range=max_range,
                mpg=mpg,
                tank_capacity=tank_capacity,
                initial_range=initial_range,
                reserve_buffer=reserve_buffer_miles,
                strategy=strat_name,
                avg_speed_mph=avg_speed_mph,
                stop_duration_mins=stop_duration_mins,
            )
            c_trip_hours = round(driving_duration_hours + (len(c_stops) * stop_duration_mins / 60.0), 2)
            comparison_matrix.append({
                "strategy": strat_name,
                "display_name": strat_name.replace("_", " ").title(),
                "fuel_stops_count": len(c_stops),
                "total_fuel_cost": float(round(c_cost, 2)),
                "total_trip_hours": c_trip_hours,
            })

        min_cost = min(item["total_fuel_cost"] for item in comparison_matrix)
        for item in comparison_matrix:
            item["difference_vs_lowest_cost"] = round(item["total_fuel_cost"] - min_cost, 2)

        result_dict["strategy_comparison"] = comparison_matrix

    return result_dict


def _find_candidate_stations_along_route(
    coordinates: List[List[float]],
    total_miles: float,
    max_detour_miles: float = 5.0,
    mpg: float = 10.0,
    include_detour_cost: bool = True,
    preferred_brands: Optional[List[str]] = None,
    fleet_discount_cents: float = 0.0,
    grade_multiplier: Decimal = Decimal("1.000"),
) -> List[Dict[str, Any]]:
    """Projects stations within spatial corridor and computes effective prices."""
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

    max_detour_deg = max_detour_miles / 69.0
    brand_keywords = [b.lower().strip() for b in preferred_brands] if preferred_brands else []
    discount_dec = Decimal(str(round(fleet_discount_cents, 4)))

    candidates = []
    for st in stations_qs:
        pt = Point(st["longitude"], st["latitude"])
        dist_deg = line.distance(pt)
        detour_miles = dist_deg * 69.0

        if detour_miles <= max_detour_miles:
            norm_pos = line.project(pt, normalized=True)
            mile = norm_pos * total_miles
            if 0 < mile < total_miles:
                # Base price scaled by fuel grade
                base_price = round(st["retail_price"] * grade_multiplier, 3)
                effective_price = base_price

                # Apply brand loyalty / fleet discount
                st_name_lower = st["name"].lower()
                is_preferred = any(brand in st_name_lower for brand in brand_keywords) if brand_keywords else False
                if is_preferred and discount_dec > 0:
                    effective_price = max(Decimal("1.50"), effective_price - discount_dec)

                # Factor in round-trip detour fuel burn cost
                detour_fuel_cost = Decimal("0.00")
                if include_detour_cost and detour_miles > 0.5:
                    detour_gallons = Decimal(str(round((2 * detour_miles) / mpg, 4)))
                    detour_fuel_cost = round(detour_gallons * base_price, 2)
                    effective_price += round(detour_fuel_cost / Decimal("20.0"), 3)

                candidates.append({
                    "station_id": st["opis_id"],
                    "name": st["name"],
                    "address": st["address"],
                    "city": st["city"],
                    "state": st["state"],
                    "rack_id": st["rack_id"],
                    "retail_price": base_price,
                    "effective_price": effective_price,
                    "detour_miles": round(detour_miles, 2),
                    "is_preferred_brand": is_preferred,
                    "latitude": st["latitude"],
                    "longitude": st["longitude"],
                    "mile_marker": round(mile, 2),
                })

    candidates.sort(key=lambda s: s["mile_marker"])
    return candidates


def _deduplicate_nearby_stations(
    stations: List[Dict[str, Any]], min_gap_miles: float = 2.0
) -> List[Dict[str, Any]]:
    """Deduplicates closely grouped stations (same exit) keeping the most cost-effective."""
    if not stations:
        return []

    filtered = []
    for s in stations:
        if not filtered or s["mile_marker"] - filtered[-1]["mile_marker"] > min_gap_miles:
            filtered.append(s)
        else:
            if s["effective_price"] < filtered[-1]["effective_price"]:
                filtered[-1] = s
    return filtered


def _calculate_optimal_stops(
    stations: List[Dict[str, Any]],
    total_miles: float,
    max_range: float = 500.0,
    mpg: float = 10.0,
    tank_capacity: float = 50.0,
    initial_range: float = 500.0,
    reserve_buffer: float = 40.0,
    strategy: str = "lowest_cost",
    avg_speed_mph: float = 60.0,
    stop_duration_mins: int = 15,
) -> Tuple[List[Dict[str, Any]], Decimal]:
    """
    Core refueling optimizer supporting lowest_cost, minimum_stops, balanced, and conservative strategies.
    Ensures refuels never exceed physical tank capacity and includes HOS rest break flags.
    """
    curr_mile = 0.0
    tank_miles = initial_range
    stops = []
    total_cost = Decimal("0.00")
    last_hos_break_hours = 0.0

    # Strategy tuning parameters
    if strategy == "conservative":
        effective_reserve = max(reserve_buffer, max_range * 0.18)
        search_window_min_fraction = 0.40
    elif strategy == "minimum_stops":
        effective_reserve = max(15.0, reserve_buffer * 0.6)
        search_window_min_fraction = 0.75  # Push deep into tank
    elif strategy == "balanced":
        effective_reserve = max(20.0, reserve_buffer * 0.8)
        search_window_min_fraction = 0.55
    else:  # lowest_cost
        effective_reserve = reserve_buffer
        search_window_min_fraction = 0.45

    while curr_mile + tank_miles < total_miles:
        safe_max_mile = curr_mile + tank_miles - effective_reserve
        reachable = [s for s in stations if curr_mile < s["mile_marker"] <= safe_max_mile]

        if not reachable:
            reachable = [s for s in stations if curr_mile < s["mile_marker"] <= curr_mile + tank_miles]
            if not reachable:
                logger.warning(f"No fuel station found within {tank_miles} miles of mile {curr_mile:.1f}")
                break

        preferred_min_mile = curr_mile + (max_range * search_window_min_fraction)
        window = [s for s in reachable if s["mile_marker"] >= preferred_min_mile]
        if not window:
            window = reachable

        # Strategy station selection
        if strategy == "minimum_stops":
            min_p = min(s["effective_price"] for s in window)
            acceptable_stations = [s for s in window if s["effective_price"] <= min_p * Decimal("1.08")]
            best_station = max(acceptable_stations, key=lambda s: s["mile_marker"])
        elif strategy == "balanced":
            def balanced_score(st):
                dist_driven = st["mile_marker"] - curr_mile
                price_factor = float(st["effective_price"]) * 100.0
                dist_reward = (dist_driven / max_range) * 20.0
                return price_factor - dist_reward

            best_station = min(window, key=balanced_score)
        else:  # lowest_cost & conservative
            def cost_score(st):
                score = st["effective_price"]
                if st["state"] in LOW_TAX_STATES and st["mile_marker"] > curr_mile + (max_range * 0.6):
                    score -= Decimal("0.08")
                return score

            best_station = min(window, key=cost_score)

        leg_distance = best_station["mile_marker"] - curr_mile
        gallons_needed = min(tank_capacity, leg_distance / mpg)
        gallons = round(gallons_needed, 2)
        price = best_station["retail_price"]
        cost = round(Decimal(str(gallons)) * price, 2)
        total_cost += cost

        # Fuel gauge metrics
        arrival_gallons = max(0.0, round(tank_capacity - gallons_needed, 2))
        arrival_pct = round((arrival_gallons / tank_capacity) * 100, 1)

        # Hours of Service (HOS) & timing
        est_arrival_hours = round(best_station["mile_marker"] / avg_speed_mph, 1)
        driving_since_break = est_arrival_hours - last_hos_break_hours
        hos_break_recommended = False
        hos_reason = None
        if driving_since_break >= 7.5:
            hos_break_recommended = True
            hos_reason = (
                f"Cumulative driving time is ~{est_arrival_hours:.1f} hours ({driving_since_break:.1f} hrs since departure/break). "
                "Recommended 30-minute DOT/FMCSA rest break aligns with this refueling stop."
            )
            last_hos_break_hours = est_arrival_hours

        stop_entry = {
            "stop_number": len(stops) + 1,
            "station_id": best_station["station_id"],
            "truckstop_name": best_station["name"],
            "address": best_station["address"],
            "city": best_station["city"],
            "state": best_station["state"],
            "retail_price_per_gallon": float(price),
            "effective_price_per_gallon": float(round(best_station["effective_price"], 3)),
            "mile_marker": best_station["mile_marker"],
            "distance_from_previous_stop_miles": round(leg_distance, 1),
            "detour_miles": best_station.get("detour_miles", 0.0),
            "arrival_fuel_percent": arrival_pct,
            "gallons_refueled": gallons,
            "cost_at_stop": float(cost),
            "estimated_arrival_hours": est_arrival_hours,
            "estimated_refuel_duration_minutes": stop_duration_mins,
            "hos_rest_break_recommended": hos_break_recommended,
            "coordinates": {
                "latitude": best_station["latitude"],
                "longitude": best_station["longitude"],
            },
        }
        if hos_reason:
            stop_entry["hos_reason"] = hos_reason

        stops.append(stop_entry)
        curr_mile = best_station["mile_marker"]
        tank_miles = max_range

    # Account for fuel burned on final leg to destination
    if stops:
        final_leg_distance = total_miles - curr_mile
        final_leg_gallons = round(final_leg_distance / mpg, 2)
        last_price = Decimal(str(stops[-1]["retail_price_per_gallon"]))
        final_leg_cost = round(Decimal(str(final_leg_gallons)) * last_price, 2)

        total_cost += final_leg_cost
        remaining_fuel = round(tank_capacity - final_leg_gallons, 2)

        stops[-1]["final_leg"] = {
            "distance_to_destination_miles": round(final_leg_distance, 1),
            "fuel_consumed_to_destination_gallons": final_leg_gallons,
            "final_leg_fuel_cost": float(final_leg_cost),
            "remaining_fuel_at_destination_gallons": max(0.0, remaining_fuel),
        }

    return stops, total_cost
