import time
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from routing.serializers import RouteRequestSerializer, RouteResponseSerializer
from routing.services.geocoding_service import geocode_location
from routing.services.osrm_service import get_osrm_route
from routing.services.fuel_optimizer import optimize_fuel_stops
from routing.models import FuelStation
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


class MapView(TemplateView):
    """Interactive visual map UI for exploring optimized routes."""
    template_name = "map.html"


class RouteFuelOptimizationView(APIView):
    """
    API endpoint that accepts a start location and finish location in the USA,
    retrieves the route from OSRM, calculates the optimal fuel stops based on fuel prices,
    and returns the route map representation along with the total fuel cost.

    Supports both POST (JSON body) and GET (query params) for easy Postman / browser testing.
    """

    def get(self, request):
        serializer = RouteRequestSerializer(data=request.query_params)
        return self._process_request(serializer)

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        return self._process_request(serializer)

    def _process_request(self, serializer: RouteRequestSerializer) -> Response:
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_input = serializer.validated_data["start"]
        finish_input = serializer.validated_data["finish"]

        start_time = time.perf_counter()
        total_external_calls = 0

        try:
            # 1. Geocode Start Location (0 or 1 external call)
            start_lat, start_lon, start_label, calls1 = geocode_location(start_input)
            total_external_calls += calls1

            # 2. Geocode Finish Location (0 or 1 external call)
            finish_lat, finish_lon, finish_label, calls2 = geocode_location(finish_input)
            total_external_calls += calls2

            # 3. Retrieve Route & Geometry from OSRM (exactly 1 external call)
            route_data, calls3 = get_osrm_route(
                start_lat=start_lat,
                start_lon=start_lon,
                finish_lat=finish_lat,
                finish_lon=finish_lon,
            )
            total_external_calls += calls3

            # 4. Fuel Stop Optimization along route (0 external calls - purely local DB + spatial)
            optimization_result = optimize_fuel_stops(route_data)

            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response_data = {
                "status": "success",
                "start_location": start_label,
                "finish_location": finish_label,
                "total_distance_miles": optimization_result["total_distance_miles"],
                "total_duration_hours": optimization_result["total_duration_hours"],
                "duration_formatted": optimization_result["duration_formatted"],
                "fuel_efficiency_mpg": optimization_result["fuel_efficiency_mpg"],
                "vehicle_max_range_miles": optimization_result["vehicle_max_range_miles"],
                "total_gallons_consumed": optimization_result["total_gallons_consumed"],
                "total_fuel_cost": optimization_result["total_fuel_cost"],
                "fuel_stops_count": optimization_result["fuel_stops_count"],
                "fuel_stops": optimization_result["fuel_stops"],
                "route_geometry": optimization_result["route_geometry"],
                "external_api_calls": total_external_calls,
                "execution_time_ms": execution_time_ms,
            }

            if "note" in optimization_result:
                response_data["note"] = optimization_result["note"]

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error processing fuel optimization route request")
            return Response(
                {
                    "status": "error",
                    "message": str(e),
                    "external_api_calls": total_external_calls,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class HealthCheckView(APIView):
    """System health check endpoint verifying database status and station count."""

    def get(self, request):
        station_count = FuelStation.objects.count()
        return Response(
            {
                "status": "healthy",
                "database_connected": True,
                "fuel_stations_loaded": station_count,
            },
            status=status.HTTP_200_OK,
        )
