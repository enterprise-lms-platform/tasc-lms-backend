from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    EnrollmentViewSet,
    SessionProgressViewSet,
    CertificateViewSet,
    DiscussionViewSet,
    DiscussionReplyViewSet,
)

router = DefaultRouter()
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'session-progress', SessionProgressViewSet, basename='session-progress')
router.register(r'certificates', CertificateViewSet, basename='certificate')
router.register(r'discussions', DiscussionViewSet, basename='discussion')
router.register(r'discussion-replies', DiscussionReplyViewSet, basename='discussion-reply')

urlpatterns = [
    path('', include(router.urls)),
]