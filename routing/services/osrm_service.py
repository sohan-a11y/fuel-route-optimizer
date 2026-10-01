import logging
from typing import Dict, Any, Tuple
import requests
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"
METERS_TO_MILES = 0.000621371192237334


def get_osrm_route(
    start_lat: float, start_lon: float, finish_lat: float, finish_lon: float
) -> Tuple[Dict[str, Any], int]:
    """
    Fetches the driving route geometry and distance between two points using OSRM.
    Returns:
        (route_data_dict, api_calls_count)
    """
    # OSRM expects coordinates in {longitude},{latitude} order
    url = (
        f"{OSRM_BASE_URL}/{start_lon},{start_lat};{finish_lon},{finish_lat}"
        "?overview=full&geometries=geojson&steps=false"
    )

    headers = {
        "User-Agent": "DjangoFuelRouteOptimizer/1.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            error_msg = data.get("message", "No drivable route found between the specified locations.")
            logger.error(f"OSRM Routing failed: {error_msg}")
            raise ValidationError(f"Routing failed: {error_msg}")

        route = data["routes"][0]
        distance_meters = float(route["distance"])
        distance_miles = distance_meters * METERS_TO_MILES
        duration_seconds = float(route["duration"])
        duration_hours = duration_seconds / 3600.0

        geometry = route.get("geometry", {})
        coordinates = geometry.get("coordinates", [])

        if not coordinates:
            raise ValidationError("OSRM returned an empty route geometry.")

        result = {
            "total_distance_miles": round(distance_miles, 2),
            "total_duration_hours": round(duration_hours, 2),
            "duration_formatted": f"{int(duration_hours)}h {int((duration_hours % 1) * 60)}m",
            "geojson_geometry": geometry,
            "coordinates": coordinates,
        }
        return result, 1

    except requests.Timeout:
        logger.error("OSRM request timed out.")
        raise ValidationError("Routing service timed out. Please try again.")
    except requests.RequestException as e:
        logger.error(f"OSRM request exception: {e}")
        raise ValidationError(f"External routing service error: {str(e)}")
