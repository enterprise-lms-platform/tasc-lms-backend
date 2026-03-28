from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_superadmin import OrganizationSuperadminViewSet, UserSuperadminViewSet, SecurityStatsView, SystemHealthView

router = DefaultRouter()
router.register(r"organizations", OrganizationSuperadminViewSet, basename="superadmin-organizations")
router.register(r"users", UserSuperadminViewSet, basename="superadmin-users")

urlpatterns = [
    path("", include(router.urls)),
    path("security/stats/", SecurityStatsView.as_view(), name="security-stats"),
    path("system/health/", SystemHealthView.as_view(), name="system-health"),
]
