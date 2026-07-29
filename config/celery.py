import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("truckdriverlog")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Periodic maintenance: prune stale anonymous trips nightly so the demo
# database never grows unbounded.
app.conf.beat_schedule = {
    "cleanup-old-trips": {
        "task": "trips.tasks.cleanup_old_trips",
        "schedule": crontab(hour=3, minute=0),
        "args": (30,),  # delete trips older than 30 days
    },
}
