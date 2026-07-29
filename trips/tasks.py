import logging
from datetime import timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone

from .exceptions import PlanningError
from .models import Trip

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def plan_trip_task(self, trip_id: str):
    """Plan a trip in the background (used by the `mode=async` API path)."""
    from .services import planner  # local import keeps worker boot fast

    try:
        trip = Trip.objects.get(id=trip_id)
    except Trip.DoesNotExist:
        logger.warning("plan_trip_task: trip %s no longer exists", trip_id)
        return

    try:
        trip.result = planner.plan_trip(
            trip.current_location,
            trip.pickup_location,
            trip.dropoff_location,
            trip.current_cycle_used,
        )
        trip.status = Trip.Status.COMPLETED
        trip.error = ""
    except PlanningError as exc:
        trip.status = Trip.Status.FAILED
        trip.error = exc.message
    except Exception as exc:
        logger.exception("plan_trip_task failed for %s", trip_id)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            trip.status = Trip.Status.FAILED
            trip.error = "Trip planning failed after multiple attempts."
    trip.save()


@shared_task
def cleanup_old_trips(days: int = 30) -> int:
    """Nightly maintenance (Celery beat): prune stale demo trips."""
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Trip.objects.filter(created_at__lt=cutoff).delete()
    logger.info("cleanup_old_trips removed %s trips older than %s days", deleted, days)
    return deleted
