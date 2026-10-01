import time
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
from django.views.generic import TemplateView

from routing.serializers import RouteRequestSerializer, RouteResponseSerializer
from routing.services.geocoding_service import geocode_location
from routing.services.osrm_service import get_osrm_route
from routing.services.fuel_optimizer import optimize_fuel_stops
from routing.services.gpx_exporter import generate_gpx_route
from routing.models import FuelStation

logger = logging.getLogger(__name__)


class MapView(TemplateView):
    """Interactive visual map UI for exploring optimized routes."""
    template_name = "map.html"


class RouteFuelOptimizationView(APIView):
    """
    API endpoint that accepts a start location and finish location in the USA,
    retrieves the route from OSRM, calculates the optimal fuel stops based on fuel prices,
    and returns the route map representation along with the total fuel cost.

    Supports both POST (JSON body) and GET (query params) for easy Postman / browser testing,
    and export_format='gpx' for downloading GPS navigation files.
    """

    def get(self, request):
        serializer = RouteRequestSerializer(data=request.query_params)
        return self._process_request(serializer)

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        return self._process_request(serializer)

    def _process_request(self, serializer: RouteRequestSerializer):
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_input = serializer.validated_data["start"]
        finish_input = serializer.validated_data["finish"]
        vehicle_type = serializer.validated_data.get("vehicle_type", "truck")
        strategy = serializer.validated_data.get("optimization_strategy", "lowest_cost")
        initial_fuel_pct = serializer.validated_data.get("initial_fuel_percent", 100.0)
        reserve_fuel_pct = serializer.validated_data.get("reserve_fuel_percent", 8.0)
        max_detour = serializer.validated_data.get("max_detour_miles", 5.0)
        include_detour = serializer.validated_data.get("include_detour_cost", True)
        preferred_brands = serializer.validated_data.get("preferred_brands")
        fleet_discount = serializer.validated_data.get("fleet_discount_cents", 0.0)
        fuel_grade = serializer.validated_data.get("fuel_grade", "diesel")
        compare_strategies = serializer.validated_data.get("compare_strategies", False)
        export_format = serializer.validated_data.get("export_format", "json")
        custom_range = serializer.validated_data.get("max_range_miles")
        custom_mpg = serializer.validated_data.get("fuel_efficiency_mpg")
        custom_capacity = serializer.validated_data.get("tank_capacity_gallons")

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

            # 4. Multi-parameter Fuel Stop Optimization
            optimization_result = optimize_fuel_stops(
                route_data=route_data,
                vehicle_type=vehicle_type,
                optimization_strategy=strategy,
                initial_fuel_percent=initial_fuel_pct,
                reserve_fuel_percent=reserve_fuel_pct,
                max_detour_miles=max_detour,
                include_detour_cost=include_detour,
                preferred_brands=preferred_brands,
                fleet_discount_cents=fleet_discount,
                fuel_grade=fuel_grade,
                compare_strategies=compare_strategies,
                custom_range=custom_range,
                custom_mpg=custom_mpg,
                custom_capacity=custom_capacity,
            )

            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

            # 5. Handle GPX Export Format
            if export_format == "gpx":
                gpx_content = generate_gpx_route(
                    optimization_result=optimization_result,
                    start_label=start_label,
                    finish_label=finish_label,
                )
                response = HttpResponse(gpx_content, content_type="application/gpx+xml")
                response["Content-Disposition"] = 'attachment; filename="optimized_fuel_route.gpx"'
                return response

            # 6. JSON Response
            response_data = {
                "status": "success",
                "start_location": start_label,
                "finish_location": finish_label,
                "strategy": optimization_result["strategy"],
                "vehicle": optimization_result["vehicle"],
                "initial_fuel_state": optimization_result["initial_fuel_state"],
                "parameters": optimization_result["parameters"],
                "environmental_impact": optimization_result.get("environmental_impact"),
                "trip_duration": optimization_result.get("trip_duration"),
                "total_distance_miles": optimization_result["total_distance_miles"],
                "total_duration_hours": optimization_result["total_duration_hours"],
                "duration_formatted": optimization_result["duration_formatted"],
                "fuel_efficiency_mpg": optimization_result["fuel_efficiency_mpg"],
                "vehicle_max_range_miles": optimization_result["vehicle_max_range_miles"],
                "tank_capacity_gallons": optimization_result["tank_capacity_gallons"],
                "total_gallons_consumed": optimization_result["total_gallons_consumed"],
                "total_fuel_cost": optimization_result["total_fuel_cost"],
                "fuel_stops_count": optimization_result["fuel_stops_count"],
                "fuel_stops": optimization_result["fuel_stops"],
                "route_geometry": optimization_result["route_geometry"],
                "external_api_calls": total_external_calls,
                "execution_time_ms": execution_time_ms,
            }

            if "strategy_comparison" in optimization_result:
                response_data["strategy_comparison"] = optimization_result["strategy_comparison"]

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
