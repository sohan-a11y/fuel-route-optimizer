from django.urls import path
from routing.views import RouteFuelOptimizationView, HealthCheckView, MapView

urlpatterns = [
    path("", MapView.as_view(), name="map-view"),
    path("map/", MapView.as_view(), name="map-view-alias"),
    path("route/", RouteFuelOptimizationView.as_view(), name="route-optimize"),
    path("health/", HealthCheckView.as_view(), name="health-check"),
]
