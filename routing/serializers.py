from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        help_text="Starting location in the USA (e.g. 'New York, NY', 'Austin, TX', or '40.7128,-74.0060')",
    )
    finish = serializers.CharField(
        required=True,
        help_text="Finish location in the USA (e.g. 'Los Angeles, CA', 'Seattle, WA', or '34.0522,-118.2437')",
    )
    vehicle_type = serializers.ChoiceField(
        choices=["truck", "car", "suv", "bike", "custom"],
        default="truck",
        required=False,
        help_text="Vehicle profile: 'truck' (500mi, 10mpg), 'car' (420mi, 30mpg), 'suv' (440mi, 20mpg), 'bike' (200mi, 45mpg), or 'custom'",
    )
    optimization_strategy = serializers.ChoiceField(
        choices=["lowest_cost", "minimum_stops", "balanced", "conservative"],
        default="lowest_cost",
        required=False,
        help_text="Optimization strategy: 'lowest_cost' (max fuel savings), 'minimum_stops' (fewer stops), 'balanced' (time vs money), 'conservative' (safety reserve)",
    )
    initial_fuel_percent = serializers.FloatField(
        default=100.0,
        min_value=10.0,
        max_value=100.0,
        required=False,
        help_text="Percentage of full tank at departure (default: 100%). E.g., 50% for half-tank start",
    )
    reserve_fuel_percent = serializers.FloatField(
        default=8.0,
        min_value=5.0,
        max_value=25.0,
        required=False,
        help_text="Emergency reserve fuel buffer percentage (default: 8%)",
    )
    max_detour_miles = serializers.FloatField(
        default=5.0,
        min_value=0.5,
        max_value=20.0,
        required=False,
        help_text="Maximum allowable driving detour from highway corridor in miles (default: 5.0)",
    )
    include_detour_cost = serializers.BooleanField(
        default=True,
        required=False,
        help_text="Whether to factor in round-trip detour fuel burn cost when comparing fuel station prices",
    )
    preferred_brands = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of preferred truck stop brands (e.g. ['Love\\'s', 'Pilot', 'Flying J', 'Sheetz', 'TA'])",
    )
    fleet_discount_cents = serializers.FloatField(
        default=0.0,
        min_value=0.0,
        max_value=1.0,
        required=False,
        help_text="Fleet discount in dollars per gallon for preferred brands (e.g. 0.10 for 10 cents off)",
    )
    fuel_grade = serializers.ChoiceField(
        choices=["diesel", "regular", "premium"],
        default="diesel",
        required=False,
        help_text="Fuel grade/price adjustment: 'diesel' (1.0x), 'regular' (0.92x), 'premium' (1.08x)",
    )
    compare_strategies = serializers.BooleanField(
        default=False,
        required=False,
        help_text="If true, returns a side-by-side comparison matrix of all 4 optimization strategies",
    )
    export_format = serializers.ChoiceField(
        choices=["json", "gpx"],
        default="json",
        required=False,
        help_text="Response format: 'json' (default) or 'gpx' (downloadable GPX 1.1 XML route)",
    )
    max_range_miles = serializers.FloatField(
        required=False,
        min_value=10.0,
        help_text="Optional custom maximum driving range in miles on a full tank",
    )
    fuel_efficiency_mpg = serializers.FloatField(
        required=False,
        min_value=1.0,
        help_text="Optional custom fuel efficiency in miles per gallon",
    )
    tank_capacity_gallons = serializers.FloatField(
        required=False,
        min_value=0.5,
        help_text="Optional custom fuel tank capacity in gallons",
    )

    def validate(self, data):
        start = data.get("start", "").strip()
        finish = data.get("finish", "").strip()

        if not start:
            raise serializers.ValidationError({"start": "Start location cannot be empty."})
        if not finish:
            raise serializers.ValidationError({"finish": "Finish location cannot be empty."})
        if start.lower() == finish.lower():
            raise serializers.ValidationError("Start and finish locations must be different.")

        data["start"] = start
        data["finish"] = finish
        return data


class CoordinatesSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class FuelStopSerializer(serializers.Serializer):
    stop_number = serializers.IntegerField()
    station_id = serializers.IntegerField()
    truckstop_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    retail_price_per_gallon = serializers.FloatField()
    effective_price_per_gallon = serializers.FloatField(required=False)
    mile_marker = serializers.FloatField()
    distance_from_previous_stop_miles = serializers.FloatField()
    detour_miles = serializers.FloatField(required=False)
    arrival_fuel_percent = serializers.FloatField(required=False)
    gallons_refueled = serializers.FloatField()
    cost_at_stop = serializers.FloatField()
    estimated_arrival_hours = serializers.FloatField(required=False)
    estimated_refuel_duration_minutes = serializers.IntegerField(required=False)
    hos_rest_break_recommended = serializers.BooleanField(required=False)
    hos_reason = serializers.CharField(required=False)
    coordinates = CoordinatesSerializer()
    final_leg = serializers.DictField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)


class RouteResponseSerializer(serializers.Serializer):
    status = serializers.CharField(default="success")
    start_location = serializers.CharField()
    finish_location = serializers.CharField()
    strategy = serializers.CharField()
    vehicle = serializers.DictField()
    initial_fuel_state = serializers.DictField(required=False)
    parameters = serializers.DictField(required=False)
    environmental_impact = serializers.DictField(required=False)
    trip_duration = serializers.DictField(required=False)
    total_distance_miles = serializers.FloatField()
    total_duration_hours = serializers.FloatField()
    duration_formatted = serializers.CharField()
    fuel_efficiency_mpg = serializers.FloatField()
    vehicle_max_range_miles = serializers.FloatField()
    tank_capacity_gallons = serializers.FloatField()
    total_gallons_consumed = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()
    fuel_stops_count = serializers.IntegerField()
    fuel_stops = FuelStopSerializer(many=True)
    strategy_comparison = serializers.ListField(required=False)
    route_geometry = serializers.DictField()
    external_api_calls = serializers.IntegerField()
    execution_time_ms = serializers.FloatField()
    note = serializers.CharField(required=False)
