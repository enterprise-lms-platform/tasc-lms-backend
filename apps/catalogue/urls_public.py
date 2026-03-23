from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_public import (
    PublicCourseViewSet,
    PublicCategoryViewSet,
    PublicTagViewSet,
    PublicStatsViewSet,
    TrustedClientsViewSet,
)
from apps.payments.views_public import PublicSubscriptionPlanViewSet

# Router for public catalogue and shared public endpoints
router = DefaultRouter()
router.register(r'courses', PublicCourseViewSet, basename='public-course')
router.register(r'subscription-plans', PublicSubscriptionPlanViewSet, basename='public-subscription-plans')
router.register(r'categories', PublicCategoryViewSet, basename='public-category')
router.register(r'tags', PublicTagViewSet, basename='public-tag')
router.register(r'stats', PublicStatsViewSet, basename='public-stats')
router.register(r'clients', TrustedClientsViewSet, basename='public-clients')

urlpatterns = [
    path('', include(router.urls)),
]
