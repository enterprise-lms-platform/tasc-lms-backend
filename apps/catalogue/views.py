from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import (
    Category, Course, Session, Tag
)
from .permissions import IsCourseWriter, CanEditCourse, CanDeleteCourse
from .serializers import (
    TagSerializer, CategorySerializer, CategoryDetailSerializer,
    SessionSerializer, SessionCreateSerializer,
    CourseListSerializer, CourseDetailSerializer, CourseCreateSerializer
)

User = get_user_model()


@extend_schema(
    tags=['Catalogue - Tags'],
    description='Manage course tags for categorization and filtering',
)
class TagViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing course tags."""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]


@extend_schema(
    tags=['Catalogue - Categories'],
    description='Manage course categories with hierarchical structure',
)
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing course categories."""
    queryset = Category.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CategoryDetailSerializer
        return CategorySerializer
    
    @extend_schema(
        summary='Get all categories',
        description='Returns list of all active course categories with optional hierarchical structure',
        parameters=[
            OpenApiParameter(
                name='parent',
                description='Filter by parent category ID (null for top-level categories)',
                type=int,
                required=False
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get category details',
        description='Returns detailed information about a category including its children',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


@extend_schema(
    tags=['Catalogue - Courses'],
    description='Manage courses with full CRUD operations',
)
class CourseViewSet(viewsets.ModelViewSet):
    """ViewSet for managing courses."""
    queryset = Course.objects.all()
    permission_classes = [IsAuthenticated, IsCourseWriter, CanEditCourse, CanDeleteCourse]

    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return CourseCreateSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        queryset = Course.objects.all()
        category = self.request.query_params.get('category', None)
        instructor = self.request.query_params.get('instructor', None)
        tag = self.request.query_params.get('tag', None)
        status_param = self.request.query_params.get('status', None)
        is_published = self.request.query_params.get('is_published', None)

        if category:
            queryset = queryset.filter(category_id=category)
        if instructor:
            queryset = queryset.filter(instructor_id=instructor)
        if tag:
            queryset = queryset.filter(tags__name=tag)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if is_published is not None:
            if is_published.lower() == 'true':
                queryset = queryset.filter(status=Course.Status.PUBLISHED)
            else:
                queryset = queryset.exclude(status=Course.Status.PUBLISHED)

        if self.action in ('update', 'partial_update', 'destroy'):
            role = getattr(self.request.user, 'role', None)
            if role == User.Role.INSTRUCTOR:
                queryset = queryset.filter(instructor_id=self.request.user.id)

        return queryset.distinct()

    @extend_schema(
        summary='List courses',
        description='Returns paginated list of courses with filtering options',
        parameters=[
            OpenApiParameter(name='category', type=int, description='Filter by category ID'),
            OpenApiParameter(name='instructor', type=int, description='Filter by instructor ID'),
            OpenApiParameter(name='tag', type=str, description='Filter by tag name'),
            OpenApiParameter(name='status', type=str, description='Filter by status (draft, published, archived)'),
            OpenApiParameter(name='is_published', type=bool, description='Filter by published status (true => published only, false => exclude published)'),
        ],
        responses={200: CourseListSerializer},
        examples=[
            OpenApiExample(
                'Course list (minimal)',
                value={
                    'count': 1,
                    'next': None,
                    'previous': None,
                    'results': [
                        {
                            'id': 1,
                            'title': 'Course 001',
                            'slug': 'course-001',
                            'short_description': 'Short summary',
                            'category': {'id': 1, 'name': 'Web Dev', 'slug': 'web-dev'},
                            'level': 'beginner',
                            'price': '0.00',
                            'status': 'draft',
                            'instructor_name': 'Jane Doe',
                        }
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        save_kwargs = {'created_by': self.request.user}
        role = getattr(self.request.user, 'role', None)
        if role == User.Role.INSTRUCTOR:
            save_kwargs['instructor'] = self.request.user
        elif serializer.validated_data.get('instructor') is None:
            save_kwargs['instructor'] = self.request.user
        instance = serializer.save(**save_kwargs)
        from apps.audit.services import log_event

        log_event(
            action="created",
            resource="course",
            resource_id=str(instance.id),
            actor=self.request.user,
            request=self.request,
            details=f"Course created: {instance.title} (status={instance.status})",
        )
        if instance.status == Course.Status.PUBLISHED and instance.published_at is None:
            instance.published_at = timezone.now()
            instance.save(update_fields=['published_at'])

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        old_title = serializer.instance.title
        instance = serializer.save()
        from apps.audit.services import log_event

        detail_parts = [f"Course updated: {instance.title}"]
        if old_title != instance.title:
            detail_parts.append(f"title: '{old_title}' -> '{instance.title}'")
        if old_status != instance.status:
            detail_parts.append(f"status: {old_status} -> {instance.status}")
            if old_status != Course.Status.PUBLISHED and instance.status == Course.Status.PUBLISHED:
                detail_parts.append("published")
            if old_status == Course.Status.PUBLISHED and instance.status != Course.Status.PUBLISHED:
                detail_parts.append("unpublished")

        log_event(
            action="updated",
            resource="course",
            resource_id=str(instance.id),
            actor=self.request.user,
            request=self.request,
            details=" | ".join(detail_parts),
        )

    @extend_schema(
        summary='Create course',
        description=(
            'Create a new course. Requires instructor or admin permissions.\n\n'
            '**Publish-time validation** (when `status=published`):\n'
            '- `thumbnail` must be a non-empty URL.\n'
            '- At least 4 non-empty learning objectives must be provided via '
            '`learning_objectives_list` (array) **or** `learning_objectives` (newline-separated string).\n\n'
            '**learning_objectives sync**: when `learning_objectives_list` is provided, '
            '`learning_objectives` is automatically set to the newline-joined string.'
        ),
        request=CourseCreateSerializer,
        responses={201: CourseDetailSerializer},
        examples=[
            OpenApiExample(
                'Draft course (minimal)',
                value={
                    'title': 'Advanced React Patterns',
                    'description': 'Full course description here.',
                    'short_description': 'Master advanced React patterns.',
                    'subcategory': 'react',
                    'category': 1,
                    'level': 'intermediate',
                    'price': '129.99',
                    'currency': 'USD',
                    'discount_percentage': 0,
                    'duration_hours': 24,
                    'duration_minutes': 30,
                    'duration_weeks': 8,
                    'total_sessions': 48,
                    'status': 'draft',
                    'featured': False,
                    'is_public': False,
                    'allow_self_enrollment': True,
                    'certificate_on_completion': False,
                    'enable_discussions': False,
                    'sequential_learning': False,
                    'enrollment_limit': None,
                    'access_duration': 'lifetime',
                    'start_date': None,
                    'end_date': None,
                    'grading_config': {
                        'gradingScale': 'letter',
                        'weightingMode': 'weighted',
                        'passingThreshold': 60,
                        'letterGradeThresholds': {'A': 90, 'B': 80, 'C': 70, 'D': 60},
                        'categories': [
                            {'id': 'assignments', 'name': 'Assignments', 'weight': 40},
                            {'id': 'quizzes', 'name': 'Quizzes', 'weight': 30},
                            {'id': 'projects', 'name': 'Projects', 'weight': 20},
                            {'id': 'participation', 'name': 'Participation', 'weight': 10},
                        ],
                    },
                    'learning_objectives_list': [],
                    'prerequisites': '',
                    'target_audience': '',
                },
                request_only=True,
            ),
            OpenApiExample(
                'Published course (with objectives)',
                value={
                    'title': 'Advanced React Patterns',
                    'description': 'Full course description here.',
                    'thumbnail': 'https://cdn.example.com/courses/react-patterns.jpg',
                    'status': 'published',
                    'learning_objectives_list': [
                        'Build production-ready React applications using advanced patterns',
                        'Implement render props and higher-order components',
                        'Create custom hooks for reusable logic',
                        'Optimize React applications for performance',
                    ],
                },
                request_only=True,
            ),
            OpenApiExample(
                'Course created (response)',
                value={
                    'id': 1,
                    'title': 'Advanced React Patterns',
                    'slug': 'advanced-react-patterns',
                    'category': {'id': 1, 'name': 'Web Development', 'slug': 'web-development'},
                    'level': 'intermediate',
                    'price': '129.99',
                    'status': 'draft',
                    'instructor_name': 'Jane Doe',
                    'learning_objectives': '',
                    'learning_objectives_list': [],
                },
                response_only=True,
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        detail_serializer = CourseDetailSerializer(serializer.instance, context=self.get_serializer_context())
        data = detail_serializer.data
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(
        summary='Get course details',
        description='Returns detailed information about a course including sessions',
        responses={200: CourseDetailSerializer},
        examples=[
            OpenApiExample(
                'Course detail (minimal)',
                value={
                    'id': 1,
                    'title': 'Course 001',
                    'slug': 'course-001',
                    'short_description': 'Short summary',
                    'description': 'Intro course description',
                    'category': {'id': 1, 'name': 'Web Dev', 'slug': 'web-dev'},
                    'level': 'beginner',
                    'price': '0.00',
                    'status': 'draft',
                    'instructor_name': 'Jane Doe',
                },
                response_only=True,
            ),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary='Update course',
        description='Update course information. Only instructor or admin can update.',
        request=CourseCreateSerializer,
        responses={200: CourseDetailSerializer},
        examples=[
            OpenApiExample(
                'Minimal course update',
                value={
                    'title': 'Course 001 (Updated)',
                    'short_description': 'Updated short summary',
                    'status': 'draft',
                },
                request_only=True,
            ),
        ],
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary='Partially update course',
        description='Patch course fields. Only instructor or admin can update.',
        request=CourseCreateSerializer,
        responses={200: CourseDetailSerializer},
        examples=[
            OpenApiExample(
                'Minimal course patch',
                value={
                    'title': 'Course 001 (Updated)',
                    'short_description': 'Updated short summary',
                    'status': 'draft',
                },
                request_only=True,
            ),
            OpenApiExample(
                'Course patched (minimal)',
                value={
                    'id': 1,
                    'title': 'Course 001 (Updated)',
                    'slug': 'course-001',
                    'short_description': 'Updated short summary',
                    'status': 'draft',
                },
                response_only=True,
            ),
        ],
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        summary='Delete course',
        description='Delete a course. Only LMS Manager or TASC Admin can delete.',
        responses={204: None},
        examples=[
            OpenApiExample(
                'Delete forbidden',
                value={'detail': 'Only LMS Manager or TASC Admin can delete courses.'},
                response_only=True,
            ),
            OpenApiExample(
                'Delete success',
                value=None,
                response_only=True,
            ),
        ],
    )
    def destroy(self, request, *args, **kwargs):
        if getattr(request.user, 'role', None) not in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            raise PermissionDenied('Only LMS Manager or TASC Admin can delete courses.')
        instance = self.get_object()
        from apps.audit.services import log_event

        log_event(
            action="deleted",
            resource="course",
            resource_id=str(instance.id),
            actor=request.user,
            request=request,
            details=f"Course deleted: {instance.title} (status={instance.status})",
        )
        return super().destroy(request, *args, **kwargs)


@extend_schema(
    tags=['Catalogue - Sessions'],
    description='Manage course sessions (video, text, live)',
)
class SessionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing course sessions."""
    queryset = Session.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return SessionCreateSerializer
        return SessionSerializer
    
    def get_queryset(self):
        queryset = Session.objects.all()
        course = self.request.query_params.get('course', None)
        session_type = self.request.query_params.get('type', None)
        
        if course:
            queryset = queryset.filter(course_id=course)
        if session_type:
            queryset = queryset.filter(session_type=session_type)
        
        return queryset.order_by('order')
    
    @extend_schema(
        summary='List sessions',
        description='Returns list of sessions with filtering by course and type',
        parameters=[
            OpenApiParameter(name='course', type=int, description='Filter by course ID'),
            OpenApiParameter(name='type', type=str, description='Filter by session type (video, text, live)'),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Create session',
        description='Create a new session for a course',
        request=SessionCreateSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
