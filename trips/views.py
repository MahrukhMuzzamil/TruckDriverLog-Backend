import logging

from django.core.cache import cache
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .exceptions import PlanningError
from .models import Trip
from .serializers import TripCreateSerializer, TripListSerializer, TripSerializer
from .services import geocoding, planner
from .tasks import plan_trip_task

logger = logging.getLogger(__name__)


class TripViewSet(viewsets.ReadOnlyModelViewSet):
    """Create is handled explicitly in `create`; retrieval/list are read-only."""

    queryset = Trip.objects.all()

    def get_serializer_class(self):
        return TripListSerializer if self.action == "list" else TripSerializer

    def get_queryset(self):
        return Trip.objects.all()[:20] if self.action == "list" else Trip.objects.all()

    def create(self, request):
        serializer = TripCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        trip = Trip(
            current_location=data["current_location"],
            pickup_location=data["pickup_location"],
            dropoff_location=data["dropoff_location"],
            current_cycle_used=data["current_cycle_used"],
        )

        # `mode=async` offloads planning to Celery and returns immediately;
        # the default synchronous path is sub-second thanks to Redis-cached
        # geocoding and routing.
        if request.query_params.get("mode") == "async":
            trip.status = Trip.Status.PROCESSING
            trip.save()
            plan_trip_task.delay(str(trip.id))
            return Response(TripSerializer(trip).data, status=status.HTTP_202_ACCEPTED)

        try:
            trip.result = planner.plan_trip(
                data["current_location"],
                data["pickup_location"],
                data["dropoff_location"],
                data["current_cycle_used"],
            )
            trip.status = Trip.Status.COMPLETED
        except PlanningError:
            raise
        except Exception:
            logger.exception("Unexpected planning failure")
            return Response(
                {"detail": "Something went wrong while planning this trip."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        trip.save()
        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def geocode_suggest(request):
    """Debounced autocomplete for the location inputs."""
    query = request.query_params.get("q", "")
    return Response({"results": geocoding.suggest(query)})


@api_view(["GET"])
def health(request):
    """Liveness probe: verifies the cache (Redis) round-trips."""
    cache.set("healthcheck", "ok", 10)
    return Response({"status": "ok", "cache": cache.get("healthcheck") == "ok"})
