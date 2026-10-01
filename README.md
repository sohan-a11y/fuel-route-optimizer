# Fuel Route Optimizer & Cost Optimization API

A production-grade Django REST API that determines the most cost-effective fueling strategy for road trips within the continental USA. Given an origin and destination, the service integrates with the Open Source Routing Machine (OSRM) to extract route geometry, projects US truck stops from OPIS fuel price data, and computes the mathematically optimal refuel stops to minimize total trip expense while adhering to vehicle range limits and physical tank capacity constraints.

---

## Key Assessment Requirements & Multi-Vehicle Profiles

| Requirement | Implementation Detail |
|---|---|
| **Framework** | Django 6.1+ & Django REST Framework 3.18+ |
| **Input** | Start and Finish locations in the USA (supports City/State names like `"Austin, TX"` or coordinate pairs `"30.2672, -97.7431"`), plus optional `vehicle_type` |
| **Routing & Mapping** | OSRM Driving API (`overview=full&geometries=geojson`) returning complete line geometry and distances |
| **External API Optimization** | **Strictly 1 to 3 calls total** (1 for OSRM, 0-2 for optional city geocoding). Truck stops are 100% geocoded and indexed locally. |
| **Assessment Default (Truck)** | Max range: **500 miles** on a full tank (50 gallons). Fuel efficiency: **10 miles per gallon (mpg)**. |
| **Multi-Vehicle Profiles** | Supports **Truck**, **Passenger Car** (14 gal tank, 30 mpg), **SUV** (22 gal tank, 20 mpg), and **Motorcycle / Bike** (4.5 gal tank, 45 mpg). |
| **Physical Tank Limit** | **Strictly enforced**: Refuel amount at any single stop **never exceeds the vehicle's physical tank capacity**. |
| **Fuel Stop Optimization** | Spatial projection along highway route polyline + greedy lookahead selecting minimum retail price per gallon |
| **Output** | Full GeoJSON route geometry, optimal fuel stops list with coordinates, gallons refueled, and total money spent |

### Supported Vehicle Profiles

| Profile (`vehicle_type`) | Full Tank Range | Efficiency | Tank Capacity | Typical Single Refuel |
|---|---|---|---|---|
| **`truck`** *(Default)* | 500 miles | 10.0 MPG | 50.0 gallons | 35 – 48 gallons |
| **`car`** | 420 miles | 30.0 MPG | 14.0 gallons | 11 – 13.5 gallons |
| **`suv`** | 440 miles | 20.0 MPG | 22.0 gallons | 16 – 21 gallons |
| **`bike`** | 200 miles | 45.0 MPG | 4.5 gallons | 3.0 – 4.2 gallons |
| **`custom`** | User specified | User specified | User specified | Capped at custom capacity |

---

## Project Structure

```
assesssment/
├── core/                           # Django Project Configuration
│   ├── settings.py                 # Installed apps, REST framework, vehicle constants
│   ├── urls.py                     # Root URL routing (/api/ and /)
│   ├── wsgi.py
│   └── asgi.py
├── routing/                        # Core Application
│   ├── models.py                   # FuelStation model with spatial & price indexes
│   ├── serializers.py              # DRF request & response serializers (with vehicle profiles)
│   ├── views.py                    # RouteFuelOptimizationView, HealthCheckView, MapView
│   ├── urls.py                     # /api/route/, /api/health/, /map/
│   ├── tests.py                    # Automated test suite (9 tests passing)
│   ├── templates/
│   │   └── map.html                # Interactive Leaflet web map visualization UI
│   ├── services/
│   │   ├── geocoding_service.py    # US boundary validation & offline city cache
│   │   ├── osrm_service.py         # OSRM public API integration
│   │   ├── fuel_optimizer.py       # Spatial route projection & tank-constrained refueling
│   │   └── data_loader.py          # CSV parser & bulk database loader
│   └── management/commands/
│       └── load_fuel_stations.py   # python manage.py load_fuel_stations
├── docs/                           # Hosted Live GitHub Pages Site
│   ├── index.html                  # Standalone client application with multi-vehicle selector
│   └── stations.json               # Seeded 6,626 US fuel stations dataset
├── fuel_prices.csv                 # Raw fuel price dataset from OPIS
├── postman_collection.json         # Ready-to-import Postman collection (Truck, Car, Bike, SUV)
├── test_request.py                 # Standalone script verifying all vehicle profiles
├── requirements.txt                # Python dependencies
└── manage.py                       # Django CLI runner
```

