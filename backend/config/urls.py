from django.urls import include, path

urlpatterns = [
    path("api/", include("claims.api.urls")),
]
