"""Learner-specific views for Learner Flow v1."""

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.mixins import ListModelMixin

from apps.catalogue.models import Course
from apps.accounts.rbac import is_admin_like, is_instructor
from apps.payments.permissions import user_has_active_subscription

from .models import Enrollment
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .serializers_learner import (
    LearnerEnrollmentResponseSerializer,
    LearnerMyCourseSerializer,
)


@extend_schema(tags=['Learner'])
class LearnerCourseViewSet(viewsets.GenericViewSet):
    """ViewSet for learner course enroll action. Browse uses public endpoints."""

    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'
    permission_classes = [IsAuthenticated]
    queryset = Course.objects.filter(status=Course.Status.PUBLISHED)

    @extend_schema(
        summary='Enroll in course',
        description='Enroll in a published course by slug. Idempotent: returns 200 if already enrolled.',
        responses={
            200: LearnerEnrollmentResponseSerializer,
            201: LearnerEnrollmentResponseSerializer,
            400: {'description': 'Validation error'},
            403: {'description': 'Subscription required'},
            404: {'description': 'Course not found or not published'},
        },
    )
    @action(detail=True, methods=['post'], url_path='enroll')
    def enroll(self, request, slug=None):
        """Enroll the authenticated user in a course. Idempotent: 200 if already enrolled."""
        course = self.get_object()

        # Validate allow_self_enrollment
        if not course.allow_self_enrollment:
            return Response(
                {'detail': 'Self-enrollment is not allowed for this course.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate enrollment limit
        if course.enrollment_limit is not None:
            active_count = course.enrollments.filter(status=Enrollment.Status.ACTIVE).count()
            if active_count >= course.enrollment_limit:
                return Response(
                    {'detail': 'Enrollment limit reached.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Validate start_date / end_date
        today = timezone.now().date()
        if course.start_date is not None and today < course.start_date:
            return Response(
                {'detail': 'Course is not yet open for enrollment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if course.end_date is not None and today > course.end_date:
            return Response(
                {'detail': 'Course enrollment has ended.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Subscription check for learners (bypass for admin/instructor)
        if not is_admin_like(request.user) and not is_instructor(request.user):
            if not user_has_active_subscription(request.user):
                return Response(
                    {'detail': 'An active subscription is required to enroll in courses.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Enroll (idempotent)
        enrollment, created = Enrollment.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={
                'paid_amount': course.price or 0,
                'currency': course.currency or 'USD',
            },
        )

        data = {
            'enrollment_id': enrollment.id,
            'course_slug': course.slug,
            'status': enrollment.status,
            'enrolled_at': enrollment.enrolled_at,
            'progress_percentage': enrollment.progress_percentage,
            'message': 'Successfully enrolled.' if created else 'Already enrolled.',
        }
        serializer = LearnerEnrollmentResponseSerializer(data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@extend_schema(tags=['Learner'])
class LearnerMyCoursesViewSet(ListModelMixin, viewsets.GenericViewSet):
    """ViewSet for listing the authenticated user's enrolled courses."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Enrollment.objects.filter(user=self.request.user).select_related(
            'course', 'course__category', 'course__instructor'
        )

        # Filter by status
        status_param = self.request.query_params.get('status', '').strip()
        if status_param and status_param in ['active', 'completed', 'dropped', 'expired']:
            qs = qs.filter(status=status_param)

        # Sort
        sort_param = self.request.query_params.get('sort', 'recent').strip().lower()
        if sort_param == 'active':
            qs = qs.order_by('-last_accessed_at')
        else:
            qs = qs.order_by('-enrolled_at')

        return qs

    @extend_schema(
        summary='List my enrolled courses',
        description='Returns the authenticated user\'s enrolled courses. Supports sort=recent|active and status filter.',
        parameters=[
            OpenApiParameter('sort', str, description='recent (default) or active'),
            OpenApiParameter('status', str, description='active, completed, dropped, expired'),
        ],
        responses={200: LearnerMyCourseSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        data = []
        for e in queryset:
            c = e.course
            cat = c.category
            course_data = {
                'slug': c.slug,
                'title': c.title,
                'thumbnail': c.thumbnail,
                'category': (
                    {'id': cat.id, 'name': cat.name, 'slug': cat.slug}
                    if cat else None
                ),
                'level': c.level,
                'total_sessions': c.total_sessions,
                'instructor_name': (
                    c.instructor.get_full_name() or c.instructor.email
                    if c.instructor else None
                ),
            }
            data.append({
                'enrollment_id': e.id,
                'course': course_data,
                'status': e.status,
                'progress_percentage': e.progress_percentage,
                'enrolled_at': e.enrolled_at,
                'last_accessed_at': e.last_accessed_at,
                'completed_at': e.completed_at,
            })
        serializer = LearnerMyCourseSerializer(data, many=True)
        return Response(serializer.data)
