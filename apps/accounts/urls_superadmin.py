from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_superadmin import (
    OrganizationSuperadminViewSet, UserSuperadminViewSet,
    SecurityStatsView, SystemHealthView,
    SuperadminReviewViewSet, DemoRequestViewSet,
    SystemSettingsView, SMTPSettingsView,
    SecurityPolicyView, TerminateAllSessionsView,
    SuperadminAssessmentsViewSet,
)

router = DefaultRouter()
router.register(r"organizations", OrganizationSuperadminViewSet, basename="superadmin-organizations")
router.register(r"users", UserSuperadminViewSet, basename="superadmin-users")
router.register(r"reviews", SuperadminReviewViewSet, basename="superadmin-reviews")
router.register(r"demo-requests", DemoRequestViewSet, basename="superadmin-demo-requests")
router.register(r"assessments", SuperadminAssessmentsViewSet, basename="superadmin-assessments")

urlpatterns = [
    path("", include(router.urls)),
    # Security
    path("security/stats/", SecurityStatsView.as_view(), name="security-stats"),
    path("security/policy/", SecurityPolicyView.as_view(), name="security-policy"),
    path("security/terminate-sessions/", TerminateAllSessionsView.as_view(), name="terminate-sessions"),
    # System
    path("system/health/", SystemHealthView.as_view(), name="system-health"),
    path("system/settings/", SystemSettingsView.as_view(), name="system-settings"),
    path("system/smtp/", SMTPSettingsView.as_view(), name="smtp-settings"),
    path("system/smtp/test/", SMTPSettingsView.as_view(), name="smtp-test"),
]
