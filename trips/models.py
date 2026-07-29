import uuid

from django.db import models


class Trip(models.Model):
    """A planned trip: raw inputs plus the fully computed plan.

    The computed plan (route, stops, schedule, daily logs) is stored as a
    single JSON document. It is written once at planning time and read as a
    unit, so a denormalized JSONField is both the simplest and the fastest
    representation for this access pattern.
    """

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used = models.FloatField(help_text="Hours already used in the 70hr/8day cycle")

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.COMPLETED
    )
    error = models.TextField(blank=True, default="")
    result = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.current_location} -> {self.pickup_location} -> {self.dropoff_location}"
