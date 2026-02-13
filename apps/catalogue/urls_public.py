from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_public import (
    PublicCourseViewSet,
    PublicCategoryViewSet,
    PublicTagViewSet,
)

# Router for public catalogue endpoints
router = DefaultRouter()
router.register(r'courses', PublicCourseViewSet, basename='public-course')
router.register(r'categories', PublicCategoryViewSet, basename='public-category')
router.register(r'tags', PublicTagViewSet, basename='public-tag')

urlpatterns = [
    path('', include(router.urls)),
]
