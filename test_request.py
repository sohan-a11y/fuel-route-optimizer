import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from rest_framework.test import APIClient

client = APIClient()
res = client.post("/api/route/", {"start": "New York, NY", "finish": "Los Angeles, CA"}, format="json")
print("HTTP Status Code:", res.status_code)
data = res.json()
print("Start Location:", data.get("start_location"))
print("Finish Location:", data.get("finish_location"))
print("Total Distance (miles):", data.get("total_distance_miles"))
print("Total Duration:", data.get("duration_formatted"))
print("Total Gallons Consumed:", data.get("total_gallons_consumed"))
print("Total Money Spent on Fuel: $", data.get("total_fuel_cost"))
print("Fuel Stops Count:", data.get("fuel_stops_count"))
print("External API Calls Made:", data.get("external_api_calls"))
print("Execution Time:", data.get("execution_time_ms"), "ms")
print("\nOptimal Fuel Stops Along Route:")
for s in data.get("fuel_stops", []):
    num = s["stop_number"]
    name = s["truckstop_name"]
    city = s["city"]
    state = s["state"]
    mile = s["mile_marker"]
    dist = s["distance_from_previous_stop_miles"]
    gal = s["gallons_refueled"]
    price = s["retail_price_per_gallon"]
    cost = s["cost_at_stop"]
    print(f"  [{num}] Mile {mile:.1f} (+{dist:.1f} mi) -> {name} ({city}, {state}): {gal} gal @ ${price:.3f}/gal = ${cost:.2f}")
