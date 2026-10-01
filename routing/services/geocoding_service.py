import re
import logging
from typing import Tuple, Dict, Any, Union
import requests
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Bounding box for USA (including Alaska and Hawaii)
USA_LAT_MIN = 18.0
USA_LAT_MAX = 72.0
USA_LON_MIN = -180.0
USA_LON_MAX = -65.0

# Pre-cached coordinates for major US cities to avoid unnecessary external API calls
MAJOR_US_CITIES: Dict[str, Tuple[float, float, str]] = {
    # (lat, lon, formatted_name)
    "new york, ny": (40.7128, -74.0060, "New York, NY, USA"),
    "new york": (40.7128, -74.0060, "New York, NY, USA"),
    "nyc": (40.7128, -74.0060, "New York, NY, USA"),
    "los angeles, ca": (34.0522, -118.2437, "Los Angeles, CA, USA"),
    "los angeles": (34.0522, -118.2437, "Los Angeles, CA, USA"),
    "la": (34.0522, -118.2437, "Los Angeles, CA, USA"),
    "chicago, il": (41.8781, -87.6298, "Chicago, IL, USA"),
    "chicago": (41.8781, -87.6298, "Chicago, IL, USA"),
    "houston, tx": (29.7604, -95.3698, "Houston, TX, USA"),
    "houston": (29.7604, -95.3698, "Houston, TX, USA"),
    "phoenix, az": (33.4484, -112.0740, "Phoenix, AZ, USA"),
    "phoenix": (33.4484, -112.0740, "Phoenix, AZ, USA"),
    "philadelphia, pa": (39.9526, -75.1652, "Philadelphia, PA, USA"),
    "philadelphia": (39.9526, -75.1652, "Philadelphia, PA, USA"),
    "san antonio, tx": (29.4241, -98.4936, "San Antonio, TX, USA"),
    "san antonio": (29.4241, -98.4936, "San Antonio, TX, USA"),
    "san diego, ca": (32.7157, -117.1611, "San Diego, CA, USA"),
    "san diego": (32.7157, -117.1611, "San Diego, CA, USA"),
    "dallas, tx": (32.7767, -96.7970, "Dallas, TX, USA"),
    "dallas": (32.7767, -96.7970, "Dallas, TX, USA"),
    "austin, tx": (30.2672, -97.7431, "Austin, TX, USA"),
    "austin": (30.2672, -97.7431, "Austin, TX, USA"),
    "san jose, ca": (37.3382, -121.8863, "San Jose, CA, USA"),
    "san francisco, ca": (37.7749, -122.4194, "San Francisco, CA, USA"),
    "san francisco": (37.7749, -122.4194, "San Francisco, CA, USA"),
    "seattle, wa": (47.6062, -122.3321, "Seattle, WA, USA"),
    "seattle": (47.6062, -122.3321, "Seattle, WA, USA"),
    "denver, co": (39.7392, -104.9903, "Denver, CO, USA"),
    "denver": (39.7392, -104.9903, "Denver, CO, USA"),
    "boston, ma": (42.3601, -71.0589, "Boston, MA, USA"),
    "boston": (42.3601, -71.0589, "Boston, MA, USA"),
    "miami, fl": (25.7617, -80.1918, "Miami, FL, USA"),
    "miami": (25.7617, -80.1918, "Miami, FL, USA"),
    "atlanta, ga": (33.7490, -84.3880, "Atlanta, GA, USA"),
    "atlanta": (33.7490, -84.3880, "Atlanta, GA, USA"),
    "las vegas, nv": (36.1699, -115.1398, "Las Vegas, NV, USA"),
    "las vegas": (36.1699, -115.1398, "Las Vegas, NV, USA"),
    "orlando, fl": (28.5383, -81.3792, "Orlando, FL, USA"),
    "orlando": (28.5383, -81.3792, "Orlando, FL, USA"),
    "portland, or": (45.5152, -122.6784, "Portland, OR, USA"),
    "portland": (45.5152, -122.6784, "Portland, OR, USA"),
    "salt lake city, ut": (40.7608, -111.8910, "Salt Lake City, UT, USA"),
    "salt lake city": (40.7608, -111.8910, "Salt Lake City, UT, USA"),
    "kansas city, mo": (39.0997, -94.5786, "Kansas City, MO, USA"),
    "kansas city": (39.0997, -94.5786, "Kansas City, MO, USA"),
    "st. louis, mo": (38.6270, -90.1994, "St. Louis, MO, USA"),
    "saint louis, mo": (38.6270, -90.1994, "St. Louis, MO, USA"),
    "washington, dc": (38.9072, -77.0369, "Washington, DC, USA"),
    "washington dc": (38.9072, -77.0369, "Washington, DC, USA"),
}

