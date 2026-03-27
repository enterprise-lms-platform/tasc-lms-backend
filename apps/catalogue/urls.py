from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    SessionAttachmentViewSet,
    TagViewSet,
    CategoryViewSet,
    CourseViewSet,
    CourseApprovalRequestViewSet,
    ModuleViewSet,
    SessionViewSet,
    QuestionCategoryViewSet,
    BankQuestionViewSet,
    CourseReviewViewSet,
    CatalogueAnalyticsViewSet,
)

router = DefaultRouter()
router.register(r'analytics', CatalogueAnalyticsViewSet, basename='catalogue-analytics')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'question-categories', QuestionCategoryViewSet, basename='question-category')
router.register(r'bank-questions', BankQuestionViewSet, basename='bank-question')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'approval-requests', CourseApprovalRequestViewSet, basename='approval-request')
router.register(r'modules', ModuleViewSet, basename='module')
router.register(r'sessions', SessionViewSet, basename='session')
router.register(r'session-attachments', SessionAttachmentViewSet, basename='session-attachment')
router.register(r'course-reviews', CourseReviewViewSet, basename='course-review')

urlpatterns = [
    path('', include(router.urls)),
]
