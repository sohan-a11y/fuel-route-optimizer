# Fuel Route Optimizer & Cost Optimization API

A production-grade Django REST API that determines the most cost-effective fueling strategy for road trips within the continental USA. Given an origin and destination, the service integrates with the Open Source Routing Machine (OSRM) to extract route geometry, projects US truck stops from OPIS fuel price data, and computes the mathematically optimal refuel stops to minimize total trip expense while adhering to vehicle range limits.

---

## Key Assessment Requirements & Implementation

| Requirement | Implementation Detail |
|---|---|
| **Framework** | Django 6.1+ & Django REST Framework 3.18+ |
| **Input** | Start and Finish locations in the USA (supports City/State names like `"Austin, TX"` or coordinate pairs `"30.2672, -97.7431"`) |
| **Routing & Mapping** | OSRM Driving API (`overview=full&geometries=geojson`) returning complete line geometry and distances |
| **External API Optimization** | **Strictly 1 to 3 calls total** (1 for OSRM, 0-2 for optional city geocoding). Truck stops are 100% geocoded and indexed locally. |
| **Vehicle Constraints** | Max range: **500 miles** on a full tank (50 gallons). Fuel efficiency: **10 miles per gallon (mpg)**. |
| **Fuel Stop Optimization** | Spatial projection along highway route polyline + greedy/DP lookahead algorithm selecting minimum retail price per gallon |
| **Output** | Full GeoJSON route geometry, optimal fuel stops list with coordinates, gallons refueled, and total money spent |

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
│   ├── serializers.py              # DRF request & response serializers
│   ├── views.py                    # RouteFuelOptimizationView, HealthCheckView, MapView
│   ├── urls.py                     # /api/route/, /api/health/, /map/
│   ├── tests.py                    # Comprehensive automated test suite
│   ├── templates/
│   │   └── map.html                # Interactive Leaflet web map visualization UI
│   ├── services/
│   │   ├── geocoding_service.py    # US boundary validation & offline city cache
│   │   ├── osrm_service.py         # OSRM public API integration
│   │   ├── fuel_optimizer.py       # Spatial route projection & fuel stop selection
│   │   └── data_loader.py          # CSV parser & bulk database loader
│   └── management/commands/
│       └── load_fuel_stations.py   # python manage.py load_fuel_stations
├── fuel_prices.csv                 # Raw fuel price dataset from OPIS
├── postman_collection.json         # Ready-to-import Postman collection
├── test_request.py                 # Standalone script to verify API response
├── requirements.txt                # Python dependencies
└── manage.py                       # Django CLI runner
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- Windows PowerShell / Command Prompt / Bash

### 2. Activate Virtual Environment & Install Dependencies

If setting up for the first time:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Apply Migrations & Load Fuel Station Data

```powershell
python manage.py migrate
python manage.py load_fuel_stations
```

> **Note**: `load_fuel_stations` maps all US truck stops to precise geographic coordinates using local GeoNames US data and inserts 6,600+ unique US stations into the SQLite database in ~5 seconds.

### 4. Run the Development Server

```powershell
python manage.py runserver
```
The server will start at `http://127.0.0.1:8000/`.

---

## Testing the API

### Option A: Using Postman (Recommended)

