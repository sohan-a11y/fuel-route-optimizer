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
    mile_marker = serializers.FloatField()
    distance_from_previous_stop_miles = serializers.FloatField()
    gallons_refueled = serializers.FloatField()
    cost_at_stop = serializers.FloatField()
    coordinates = CoordinatesSerializer()
    final_leg = serializers.DictField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)


class RouteResponseSerializer(serializers.Serializer):
    status = serializers.CharField(default="success")
    start_location = serializers.CharField()
    finish_location = serializers.CharField()
    vehicle = serializers.DictField(required=False)
    total_distance_miles = serializers.FloatField()
    total_duration_hours = serializers.FloatField()
    duration_formatted = serializers.CharField()
    fuel_efficiency_mpg = serializers.FloatField()
    vehicle_max_range_miles = serializers.FloatField()
    tank_capacity_gallons = serializers.FloatField(required=False)
    total_gallons_consumed = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()
    fuel_stops_count = serializers.IntegerField()
    fuel_stops = FuelStopSerializer(many=True)
    route_geometry = serializers.DictField()
    external_api_calls = serializers.IntegerField()
    execution_time_ms = serializers.FloatField()
    note = serializers.CharField(required=False)