# Runtime session cache to avoid repeating external geocoding requests
_GEOCODE_CACHE: Dict[str, Tuple[float, float, str]] = {}


def is_within_usa(lat: float, lon: float) -> bool:
    """Verifies that coordinates are geographically within the United States."""
    return USA_LAT_MIN <= lat <= USA_LAT_MAX and USA_LON_MIN <= lon <= USA_LON_MAX


def geocode_location(location: Union[str, list, dict]) -> Tuple[float, float, str, int]:
    """
    Resolves input location (string name, coordinates list/dict) to (lat, lon, formatted_address, api_calls_made).
    Ensures the location is within the USA.
    """
    api_calls_made = 0

    # Case 1: Coordinate dictionary {'lat': ..., 'lon': ...} or {'latitude': ..., 'longitude': ...}
    if isinstance(location, dict):
        lat = location.get("lat") or location.get("latitude")
        lon = location.get("lon") or location.get("lng") or location.get("longitude")
        if lat is not None and lon is not None:
            lat, lon = float(lat), float(lon)
            if not is_within_usa(lat, lon):
                raise ValidationError(f"Coordinates ({lat}, {lon}) are outside the United States.")
            return lat, lon, f"Point({lat:.4f}, {lon:.4f})", 0

    # Case 2: List or Tuple [lat, lon] or [lon, lat]
    if isinstance(location, (list, tuple)) and len(location) == 2:
        val1, val2 = float(location[0]), float(location[1])
        # Auto-detect lat/lon vs lon/lat based on USA bounds
        if USA_LAT_MIN <= val1 <= USA_LAT_MAX and USA_LON_MIN <= val2 <= USA_LON_MAX:
            lat, lon = val1, val2
        elif USA_LON_MIN <= val1 <= USA_LON_MAX and USA_LAT_MIN <= val2 <= USA_LAT_MAX:
            lon, lat = val1, val2
        else:
            raise ValidationError(f"Coordinates [{val1}, {val2}] are outside the United States.")
        return lat, lon, f"Point({lat:.4f}, {lon:.4f})", 0

    # Case 3: String representation
    if not isinstance(location, str):
        raise ValidationError(f"Invalid location format: {location}")

    query = location.strip()
    norm_query = query.lower()

    # Check comma-separated coordinate string e.g. "30.2672, -97.7431"
    coord_match = re.match(r"^([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)$", query)
    if coord_match:
        val1, val2 = float(coord_match.group(1)), float(coord_match.group(2))
        if USA_LAT_MIN <= val1 <= USA_LAT_MAX and USA_LON_MIN <= val2 <= USA_LON_MAX:
            lat, lon = val1, val2
        elif USA_LON_MIN <= val1 <= USA_LON_MAX and USA_LAT_MIN <= val2 <= USA_LAT_MAX:
            lon, lat = val1, val2
        else:
            raise ValidationError(f"Coordinates ({val1}, {val2}) are outside the United States.")
        return lat, lon, f"Point({lat:.4f}, {lon:.4f})", 0

    # Check pre-cached major US cities
    if norm_query in MAJOR_US_CITIES:
        lat, lon, label = MAJOR_US_CITIES[norm_query]
        return lat, lon, label, 0

    # Check runtime memory cache
    if norm_query in _GEOCODE_CACHE:
        lat, lon, label = _GEOCODE_CACHE[norm_query]
        return lat, lon, label, 0

    # Fallback: Query OpenStreetMap Nominatim for exact US address/city
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "countrycodes": "us",
        "limit": 1,
        "addressdetails": 1,
    }
    headers = {
        "User-Agent": "DjangoFuelRouteOptimizer/1.0 (assessment_app; contact: backend_eng@example.com)"
    }

    try:
        api_calls_made += 1
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            raise ValidationError(
                f"Location '{query}' could not be found within the USA. "
                "Please verify city name or state code."
            )

        result = data[0]
        lat = float(result["lat"])
        lon = float(result["lon"])
        display_name = result.get("display_name", query)

        if not is_within_usa(lat, lon):
            raise ValidationError(f"Location '{query}' resolved outside the USA ({lat}, {lon}).")

        # Cache result
        _GEOCODE_CACHE[norm_query] = (lat, lon, display_name)
        return lat, lon, display_name, api_calls_made

    except requests.RequestException as e:
        logger.error(f"Geocoding error for '{query}': {e}")
        raise ValidationError(
            f"Failed to geocode '{query}' via external service. Error: {str(e)}"
        )
