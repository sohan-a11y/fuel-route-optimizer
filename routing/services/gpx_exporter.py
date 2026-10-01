import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Dict, Any


def generate_gpx_route(optimization_result: Dict[str, Any], start_label: str = "Origin", finish_label: str = "Destination") -> str:
    """
    Generates a compliant GPX 1.1 XML string for the optimized route and fuel stops.
    Compatible with Garmin GPS, TomTom, OsmAnd, Google Earth, and GPX navigation apps.
    """
    gpx = ET.Element(
        "gpx",
        version="1.1",
        creator="FuelRouteOptimizer-Django",
        xmlns="http://www.topografix.com/GPX/1/1",
        attrib={"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"}
    )

    metadata = ET.SubElement(gpx, "metadata")
    name_el = ET.SubElement(metadata, "name")
    name_el.text = f"Route from {start_label} to {finish_label}"
    desc_el = ET.SubElement(metadata, "desc")
    desc_el.text = (
        f"Optimized Fuel Route: {optimization_result.get('total_distance_miles', 0):.1f} miles, "
        f"{optimization_result.get('fuel_stops_count', 0)} fuel stops, "
        f"Estimated Total Fuel Cost: ${optimization_result.get('total_fuel_cost', 0):.2f}"
    )

    # 1. Waypoints for Start and Destination
    route_geom = optimization_result.get("route_geometry", {})
    coords = route_geom.get("coordinates", [])

    if coords:
        # Start Waypoint
        start_wpt = ET.SubElement(gpx, "wpt", lat=str(coords[0][1]), lon=str(coords[0][0]))
        ET.SubElement(start_wpt, "name").text = f"Origin: {start_label}"
        ET.SubElement(start_wpt, "sym").text = "Flag, Green"

        # End Waypoint
        end_wpt = ET.SubElement(gpx, "wpt", lat=str(coords[-1][1]), lon=str(coords[-1][0]))
        ET.SubElement(end_wpt, "name").text = f"Destination: {finish_label}"
        ET.SubElement(end_wpt, "sym").text = "Flag, Red"

    # 2. Waypoints for each Fuel Stop
    for stop in optimization_result.get("fuel_stops", []):
        stop_coords = stop.get("coordinates", {})
        wpt = ET.SubElement(
            gpx,
            "wpt",
            lat=str(stop_coords.get("latitude")),
            lon=str(stop_coords.get("longitude")),
        )
        ET.SubElement(wpt, "name").text = f"Stop #{stop.get('stop_number')}: {stop.get('truckstop_name')}"
        ET.SubElement(wpt, "desc").text = (
            f"Address: {stop.get('address', '')}, {stop.get('city')}, {stop.get('state')} | "
            f"Price: ${stop.get('retail_price_per_gallon', 0):.3f}/gal | "
            f"Refuel: {stop.get('gallons_refueled', 0)} gal | "
            f"Cost: ${stop.get('cost_at_stop', 0):.2f} | "
            f"Mile: {stop.get('mile_marker', 0):.1f}"
        )
        ET.SubElement(wpt, "sym").text = "Gas Station"

    # 3. Track with Track Segments and Track Points
    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = f"Optimized Path ({start_label} -> {finish_label})"
    trkseg = ET.SubElement(trk, "trkseg")

    for pt in coords:
        ET.SubElement(trkseg, "trkpt", lat=str(pt[1]), lon=str(pt[0]))

    rough_string = ET.tostring(gpx, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")
