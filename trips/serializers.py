from rest_framework import serializers

from .models import Trip


class TripCreateSerializer(serializers.Serializer):
    """Validates the four trip-planning inputs."""

    current_location = serializers.CharField(max_length=255)
    pickup_location = serializers.CharField(max_length=255)
    dropoff_location = serializers.CharField(max_length=255)
    current_cycle_used = serializers.FloatField(min_value=0, max_value=70)

    def validate(self, attrs):
        for field in ("current_location", "pickup_location", "dropoff_location"):
            attrs[field] = attrs[field].strip()
            if not attrs[field]:
                raise serializers.ValidationError({field: "This field may not be blank."})
        return attrs


class TripSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = [
            "id",
            "current_location",
            "pickup_location",
            "dropoff_location",
            "current_cycle_used",
            "status",
            "error",
            "result",
            "created_at",
        ]
        read_only_fields = fields


class TripListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for history listings (no heavy result JSON)."""

    summary = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            "id",
            "current_location",
            "pickup_location",
            "dropoff_location",
            "current_cycle_used",
            "status",
            "summary",
            "created_at",
        ]

    def get_summary(self, obj):
        if obj.result:
            return obj.result.get("summary")
        return None
