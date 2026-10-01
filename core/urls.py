from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
    # Root alias directly to route endpoint for ease of use
    path("", include("routing.urls")),
]
