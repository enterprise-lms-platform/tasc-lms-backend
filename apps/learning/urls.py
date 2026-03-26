from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    EnrollmentViewSet,
    SessionProgressViewSet,
    CertificateViewSet,
    DiscussionViewSet,
    DiscussionReplyViewSet,
    ReportViewSet,
    SubmissionViewSet,
    QuizSubmissionViewSet,
    LearningAnalyticsViewSet,
)

router = DefaultRouter()
router.register(r'analytics', LearningAnalyticsViewSet, basename='learning-analytics')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'session-progress', SessionProgressViewSet, basename='session-progress')
router.register(r'certificates', CertificateViewSet, basename='certificate')
router.register(r'discussions', DiscussionViewSet, basename='discussion')
router.register(r'discussion-replies', DiscussionReplyViewSet, basename='discussion-reply')
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'submissions', SubmissionViewSet, basename='submission')
router.register(r'quiz-submissions', QuizSubmissionViewSet, basename='quiz-submission')

urlpatterns = [
    path('', include(router.urls)),
]
