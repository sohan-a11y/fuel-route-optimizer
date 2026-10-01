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