---

## Live Demo & Repository

- **GitHub Repository**: [https://github.com/sohan-a11y/fuel-route-optimizer](https://github.com/sohan-a11y/fuel-route-optimizer)
- **Live Hosted Web Map**: [https://sohan-a11y.github.io/fuel-route-optimizer/](https://sohan-a11y.github.io/fuel-route-optimizer/)

---

## Getting Started

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- Windows PowerShell / Command Prompt / Bash

### 2. Activate Virtual Environment & Install Dependencies

```powershell
cd c:\Users\kalya\Downloads\assesssment
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Apply Migrations & Load Fuel Station Data

```powershell
python manage.py migrate
python manage.py load_fuel_stations
```

> **Note**: `load_fuel_stations` maps all US truck stops to precise geographic coordinates and inserts 6,626 unique US stations into the SQLite database in ~5 seconds.

### 4. Run the Development Server

```powershell
python manage.py runserver
```
The server will start at `http://127.0.0.1:8000/`.

---

## Testing with Postman

1. Open Postman.
2. Click **Import** (top left).
3. Select [`postman_collection.json`](file:///c:/Users/kalya/Downloads/assesssment/postman_collection.json).
4. Run any of the pre-configured requests:
   - **1. Commercial Truck**: Default 500-mile range, 10 MPG, 50-gallon tank.
   - **2. Passenger Car**: 420-mile range, 30 MPG, 14-gallon tank (refuels ~12–13 gal per stop).
   - **3. Motorcycle / Bike**: 200-mile range, 45 MPG, 4.5-gallon tank (refuels ~3–4 gal per stop).
   - **4. SUV / Pickup**: 440-mile range, 20 MPG, 22-gallon tank.
   - **5. Short Distance Trip**: Austin to Dallas (< 500 miles on single tank).
   - **6. Direct Coordinates**: Direct latitude/longitude input.

---

## Sample API Requests & Responses

### 1. Passenger Car Profile
**Request**: `POST /api/route/`
```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA",
  "vehicle_type": "car"
}
```

**Response**:
```json
{
  "status": "success",
  "start_location": "New York, NY, USA",
  "finish_location": "Los Angeles, CA, USA",
  "vehicle": {
    "name": "Passenger Car (Sedan)",
    "vehicle_type": "car",
    "max_range_miles": 420.0,
    "fuel_efficiency_mpg": 30.0,
    "tank_capacity_gallons": 14.0
  },
  "total_distance_miles": 2794.22,
  "total_gallons_consumed": 93.14,
  "total_fuel_cost": 295.94,
  "fuel_stops_count": 8,
  "fuel_stops": [
    {
      "stop_number": 1,
      "truckstop_name": "TRUCK WORLD TRUCKSTOP",
      "city": "Hubbard",
      "state": "OH",
      "retail_price_per_gallon": 3.259,
      "mile_marker": 394.9,
      "distance_from_previous_stop_miles": 394.9,
      "gallons_refueled": 13.16,
      "cost_at_stop": 42.89
    },
    {
      "stop_number": 2,
      "truckstop_name": "Gallops",
      "city": "Michigan City",
      "state": "IN",
      "retail_price_per_gallon": 3.399,
      "mile_marker": 759.1,
      "distance_from_previous_stop_miles": 364.2,
      "gallons_refueled": 12.14,
      "cost_at_stop": 41.26
    }
  ]
}
```
*(Notice refuels are ~12–13 gallons, never exceeding the 14-gallon tank capacity!)*

---

## Running the Automated Test Suite

```powershell
python manage.py test routing
```
Output:
```text
Ran 9 tests in 15.265s
OK
```
Tests verify health check, single-tank trips, cross-country truck trips, car tank limits (14 gal), bike tank limits (4.5 gal), coordinates input, and validation errors.
