import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from rest_framework.test import APIClient

client = APIClient()

for v_type in ["truck", "car", "bike"]:
    print(f"\n==================== TESTING VEHICLE: {v_type.upper()} ====================")
    res = client.post(
        "/api/route/",
        {
            "start": "New York, NY",
            "finish": "Los Angeles, CA",
            "vehicle_type": v_type
        },
        format="json"
    )
    data = res.json()
    v = data.get("vehicle", {})
    print(f"Vehicle: {v.get('name')} | Tank: {data.get('tank_capacity_gallons')} gal | MPG: {data.get('fuel_efficiency_mpg')} | Range: {data.get('vehicle_max_range_miles')} mi")
    print(f"Total Distance: {data.get('total_distance_miles')} mi | Fuel Consumed: {data.get('total_gallons_consumed')} gal")
    print(f"Total Fuel Cost: ${data.get('total_fuel_cost'):.2f} | Fuel Stops Count: {data.get('fuel_stops_count')}")
    print("Sample Fuel Stops:")
    for s in data.get("fuel_stops", [])[:3]:
        num = s["stop_number"]
        name = s["truckstop_name"]
        city = s["city"]
        state = s["state"]
        mile = s["mile_marker"]
        gal = s["gallons_refueled"]
        price = s["retail_price_per_gallon"]
        cost = s["cost_at_stop"]
        print(f"  [{num}] Mile {mile:.1f} -> {name} ({city}, {state}): {gal:.1f} gal (<= {data.get('tank_capacity_gallons')} gal max) @ ${price:.3f} = ${cost:.2f}")
    if len(data.get("fuel_stops", [])) > 3:
        last = data["fuel_stops"][-1]
        print(f"  ... [Last Stop #{last['stop_number']}] Mile {last['mile_marker']:.1f} -> {last['truckstop_name']}: {last['gallons_refueled']:.1f} gal @ ${last['retail_price_per_gallon']:.3f} = ${last['cost_at_stop']:.2f}")
