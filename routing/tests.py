import xml.etree.ElementTree as ET
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from routing.models import FuelStation
from routing.services.data_loader import ensure_fuel_stations_loaded


class FuelRoutingAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Ensure database is loaded with fuel stations
        ensure_fuel_stations_loaded()

    def setUp(self):
        self.client = APIClient()
        self.route_url = reverse("route-optimize")
        self.health_url = reverse("health-check")

    def test_health_check_endpoint(self):
        """Verifies health check endpoint returns 200 and fuel station counts."""
        response = self.client.get(self.health_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["database_connected"])
        self.assertGreater(data["fuel_stations_loaded"], 6000)

    def test_short_distance_route_within_500_miles(self):
        """
        Trip <= 500 miles (Austin, TX to Dallas, TX is ~195 miles):
        Should reach without mid-route fuel stops, but calculate total fuel cost.
        """
        payload = {"start": "Austin, TX", "finish": "Dallas, TX"}
        response = self.client.post(self.route_url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("Austin", data["start_location"])
        self.assertIn("Dallas", data["finish_location"])
        self.assertLess(data["total_distance_miles"], 500.0)
        self.assertEqual(data["fuel_stops_count"], 0)
        self.assertEqual(len(data["fuel_stops"]), 0)
        self.assertGreater(data["total_fuel_cost"], 0.0)
        self.assertIn("coordinates", data["route_geometry"])
        self.assertLessEqual(data["external_api_calls"], 3)

    def test_long_distance_cross_country_route(self):
        """
        Trip > 500 miles (New York, NY to Los Angeles, CA is ~2790 miles):
        Should determine optimal fuel stops with no consecutive leg exceeding 500 miles.
        """
        payload = {"start": "New York, NY", "finish": "Los Angeles, CA"}
        response = self.client.post(self.route_url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertGreater(data["total_distance_miles"], 2500.0)
        self.assertGreater(data["fuel_stops_count"], 0)
        self.assertGreater(data["total_fuel_cost"], 0.0)

        # Check every leg distance is within 500-mile vehicle range
        stops = data["fuel_stops"]
        for stop in stops:
            self.assertLessEqual(
                stop["distance_from_previous_stop_miles"],
                data["vehicle_max_range_miles"],
                f"Stop {stop['stop_number']} exceeded vehicle range!",
            )
            self.assertGreater(stop["retail_price_per_gallon"], 0.0)
            self.assertGreater(stop["gallons_refueled"], 0.0)
            self.assertGreater(stop["cost_at_stop"], 0.0)

        # Check external API calls minimization (1 to 3 calls)
        self.assertLessEqual(data["external_api_calls"], 3)

    def test_get_request_with_query_params(self):
        """Verifies GET endpoint works seamlessly with query parameters."""
        response = self.client.get(
            self.route_url,
            {"start": "Chicago, IL", "finish": "Atlanta, GA"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("Chicago", data["start_location"])
        self.assertIn("Atlanta", data["finish_location"])
        self.assertGreater(data["total_distance_miles"], 600.0)
        self.assertGreaterEqual(data["fuel_stops_count"], 1)

    def test_coordinate_input_format(self):
        """Verifies coordinates (lat, lon) input is parsed and optimized correctly."""
        payload = {
            "start": "30.2672, -97.7431",  # Austin, TX
            "finish": "32.7767, -96.7970",  # Dallas, TX
        }
        response = self.client.post(self.route_url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertGreater(data["total_distance_miles"], 180.0)

    def test_validation_error_on_empty_input(self):
        """Verifies 400 Bad Request when start or finish is missing."""
        response = self.client.post(self.route_url, data={"start": "Austin, TX"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("finish", response.json()["errors"])

    def test_validation_error_on_identical_locations(self):
        """Verifies 400 Bad Request when start and finish are the same."""
        payload = {"start": "Austin, TX", "finish": "Austin, TX"}
        response = self.client.post(self.route_url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_car_vehicle_profile_and_tank_capacity_cap(self):
        """Verifies passenger car profile respects physical 14-gallon tank capacity."""
        payload = {
            "start": "New York, NY",
            "finish": "Los Angeles, CA",
            "vehicle_type": "car",
        }
        response = self.client.post(self.route_url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["tank_capacity_gallons"], 14.0)
        self.assertEqual(data["fuel_efficiency_mpg"], 30.0)
        self.assertEqual(data["vehicle_max_range_miles"], 420.0)

        for stop in data["fuel_stops"]:
            self.assertLessEqual(
                stop["gallons_refueled"],
                14.0,
                f"Car refuel of {stop['gallons_refueled']} gal exceeded 14.0 gal tank capacity!",
            )

    def test_bike_vehicle_profile_and_tank_capacity_cap(self):
        """Verifies motorcycle profile respects 4.5-gallon tank capacity."""
        payload = {
            "start": "Austin, TX",
            "finish": "Dallas, TX",
            "vehicle_type": "bike",
        }
        response = self.client.post(self.route_url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["tank_capacity_gallons"], 4.5)
        self.assertEqual(data["fuel_efficiency_mpg"], 45.0)
        self.assertEqual(data["vehicle_max_range_miles"], 200.0)

    def test_strategy_comparison_matrix(self):
        """Verifies compare_strategies=True returns evaluation across all 4 strategies."""
        payload = {
            "start": "New York, NY",
            "finish": "Los Angeles, CA",
            "compare_strategies": True,
        }
        response = self.client.post(self.route_url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("strategy_comparison", data)
        self.assertEqual(len(data["strategy_comparison"]), 4)

        strat_names = [s["strategy"] for s in data["strategy_comparison"]]
        self.assertIn("lowest_cost", strat_names)
        self.assertIn("minimum_stops", strat_names)
        self.assertIn("balanced", strat_names)
        self.assertIn("conservative", strat_names)

    def test_environmental_esg_metrics(self):
        """Verifies calculation of carbon footprint and EPA tree offset metrics."""
        payload = {
            "start": "Chicago, IL",
            "finish": "Miami, FL",
            "vehicle_type": "car",
            "fuel_grade": "regular",
        }
        response = self.client.post(self.route_url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("environmental_impact", data)
        env = data["environmental_impact"]
        self.assertGreater(env["carbon_emissions_kg"], 0.0)
        self.assertGreater(env["carbon_emissions_lbs"], 0.0)
        self.assertGreater(env["trees_offset_per_year"], 0.0)

    def test_gpx_export_format(self):
        """Verifies export_format='gpx' returns valid GPX 1.1 XML."""
        response = self.client.get(
            self.route_url,
            {"start": "Austin, TX", "finish": "Dallas, TX", "export_format": "gpx"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("application/gpx+xml", response.headers["Content-Type"])
        root = ET.fromstring(response.content)
        self.assertTrue(root.tag.endswith("gpx"))
