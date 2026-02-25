from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_public import (
    CategoryManagementViewSet,
    PublicCourseViewSet,
    PublicCategoryViewSet,
    PublicTagViewSet,
)

# Router for public catalogue endpoints
router = DefaultRouter()
router.register(r'courses', PublicCourseViewSet, basename='public-course')
router.register(r'categories', PublicCategoryViewSet, basename='public-category')
router.register(r'tags', PublicTagViewSet, basename='public-tag')

# Router for management endpoints (LMS Manager only)
management_router = DefaultRouter()
management_router.register(r'categories', CategoryManagementViewSet, basename='manage-category')

urlpatterns = [
    path('', include(router.urls)),
    path('management/', include(management_router.urls)),

    path('manage/categories/bulk/', CategoryManagementViewSet.as_view({'post': 'bulk'}), name='manage-category-bulk'),
    path('manage/categories/tree/', CategoryManagementViewSet.as_view({'get': 'tree'}), name='manage-category-tree'),
    path('manage/categories/statistics/', CategoryManagementViewSet.as_view({'get': 'statistics'}), name='manage-category-statistics'),

]
