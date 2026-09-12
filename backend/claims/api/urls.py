from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClaimViewSet, HealthView, LoginView, LogoutView, MeView

router = DefaultRouter()
router.register("claims", ClaimViewSet, basename="claim")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