1. Open Postman.
2. Click **Import** (top left).
3. Drag & drop or select [`postman_collection.json`](file:///c:/Users/kalya/Downloads/assesssment/postman_collection.json).
4. Run any of the pre-configured requests:
   - **Optimize Route (NY to LA - Cross Country)**: Demonstrates optimal 6-stop fueling across 2,794 miles.
   - **Optimize Route (Austin to Dallas - Under 500 Miles)**: Demonstrates single-tank trip under 500 miles.
   - **Optimize Route (Chicago to Miami - Mid Distance)**: Demonstrates ~1,370 mile Midwest-to-Florida route.
   - **Optimize Route (Coordinates Input)**: Demonstrates direct latitude/longitude inputs.
   - **Health Check**: Checks DB status and station count.

### Option B: Using cURL or PowerShell

#### 1. Long Distance Route (New York to Los Angeles)
```powershell
curl -X POST http://127.0.0.1:8000/api/route/ `
  -H "Content-Type: application/json" `
  -d '{"start": "New York, NY", "finish": "Los Angeles, CA"}'
```

#### 2. Short Distance Route (Austin to Dallas)
```powershell
curl -X POST http://127.0.0.1:8000/api/route/ `
  -H "Content-Type: application/json" `
  -d '{"start": "Austin, TX", "finish": "Dallas, TX"}'
```

#### 3. GET with Query Parameters
```
http://127.0.0.1:8000/api/route/?start=Austin,%20TX&finish=Dallas,%20TX
```

### Option C: Interactive Visual Web Map

Navigate to `http://127.0.0.1:8000/` or `http://127.0.0.1:8000/map/` in any web browser.
- Interactive Leaflet map displaying the complete highway route line.
- Color-coded pins for Origin (Green), Destination (Red), and Optimal Fuel Stops (Amber).
- Real-time trip dashboard with distance, duration, gallons consumed, and total cost.
- Click any stop card to fly directly to that truck stop on the map.

---

## API Documentation

### `POST /api/route/`
**Request Body**:
```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```

**Response (HTTP 200 OK)**:
```json
{
  "status": "success",
  "start_location": "New York, NY, USA",
  "finish_location": "Los Angeles, CA, USA",
  "total_distance_miles": 2794.22,
  "total_duration_hours": 49.8,
  "duration_formatted": "49h 48m",
  "fuel_efficiency_mpg": 10.0,
  "vehicle_max_range_miles": 500.0,
  "total_gallons_consumed": 279.42,
  "total_fuel_cost": 873.36,
  "fuel_stops_count": 6,
  "fuel_stops": [
    {
      "stop_number": 1,
      "station_id": 7170,
      "truckstop_name": "SHEETZ #639",
      "address": "I-80 Exit 223",
      "city": "Youngstown",
      "state": "OH",
      "retail_price_per_gallon": 3.059,
      "mile_marker": 408.9,
      "distance_from_previous_stop_miles": 408.9,
      "gallons_refueled": 40.89,
      "cost_at_stop": 125.08,
      "coordinates": {
        "latitude": 41.0998,
        "longitude": -80.6495
      }
    },
    {
      "stop_number": 2,
      "station_id": 70744,
      "truckstop_name": "CASEYS #3686",
      "address": "I-80 EXIT 81",
      "city": "Utica",
      "state": "IL",
      "retail_price_per_gallon": 2.969,
      "mile_marker": 884.3,
      "distance_from_previous_stop_miles": 475.4,
      "gallons_refueled": 47.54,
      "cost_at_stop": 141.15,
      "coordinates": {
        "latitude": 41.3414,
        "longitude": -89.0118
      }
    },
    {
      "stop_number": 3,
      "station_id": 69840,
      "truckstop_name": "KUM & GO #0370",
      "address": "I-80, EXIT 439 & SR-370",
      "city": "Gretna",
      "state": "NE",
      "retail_price_per_gallon": 2.921,
      "mile_marker": 1311.1,
      "distance_from_previous_stop_miles": 426.9,
      "gallons_refueled": 42.69,
      "cost_at_stop": 124.68,
      "coordinates": {
        "latitude": 41.1408,
        "longitude": -96.2417
      }
    },
    {
      "stop_number": 4,
      "station_id": 69085,
      "truckstop_name": "FATDOGS OGALLALA",
      "address": "US-80, EXIT 126 & US-26/SR-61",
      "city": "Ogallala",
      "state": "NE",
      "retail_price_per_gallon": 3.014,
      "mile_marker": 1630.6,
      "distance_from_previous_stop_miles": 319.5,
      "gallons_refueled": 31.95,
      "cost_at_stop": 96.3,
      "coordinates": {
        "latitude": 41.128,
        "longitude": -101.7196
      }
    },
    {
      "stop_number": 5,
      "station_id": 6886,
      "truckstop_name": "PWI #535",
      "address": "I-70, EXIT 47",
      "city": "Palisade",
      "state": "CO",
      "retail_price_per_gallon": 3.379,
      "mile_marker": 2063.2,
      "distance_from_previous_stop_miles": 432.6,
      "gallons_refueled": 43.26,
      "cost_at_stop": 146.18,
      "coordinates": {
        "latitude": 39.1103,
        "longitude": -108.3512
      }
    },
    {
      "stop_number": 6,
      "station_id": 72965,
      "truckstop_name": "Maverik #674",
      "address": "I-15, Exit 45",
      "city": "North Las Vegas",
      "state": "NV",
      "retail_price_per_gallon": 3.282,
      "mile_marker": 2547.0,
      "distance_from_previous_stop_miles": 483.8,
      "gallons_refueled": 73.11,
      "cost_at_stop": 239.97,
      "coordinates": {
        "latitude": 36.1989,
        "longitude": -115.1175
      },
      "note": "Includes 24.72 gallons to cover the final 247.2-mile leg to the destination."
    }
  ],
  "route_geometry": {
    "type": "LineString",
    "coordinates": [
      [-74.006, 40.7128],
      "..."
    ]
  },
  "external_api_calls": 1,
  "execution_time_ms": 10079.64
}
```

---

## Running the Automated Test Suite

Run the full Django test suite with:

```powershell
python manage.py test routing
```

Test coverage includes:
- Health check endpoint verification
- Short distance trip ($< 500$ miles) logic
- Cross-country trip ($> 2500$ miles) multi-stop optimization
- Max range enforcement ($\le 500$ miles per leg)
- Latitude & Longitude coordinate inputs
- GET query parameter handling
- Missing parameter and invalid location handling
