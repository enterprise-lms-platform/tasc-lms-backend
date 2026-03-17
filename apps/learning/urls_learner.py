"""URL configuration for learner-specific endpoints."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_learner import LearnerCourseViewSet, LearnerMyCoursesViewSet

router = DefaultRouter()
router.register(r'courses', LearnerCourseViewSet, basename='learner-course')
router.register(r'my-courses', LearnerMyCoursesViewSet, basename='learner-my-courses')

urlpatterns = [
    path('', include(router.urls)),
]
