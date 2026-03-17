from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_public import (
    PublicCourseViewSet,
    PublicCategoryViewSet,
    PublicTagViewSet,
    PublicStatsViewSet,
    TrustedClientsViewSet,
)

# Router for public catalogue endpoints
router = DefaultRouter()
router.register(r'courses', PublicCourseViewSet, basename='public-course')
router.register(r'categories', PublicCategoryViewSet, basename='public-category')
router.register(r'tags', PublicTagViewSet, basename='public-tag')
router.register(r'stats', PublicStatsViewSet, basename='public-stats')
router.register(r'clients', TrustedClientsViewSet, basename='public-clients')

urlpatterns = [
    path('', include(router.urls)),
]
