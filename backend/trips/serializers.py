from rest_framework import serializers

from .models import Trip


class TripInputSerializer(serializers.Serializer):
    """Validates the four trip inputs (plus an optional trip start time)."""

    current_location = serializers.CharField(max_length=255)
    pickup_location = serializers.CharField(max_length=255)
    dropoff_location = serializers.CharField(max_length=255)
    current_cycle_used = serializers.FloatField(min_value=0, max_value=70)
    start_time = serializers.DateTimeField(required=False, allow_null=True)

    def validate_current_cycle_used(self, value: float) -> float:
        if value < 0 or value > 70:
            raise serializers.ValidationError(
                "Cycle hours used must be between 0 and 70.")
        return value


LOG_DETAIL_FIELDS = [
    "driver_name", "co_driver_name", "carrier_name", "main_office_address",
    "home_terminal_address", "truck_trailer_numbers", "shipping_document",
    "shipper_commodity",
]


class LogDetailsSerializer(serializers.ModelSerializer):
    """The optional driver/carrier header fields supplied at PDF-download time."""

    class Meta:
        model = Trip
        fields = LOG_DETAIL_FIELDS
        extra_kwargs = {f: {"required": False, "allow_blank": True}
                        for f in LOG_DETAIL_FIELDS}


class TripSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = [
            "id", "current_location", "pickup_location", "dropoff_location",
            "current_cycle_used", "start_time", "result", "created_at",
            *LOG_DETAIL_FIELDS,
        ]
