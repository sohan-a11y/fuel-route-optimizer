import csv
import logging
from decimal import Decimal
from pathlib import Path
from typing import Dict, Tuple, Optional

import pgeocode
from django.conf import settings
from routing.models import FuelStation

logger = logging.getLogger(__name__)

# Known US city coordinate overrides for specific names in OPIS CSV
OVERRIDE_COORDS: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("de forest", "WI"): (43.2505, -89.3448),
    ("winston salem", "NC"): (36.0999, -80.2442),
    ("saint albans", "VT"): (44.8109, -73.0832),
    ("saint charles", "MO"): (38.7881, -90.4974),
    ("saint clair", "MI"): (42.8242, -82.4938),
    ("saint croix", "IN"): (38.2259, -86.5894),
    ("saint joseph", "MO"): (39.7674, -94.8467),
    ("saint louis", "MO"): (38.6270, -90.1994),
    ("saint marys", "KS"): (39.1947, -96.0694),
    ("saint paul", "NE"): (41.2144, -98.4587),
    ("saint robert", "MO"): (37.8284, -92.1402),
    ("saint thomas", "PA"): (39.9079, -77.8078),
}

CANADIAN_PROVINCES = {
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"
}


def get_us_city_coordinates_lookup() -> Dict[Tuple[str, str], Tuple[float, float]]:
    """
    Builds a high-accuracy in-memory lookup table of (normalized_city, state) -> (lat, lon)
    using GeoNames US dataset bundled via pgeocode, supplemented with city overrides.
    """
    nomi = pgeocode.Nominatim("us")
    df = nomi._data

    lookup: Dict[Tuple[str, str], Tuple[float, float]] = {}
    for _, row in df.iterrows():
        pname = str(row["place_name"]).strip().lower()
        state = str(row["state_code"]).strip().upper()
        if (pname, state) not in lookup:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                lookup[(pname, state)] = (lat, lon)
            except (ValueError, TypeError):
                continue

    # Apply manual overrides for any normalization differences
    for (city, state), coords in OVERRIDE_COORDS.items():
        lookup[(city.lower(), state.upper())] = coords

    return lookup


def load_fuel_stations_from_csv(csv_path: Optional[Path] = None, force_reload: bool = False) -> int:
    """
    Parses the fuel prices CSV, geolocates every truck stop in the USA,
    and bulk loads them into the database.
    """
    if csv_path is None:
        csv_path = getattr(settings, "FUEL_PRICES_CSV_PATH", Path("fuel_prices.csv"))

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Fuel prices CSV not found at: {csv_path}")

    current_count = FuelStation.objects.count()
    if current_count > 0 and not force_reload:
        logger.info(f"Database already populated with {current_count} fuel stations.")
        return current_count

    if force_reload and current_count > 0:
        logger.info(f"Purging {current_count} existing fuel station records for reload...")
        FuelStation.objects.all().delete()

    logger.info("Initializing US city geocoding lookup...")
    city_lookup = get_us_city_coordinates_lookup()

    logger.info(f"Parsing fuel prices CSV from {csv_path}...")
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    # Deduplicate entries by (opis_id, city, state), selecting the lowest price
    best_stations: Dict[Tuple[str, str, str], dict] = {}
    skipped_canadian = 0
    skipped_unmatched = 0

    for row in raw_rows:
        state = row.get("State", "").strip().upper()
        if state in CANADIAN_PROVINCES:
            skipped_canadian += 1
            continue

        opis_id_raw = row.get("OPIS Truckstop ID", "").strip()
        city_raw = row.get("City", "").strip()
        city_norm = city_raw.lower()

        coords = city_lookup.get((city_norm, state))
        if not coords:
            skipped_unmatched += 1
            continue

        try:
            opis_id = int(opis_id_raw)
            price = Decimal(str(row.get("Retail Price", "0")).strip())
            rack_id_raw = row.get("Rack ID", "").strip()
            rack_id = int(rack_id_raw) if rack_id_raw.isdigit() else None
        except (ValueError, TypeError):
            continue

        dedup_key = (opis_id_raw, city_norm, state)
        if dedup_key not in best_stations or price < best_stations[dedup_key]["retail_price"]:
            best_stations[dedup_key] = {
                "opis_id": opis_id,
                "name": row.get("Truckstop Name", "").strip(),
                "address": row.get("Address", "").strip(),
                "city": city_raw,
                "state": state,
                "rack_id": rack_id,
                "retail_price": price,
                "latitude": coords[0],
                "longitude": coords[1],
            }

    station_instances = [FuelStation(**data) for data in best_stations.values()]

    logger.info(f"Bulk inserting {len(station_instances)} unique US fuel stations into database...")
    batch_size = 1000
    FuelStation.objects.bulk_create(station_instances, batch_size=batch_size)

    total_created = FuelStation.objects.count()
    logger.info(
        f"Successfully loaded {total_created} fuel stations "
        f"(skipped {skipped_canadian} Canadian rows, {skipped_unmatched} unmatched)."
    )
    return total_created


def ensure_fuel_stations_loaded():
    """Helper to ensure data exists before queries."""
    if FuelStation.objects.count() == 0:
        logger.info("FuelStation table is empty. Triggering automated initial data ingestion...")
        load_fuel_stations_from_csv()
