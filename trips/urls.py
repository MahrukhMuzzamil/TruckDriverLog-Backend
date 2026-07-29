from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("trips", views.TripViewSet, basename="trip")

urlpatterns = [
    path("", include(router.urls)),
    path("geocode/suggest/", views.geocode_suggest, name="geocode-suggest"),
    path("health/", views.health, name="health"),
]
