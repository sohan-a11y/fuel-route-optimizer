# Fuel Route Optimizer & Cost Optimization API

A production-grade Django REST API that determines the most cost-effective fueling strategy for road trips within the continental USA. Given an origin and destination, the service integrates with the Open Source Routing Machine (OSRM) to extract route geometry, projects US truck stops from OPIS fuel price data, and computes the mathematically optimal refuel stops to minimize total trip expense while adhering to vehicle range limits and physical tank capacity constraints.

---

## Key Assessment Requirements & Comprehensive Capabilities

| Feature / Requirement | Implementation Detail |
|---|---|
| **Framework** | Django 6.1+ & Django REST Framework 3.18+ |
| **Input** | Start and Finish locations in the USA (City/State names like `"Austin, TX"` or coordinate pairs `"30.2672, -97.7431"`) |
| **Routing & Mapping** | OSRM Driving API (`overview=full&geometries=geojson`) returning complete polyline geometry, driving duration, and distances |
| **External API Optimization** | **Strictly 1 to 3 calls total** (1 for OSRM, 0-2 for optional city geocoding). Truck stops are 100% geocoded and indexed locally. |
| **Assessment Default (Truck)** | Max range: **500 miles** on a full tank (50 gallons). Fuel efficiency: **10 miles per gallon (mpg)**. |
| **Multi-Vehicle Profiles** | Supports **Truck**, **Passenger Car** (14 gal tank, 30 mpg), **SUV** (22 gal tank, 20 mpg), **Motorcycle / Bike** (4.5 gal tank, 45 mpg), and **Custom** specs. |
| **Physical Tank Limit** | **Strictly enforced**: Refuel amount at any single stop **never exceeds the vehicle's physical tank capacity**. |
| **4 Optimization Strategies** | `lowest_cost` (max savings), `minimum_stops` (fewer stops), `balanced` (time vs money), and `conservative` (safety reserve buffer). |
| **Strategy Trade-Off Matrix** | Parameter `compare_strategies=true` returns side-by-side comparison across all 4 strategies with dollar and time savings. |
| **ESG Environmental Metrics** | EPA-compliant carbon emissions reporting (`carbon_emissions_kg`, `carbon_emissions_lbs`) and annual mature tree offset estimation. |
| **DOT Hours of Service (HOS)** | Flags refueling stops where cumulative driving exceeds ~8 hours to fulfill mandatory FMCSA/DOT 30-minute commercial rest breaks. |
| **Fuel Grades & Pricing** | Supports `diesel` (1.00x), `regular` 87 unleaded (0.92x), and `premium` 93 (1.08x). |
| **Detour Penalties & Fleet Loyalty** | Models round-trip detour fuel burn cost and applies fleet card loyalty discounts (e.g. $0.15/gal off Love's or Pilot). |
| **GPX 1.1 Route Export** | Parameter `export_format=gpx` generates a fully compliant GPX 1.1 XML track and waypoints for GPS / Garmin / Google Earth devices. |
| **Interactive Map & Live Demo** | Interactive Leaflet UI with live route drawing, stop markers, fuel gauges, and strategy comparisons. |

---

### Supported Vehicle Profiles

| Profile (`vehicle_type`) | Full Tank Range | Efficiency | Tank Capacity | Default Fuel | Single Refuel Cap |
|---|---|---|---|---|---|
| **`truck`** *(Assessment Default)* | 500 miles | 10.0 MPG | 50.0 gallons | Diesel | Max 50.0 gal |
| **`car`** | 420 miles | 30.0 MPG | 14.0 gallons | Regular 87 | Max 14.0 gal |
| **`suv`** | 440 miles | 20.0 MPG | 22.0 gallons | Regular 87 | Max 22.0 gal |
| **`bike`** | 200 miles | 45.0 MPG | 4.5 gallons | Regular 87 | Max 4.5 gal |
| **`custom`** | User specified | User specified | User specified | Configurable | Capped at custom capacity |

---

## Live Links & Repository

- **GitHub Repository**: [https://github.com/sohan-a11y/fuel-route-optimizer](https://github.com/sohan-a11y/fuel-route-optimizer)
- **Live Hosted Web Map**: [https://sohan-a11y.github.io/fuel-route-optimizer/](https://sohan-a11y.github.io/fuel-route-optimizer/)

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
│   ├── tests.py                    # Automated test suite (12 tests passing)
│   ├── templates/
│   │   └── map.html                # Interactive Leaflet web map visualization UI
│   ├── services/
│   │   ├── geocoding_service.py    # US boundary validation & offline city cache
│   │   ├── osrm_service.py         # OSRM public API integration
│   │   ├── fuel_optimizer.py       # Multi-vehicle & multi-strategy optimization engine
│   │   ├── gpx_exporter.py         # GPX 1.1 XML generation service
│   │   └── data_loader.py          # CSV parser & bulk database loader
│   └── management/commands/
│       └── load_fuel_stations.py   # python manage.py load_fuel_stations
├── docs/                           # Hosted Live GitHub Pages Site
│   ├── index.html                  # Standalone client application with full optimization engine
│   └── stations.json               # Seeded 6,626 US fuel stations dataset
├── fuel_prices.csv                 # Raw fuel price dataset from OPIS
├── postman_collection.json         # Ready-to-import Postman collection (10 requests)
├── test_request.py                 # Standalone script verifying all advanced features
├── requirements.txt                # Python dependencies
└── manage.py                       # Django CLI runner
```

---

## Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- Windows PowerShell / Command Prompt / Terminal

### 2. Activate Virtual Environment & Install Dependencies

```powershell
cd c:\Users\kalya\Downloads\assesssment
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Apply Migrations & Ingest Fuel Station Data

```powershell
python manage.py migrate
python manage.py load_fuel_stations
```

> **Note**: `load_fuel_stations` maps all US truck stops to precise geographic coordinates and inserts 6,626 unique US stations into the SQLite database in ~5 seconds.

### 4. Run the Development Server

```powershell
python manage.py runserver
```

- **Interactive Map UI**: [http://127.0.0.1:8000/map/](http://127.0.0.1:8000/map/)
- **API Route Endpoint**: [http://127.0.0.1:8000/api/route/](http://127.0.0.1:8000/api/route/)
- **Health Check Endpoint**: [http://127.0.0.1:8000/api/health/](http://127.0.0.1:8000/api/health/)

---

## Running the Automated Test Suite

Run the Django test suite covering short trips, cross-country trips, car 14-gal tank caps, bike 4.5-gal tank caps, strategy comparison, ESG metrics, GPX export, and error handling:

```powershell
python manage.py test routing
```

Result:
```
Ran 12 tests in 36.777s

OK
```

---

## API Documentation

### `POST /api/route/` or `GET /api/route/`

#### Request Body Parameters

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA",
  "vehicle_type": "truck",
  "optimization_strategy": "lowest_cost",
  "initial_fuel_percent": 100.0,
  "fuel_grade": "diesel",
  "compare_strategies": true,
  "max_detour_miles": 5.0,
  "include_detour_cost": true,
  "preferred_brands": ["Love's", "Pilot"],
  "fleet_discount_cents": 0.15,
  "export_format": "json"
}
```

#### Parameter Reference

| Field | Type | Default | Description |
|---|---|---|---|
| `start` | `string` | **Required** | US origin city/state (`"New York, NY"`) or coordinates (`"40.7128, -74.0060"`) |
| `finish` | `string` | **Required** | US destination city/state (`"Los Angeles, CA"`) or coordinates (`"34.0522, -118.2437"`) |
| `vehicle_type` | `string` | `"truck"` | `"truck"`, `"car"`, `"suv"`, `"bike"`, or `"custom"` |
| `optimization_strategy` | `string` | `"lowest_cost"` | `"lowest_cost"`, `"minimum_stops"`, `"balanced"`, or `"conservative"` |
| `initial_fuel_percent` | `float` | `100.0` | Departure fuel tank level percentage (e.g. 50% for half-tank start) |
| `fuel_grade` | `string` | `"diesel"` | Fuel pricing adjustment: `"diesel"` (1.0x), `"regular"` (0.92x), `"premium"` (1.08x) |
| `compare_strategies` | `boolean` | `false` | When `true`, returns a comparison matrix evaluating all 4 strategies |
| `max_detour_miles` | `float` | `5.0` | Maximum allowable detour distance from highway route corridor |
| `include_detour_cost` | `boolean` | `true` | Factors in round-trip detour fuel burn expense when selecting stops |
| `preferred_brands` | `list` | `[]` | List of preferred truck stop brands for fleet card discounts |
| `fleet_discount_cents`| `float` | `0.0` | Fleet card discount in dollars per gallon (e.g. `0.15` for 15¢/gal) |
| `export_format` | `string` | `"json"` | `"json"` (default) or `"gpx"` for direct GPS XML download |

---

## 5-Minute Loom Video Recording Guide

When recording your Loom demonstration, follow this 4-step walkthrough:

1. **Introduction & Architecture (1 min)**:
   - Introduce the project: Django REST Framework backend with OSRM routing and OPIS US fuel station spatial indexing.
   - Mention the 1-to-3 external API call limit: Exactly 1 OSRM call is made per route, with 6,626 US fuel stations loaded and spatially indexed locally.
2. **Postman Demonstration (2 mins)**:
   - Import `postman_collection.json`.
   - Run **Request 1 (Multi-Strategy Trade-Off Matrix)**: Show how `compare_strategies=true` evaluates all 4 strategies (Lowest Cost vs Min Stops) and returns dollar savings and trip duration.
   - Run **Request 3 (Passenger Car Profile)**: Show that refuels are capped strictly at 14.0 gallons, showing that car tank constraints are properly enforced.
   - Run **Request 6 (Half-Tank Start)**: Show that starting with 50% fuel schedules the first fuel stop within the first 250 miles.
   - Run **Request 9 (GPX Export)**: Show the downloadable GPX 1.1 XML response for Garmin/GPS units.
3. **Live Web Map Demonstration (1.5 mins)**:
   - Open the live hosted link: `https://sohan-a11y.github.io/fuel-route-optimizer/`.
   - Switch between **Truck** (500 mi) and **Car** (420 mi).
   - Show the interactive **Strategy Trade-Off Matrix** table and click rows to instantly apply different strategies.
   - Point out the **Environmental Impact ESG banner** (CO2 kg & trees needed) and **30-Min DOT Rest Break** alert badges on long trips.
4. **Summary & Wrap-Up (30 sec)**:
   - Highlight the 12 passing automated tests (`python manage.py test routing`).
   - Conclude by pointing to the GitHub repository and live demo.
