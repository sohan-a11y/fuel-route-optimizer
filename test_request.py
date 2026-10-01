import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from rest_framework.test import APIClient

client = APIClient()

# Test 1: Full Strategy Comparison Matrix
print("=================== 1. FULL STRATEGY COMPARISON MATRIX ===================")
res = client.post(
    "/api/route/",
    {
        "start": "New York, NY",
        "finish": "Los Angeles, CA",
        "vehicle_type": "truck",
        "compare_strategies": True
    },
    format="json"
)
d = res.json()
print("Strategy comparison matrix:")
for strat in d.get("strategy_comparison", []):
    print(f"  [{strat['display_name']}]: Stops: {strat['fuel_stops_count']}, Cost: ${strat['total_fuel_cost']:.2f}, Trip: {strat['total_trip_hours']}h (+${strat.get('difference_vs_lowest_cost', 0):.2f})")

# Test 2: Environmental Impact & ESG Carbon Metrics
print("\n=================== 2. ENVIRONMENTAL IMPACT (ESG) ===================")
env = d.get("environmental_impact", {})
print(f"Carbon Footprint: {env.get('carbon_emissions_kg')} kg CO2 ({env.get('carbon_emissions_lbs')} lbs CO2)")
print(f"Trees needed to offset 1 year: {env.get('trees_offset_per_year')} trees")

# Test 3: DOT Hours of Service (HOS) Rest Break Flags
print("\n=================== 3. DOT HOURS OF SERVICE (HOS) REST BREAK FLAGS ===================")
for s in d.get("fuel_stops", []):
    hos_flag = "[MANDATORY 30-MIN REST BREAK]" if s.get("hos_rest_break_recommended") else "Refuel only"
    print(f"  Stop #{s['stop_number']} @ Mile {s['mile_marker']} (~{s.get('estimated_arrival_hours')}h driving): {s['truckstop_name']} -> {hos_flag}")

# Test 4: Passenger Car with Regular Gasoline & 14-Gal Tank
print("\n=================== 4. PASSENGER CAR PROFILE (REGULAR 87 GAS, 14 GAL TANK) ===================")
res = client.post(
    "/api/route/",
    {
        "start": "Chicago, IL",
        "finish": "Miami, FL",
        "vehicle_type": "car",
        "fuel_grade": "regular"
    },
    format="json"
)
cd = res.json()
print(f"Car Trip (Chicago -> Miami, {cd['total_distance_miles']:.1f} mi): {cd['fuel_stops_count']} stops, Total Cost: ${cd['total_fuel_cost']:.2f}")
for s in cd.get("fuel_stops", []):
    print(f"  Stop #{s['stop_number']} @ Mile {s['mile_marker']}: {s['truckstop_name']} | Refuel: {s['gallons_refueled']} gal (Max tank: 14 gal) | Cost: ${s['cost_at_stop']:.2f}")

# Test 5: GPX Export Format
print("\n=================== 5. GPX 1.1 ROUTE & WAYPOINTS EXPORT ===================")
res_gpx = client.get(
    "/api/route/?start=Austin,+TX&finish=Dallas,+TX&export_format=gpx"
)
print("GPX Response Status:", res_gpx.status_code)
print("GPX Content-Type:", res_gpx.headers.get("Content-Type"))
print("GPX Content Snippet:\n", res_gpx.content.decode("utf-8")[:400])
