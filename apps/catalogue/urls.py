from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    TagViewSet,
    CategoryViewSet,
    CourseViewSet,
    ModuleViewSet,
    SessionViewSet,
)

router = DefaultRouter()
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'modules', ModuleViewSet, basename='module')
router.register(r'sessions', SessionViewSet, basename='session')

urlpatterns = [
    path('', include(router.urls)),
]
