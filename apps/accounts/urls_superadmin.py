from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_superadmin import OrganizationSuperadminViewSet, UserSuperadminViewSet

router = DefaultRouter()
router.register(r"organizations", OrganizationSuperadminViewSet, basename="superadmin-organizations")
router.register(r"users", UserSuperadminViewSet, basename="superadmin-users")

urlpatterns = [
    path("", include(router.urls)),
]
