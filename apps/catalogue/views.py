from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from django.db import transaction
from django.db.models import Max, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.accounts.rbac import is_admin_like
from apps.common.spaces import create_boto3_client, delete_spaces_object
from apps.payments.permissions import HasActiveSubscription
from apps.learning.models import Enrollment, QuizSubmission, Submission

from .models import (
    Assignment, BankQuestion, Category, Course, CourseApprovalRequest, Module,
    Quiz, QuizQuestion, QuestionCategory, Session, Tag, CourseReview, SessionAttachment
)
from .permissions import (
    CanEditBankQuestion, CanEditQuestionCategory, CanEditCourse,
    CanDeleteCourse, CanEditModuleCourse, CanEditSessionCourse,
    IsApprovalManager, IsCategoryManagerOrReadOnly, IsCourseWriter,
)
from .serializers import (
    AddFromBankSerializer, AssignmentCreateUpdateSerializer, AssignmentSerializer,
    BankQuestionListSerializer, BankQuestionSerializer,
    CategoryDetailSerializer, CategorySerializer,
    CourseCreateSerializer, CourseDetailSerializer, CourseListSerializer,
    ModuleSerializer, ModuleBulkReorderSerializer,
    QuestionCategorySerializer,
    QuizDetailSerializer, QuizQuestionListWriteSerializer, QuizQuestionSerializer,
    QuizSettingsUpdateSerializer, QuizSessionSummarySerializer,
    SessionCreateSerializer, SessionSerializer,
    TagSerializer, CourseReviewSerializer, CourseReviewCreateSerializer,
    CourseReviewSummarySerializer,     CourseApprovalRequestSerializer, ApproveActionSerializer, RejectActionSerializer, SessionAttachmentSerializer,
)
from apps.learning.serializers import (
    QuizSubmissionCreateSerializer, QuizSubmissionSerializer,
    SubmissionCreateSerializer, SubmissionSerializer
)

User = get_user_model()


def _coerce_quiz_question_points(pts, existing_points=None):
    """
    Parse points for quiz_questions PUT. None preserves existing on update, else defaults to 0.
    Raises ValidationError (400) for invalid values.
    """
    if pts is None:
        if existing_points is not None:
            return max(0, int(existing_points))
        return 0
    try:
        v = int(pts)
    except (TypeError, ValueError):
        raise ValidationError(
            {'questions': ['Invalid points value; must be a non-negative integer.']}
        )
    if v < 0:
        raise ValidationError({'questions': ['points must be >= 0.']})
    return v


class CataloguePageNumberPagination(PageNumberPagination):
    """Pagination for catalogue list endpoints (tags, categories)."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


@extend_schema(
    tags=['Catalogue - Tags'],
    description='Manage course tags for categorization and filtering',
)
class TagViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing course tags."""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CataloguePageNumberPagination


@extend_schema(
    tags=['Catalogue - Question Bank - Categories'],
    description='Instructor-owned categories for organizing bank questions',
)
class QuestionCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for question categories. Instructors see own; managers/admins see all."""
    serializer_class = QuestionCategorySerializer
    permission_classes = [IsAuthenticated, IsCourseWriter, CanEditQuestionCategory]
    pagination_class = CataloguePageNumberPagination

    def get_queryset(self):
        role = getattr(self.request.user, 'role', None)
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            return QuestionCategory.objects.all()
        return QuestionCategory.objects.filter(owner_id=self.request.user.id)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@extend_schema(
    tags=['Catalogue - Question Bank'],
    description='Instructor-owned reusable questions for the question bank',
)
class BankQuestionViewSet(viewsets.ModelViewSet):
    """ViewSet for bank questions. Instructors see own; managers/admins see all."""
    permission_classes = [IsAuthenticated, IsCourseWriter, CanEditBankQuestion]
    pagination_class = CataloguePageNumberPagination

    def get_serializer_class(self):
        if self.action == 'list':
            return BankQuestionListSerializer
        return BankQuestionSerializer

    def get_queryset(self):
        role = getattr(self.request.user, 'role', None)
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            qs = BankQuestion.objects.all()
        else:
            qs = BankQuestion.objects.filter(owner_id=self.request.user.id)
        qs = qs.select_related('category').order_by('-created_at')
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        category = request.query_params.get('category')
        if category is not None:
            try:
                cid = int(category)
                queryset = queryset.filter(category_id=cid)
            except (ValueError, TypeError):
                pass
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(question_text__icontains=search)
        qtype = request.query_params.get('question_type', '').strip()
        if qtype:
            queryset = queryset.filter(question_type=qtype)
        difficulty = request.query_params.get('difficulty', '').strip()
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        tag = request.query_params.get('tags', '').strip()
        if tag:
            queryset = queryset.filter(tags__contains=[tag])
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


@extend_schema(
    tags=['Catalogue - Categories'],
    description='Manage course categories with hierarchical structure',
)
class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing course categories."""
    queryset = Category.objects.all()
    permission_classes = [IsAuthenticated, IsCategoryManagerOrReadOnly]
    pagination_class = CataloguePageNumberPagination

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CategoryDetailSerializer
        return CategorySerializer

    def get_queryset(self):
        role = getattr(self.request.user, 'role', None)
        # Managers/admins can manage both active and inactive categories.
        # Other authenticated users (learners/instructors) only see active categories.
        if role in (User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
            queryset = Category.objects.all()
        else:
            queryset = Category.objects.filter(is_active=True)

        parent_val = self.request.query_params.get('parent')
        if parent_val is None:
            return queryset
        if parent_val.strip().lower() in ('', 'null'):
            return queryset.filter(parent__isnull=True)
        try:
            parent_id = int(parent_val)
        except (ValueError, TypeError):
            raise ValidationError({
                'parent': ['Invalid parent id. Must be an integer or \'null\'.']
            })
        return queryset.filter(parent_id=parent_id)

    @extend_schema(
        summary='Get all categories',
        description='Returns list of all active course categories with optional hierarchical structure',
        parameters=[
            OpenApiParameter(
                name='parent',
                description=(
                    'Filter by parent: omit for all; empty or "null" for root categories; '
                    'integer ID for children of that parent.'
                ),
                type=str,
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
        operation_id='catalogue_categories_create',
        summary='Create Category',
        description='Create a course category (root or subcategory). Only LMS Manager or TASC Admin.',
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)


@extend_schema(
    tags=['Catalogue - Courses'],
    description='Manage courses with full CRUD operations',
)
class CourseViewSet(viewsets.ModelViewSet):
    """ViewSet for managing courses."""
    queryset = Course.objects.all()
    permission_classes = [IsAuthenticated, IsCourseWriter, CanEditCourse, CanDeleteCourse]

    from rest_framework.filters import OrderingFilter, SearchFilter
    filter_backends = [OrderingFilter, SearchFilter]
    ordering_fields = ['title', 'price', 'published_at', 'created_at', 'enrollment_count']
    search_fields = ['title', 'short_description']

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

        if self.action in ('update', 'partial_update', 'destroy', 'submit_for_approval'):
            role = getattr(self.request.user, 'role', None)
            if role == User.Role.INSTRUCTOR:
                queryset = queryset.filter(instructor_id=self.request.user.id)

        return queryset.annotate(
            enrollment_count=Count('enrollments')
        ).distinct()

    @extend_schema(
        summary='Course statistics (superadmin)',
        description='Returns aggregate course counts for admin dashboards',
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Admin-level course statistics."""
        qs = Course.objects.all()
        return Response({
            'total': qs.count(),
            'published': qs.filter(status=Course.Status.PUBLISHED).count(),
            'draft': qs.filter(status=Course.Status.DRAFT).count(),
            'archived': qs.filter(status=Course.Status.ARCHIVED).count(),
            'pending_approval': qs.filter(status=Course.Status.PENDING_APPROVAL).count(),
        })

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
        summary='Submit course for approval',
        description='Submit a draft or rejected course for manager review. Creates an approval request and sets course status to pending_approval. Only the course owner (instructor) or manager/admin can submit.',
        responses={200: CourseDetailSerializer},
    )
    @action(detail=True, methods=['post'], url_path='submit-for-approval')
    def submit_for_approval(self, request, pk=None):
        course = self.get_object()

        # Prevent duplicate pending requests (check first, before status)
        if CourseApprovalRequest.objects.filter(
            course=course,
            status=CourseApprovalRequest.Status.PENDING,
        ).exists():
            raise ValidationError({
                'detail': 'This course already has a pending approval request.'
            })

        # Only draft or rejected courses can be submitted
        if course.status not in (Course.Status.DRAFT, Course.Status.REJECTED):
            raise ValidationError({
                'detail': f'Only draft or rejected courses can be submitted for approval. Current status: {course.status}.'
            })

        # Determine request_type: create for first submission, edit for resubmission
        has_prior = CourseApprovalRequest.objects.filter(course=course).exclude(
            status=CourseApprovalRequest.Status.PENDING,
        ).exists()
        request_type = CourseApprovalRequest.RequestType.EDIT if has_prior else CourseApprovalRequest.RequestType.CREATE

        with transaction.atomic():
            approval = CourseApprovalRequest.objects.create(
                course=course,
                request_type=request_type,
                requested_by=request.user,
                status=CourseApprovalRequest.Status.PENDING,
            )
            course.status = Course.Status.PENDING_APPROVAL
            course.rejection_reason = ''  # Clear on resubmit
            course.save(update_fields=['status', 'rejection_reason', 'updated_at'])

        from apps.audit.services import log_event
        log_event(
            action='submitted_for_approval',
            resource='course',
            resource_id=str(course.id),
            actor=request.user,
            request=request,
            details=f"Course submitted for approval: {course.title} (request #{approval.id})",
        )

        serializer = CourseDetailSerializer(course, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

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
    tags=['Catalogue - Course Approvals'],
    description='List and view course approval requests (LMS Manager / TASC Admin only)',
)
class CourseApprovalRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for approval requests. List and retrieve only (Phase 1)."""
    queryset = CourseApprovalRequest.objects.select_related('course', 'requested_by', 'reviewed_by')
    serializer_class = CourseApprovalRequestSerializer
    permission_classes = [IsAuthenticated, IsApprovalManager]
    pagination_class = CataloguePageNumberPagination

    def get_queryset(self):
        queryset = CourseApprovalRequest.objects.select_related(
            'course', 'requested_by', 'reviewed_by'
        )
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        request_type = self.request.query_params.get('request_type')
        if request_type:
            queryset = queryset.filter(request_type=request_type)
        course_id = self.request.query_params.get('course')
        if course_id is not None:
            try:
                queryset = queryset.filter(course_id=int(course_id))
            except (ValueError, TypeError):
                pass
        return queryset.order_by('-created_at')

    @extend_schema(
        summary='Approve course',
        description='Approve a pending approval request. Sets course status to published.',
        request=ApproveActionSerializer,
        responses={200: CourseApprovalRequestSerializer},
    )
    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        approval = self.get_object()
        if approval.status != CourseApprovalRequest.Status.PENDING:
            raise ValidationError({
                'detail': f'Only pending requests can be approved. Current status: {approval.status}.'
            })

        serializer = ApproveActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        comments = (serializer.validated_data.get('reviewer_comments') or '').strip()

        with transaction.atomic():
            approval.status = CourseApprovalRequest.Status.APPROVED
            approval.reviewed_by = request.user
            approval.reviewed_at = timezone.now()
            approval.reviewer_comments = comments
            approval.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reviewer_comments', 'updated_at'])

            course = approval.course
            course.status = Course.Status.PUBLISHED
            if course.published_at is None:
                course.published_at = timezone.now()
            course.rejection_reason = ''
            course.save(update_fields=['status', 'published_at', 'rejection_reason', 'updated_at'])

        from apps.audit.services import log_event
        log_event(
            action='updated',
            resource='course',
            resource_id=str(course.id),
            actor=request.user,
            request=request,
            details=f"Course approved: {course.title} (approval #{approval.id})",
        )

        out_serializer = CourseApprovalRequestSerializer(approval)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Reject course',
        description='Reject a pending approval request. reviewer_comments is required. Sets course status to rejected.',
        request=RejectActionSerializer,
        responses={200: CourseApprovalRequestSerializer},
    )
    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        approval = self.get_object()
        if approval.status != CourseApprovalRequest.Status.PENDING:
            raise ValidationError({
                'detail': f'Only pending requests can be rejected. Current status: {approval.status}.'
            })

        serializer = RejectActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comments = (serializer.validated_data.get('reviewer_comments') or '').strip()
        if not comments:
            raise ValidationError({'reviewer_comments': ['A reason for rejection is required.']})

        with transaction.atomic():
            approval.status = CourseApprovalRequest.Status.REJECTED
            approval.reviewed_by = request.user
            approval.reviewed_at = timezone.now()
            approval.reviewer_comments = comments
            approval.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reviewer_comments', 'updated_at'])

            course = approval.course
            course.status = Course.Status.REJECTED
            course.rejection_reason = comments
            course.save(update_fields=['status', 'rejection_reason', 'updated_at'])

        from apps.audit.services import log_event
        log_event(
            action='updated',
            resource='course',
            resource_id=str(course.id),
            actor=request.user,
            request=request,
            details=f"Course rejected: {course.title} (approval #{approval.id})",
        )

        out_serializer = CourseApprovalRequestSerializer(approval)
        return Response(out_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Catalogue - Modules'],
    description='Manage course modules (groupings of sessions)',
)
class ModuleViewSet(viewsets.ModelViewSet):
    """ViewSet for managing course modules."""

    queryset = Module.objects.all()
    permission_classes = [IsAuthenticated, IsCourseWriter, CanEditModuleCourse]
    serializer_class = ModuleSerializer

    def get_queryset(self):
        queryset = Module.objects.all()
        course = self.request.query_params.get('course', None)

        if course:
            queryset = queryset.filter(course_id=course)

        if self.action in ('update', 'partial_update', 'destroy'):
            role = getattr(self.request.user, 'role', None)
            if role == User.Role.INSTRUCTOR:
                queryset = queryset.filter(course__instructor_id=self.request.user.id)

        return queryset.order_by('order')

    def create(self, request, *args, **kwargs):
        data = dict(request.data)
        # Handle QueryDict list values (e.g. data['course'] = [1])
        for key in list(data):
            if isinstance(data[key], list) and len(data[key]) == 1:
                data[key] = data[key][0]
        # Auto-assign order when client omitted it. Overwrite with computed next_order
        # to avoid unique constraint violation (model default 0 would collide).
        if data.get('course') is not None:
            course_id = data['course']
            max_order = Module.objects.filter(course_id=course_id).aggregate(
                max_order=Max('order')
            )['max_order']
            next_order = (max_order + 1) if max_order is not None else 0
            # Overwrite order: client-sent order can cause unique violation when model
            # default 0 is used; always use computed next_order for create.
            data['order'] = next_order
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        course = serializer.validated_data.get('course')
        user = self.request.user
        role = getattr(user, 'role', None)
        if role == User.Role.INSTRUCTOR and course.instructor_id != user.id:
            raise PermissionDenied('You can only create modules in your own courses.')
        serializer.save()

    @extend_schema(
        summary='List modules',
        description='Returns list of modules with optional filtering by course',
        parameters=[
            OpenApiParameter(name='course', type=int, description='Filter by course ID'),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Bulk reorder modules',
        description='Update the order of multiple modules for a specific course in a single request.',
        request=ModuleBulkReorderSerializer,
        responses={200: dict},
        examples=[
            OpenApiExample(
                'Reorder example',
                value={'course': 5, 'order': [{'id': 10, 'order': 0}, {'id': 11, 'order': 1}]},
                request_only=True,
            ),
        ]
    )
    @action(detail=False, methods=['post'])
    def reorder(self, request):
        serializer = ModuleBulkReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course_id = serializer.validated_data['course']
        order_data = serializer.validated_data['order']
        course = get_object_or_404(Course, id=course_id)
        role = getattr(request.user, 'role', None)
        if role == User.Role.INSTRUCTOR and course.instructor_id != request.user.id:
            raise PermissionDenied('You can only reorder modules in your own courses.')
        module_ids = [item['id'] for item in order_data]
        modules = list(Module.objects.filter(id__in=module_ids, course_id=course_id))
        if len(modules) != len(module_ids):
            raise ValidationError('One or more modules do not belong to the specified course or do not exist.')
        order_map = {item['id']: item['order'] for item in order_data}
        for module in modules:
            module.order = order_map[module.id]
        with transaction.atomic():
            Module.objects.bulk_update(modules, ['order'])
        return Response({'updated': len(modules)}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Catalogue - Sessions'],
    description='Manage course sessions (video, text, live)',
)
class SessionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing course sessions."""
    queryset = Session.objects.all()
    permission_classes = [IsAuthenticated, IsCourseWriter, CanEditSessionCourse]
    pagination_class = CataloguePageNumberPagination

    def get_permissions(self):
        if self.action == 'submit':
            return [IsAuthenticated()]
        perms = list(super().get_permissions())
        if self.action == 'asset_url':
            perms.append(HasActiveSubscription())
        return perms

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

        if self.action in ('list', 'update', 'partial_update', 'destroy', 'quiz', 'quiz_questions', 'add_from_bank', 'assignment'):
            role = getattr(self.request.user, 'role', None)
            if role == User.Role.INSTRUCTOR:
                queryset = queryset.filter(course__instructor_id=self.request.user.id)

        return queryset.order_by('order')

    def _get_or_create_quiz(self, session):
        """Return Quiz for session. 404 if session_type != 'quiz'."""
        if session.session_type != Session.SessionType.QUIZ:
            return None
        quiz, _ = Quiz.objects.get_or_create(session=session, defaults={'settings': {}})
        return quiz

    def _get_assignment(self, session):
        """Return Assignment if exists; do not create. None if session_type != 'assignment'."""
        if session.session_type != Session.SessionType.ASSIGNMENT:
            return None
        try:
            return session.assignment
        except Assignment.DoesNotExist:
            return None

    def _get_or_create_assignment(self, session):
        """Return Assignment for session, creating if missing. None if session_type != 'assignment'."""
        if session.session_type != Session.SessionType.ASSIGNMENT:
            return None
        assignment, _ = Assignment.objects.get_or_create(
            session=session,
            defaults={
                'assignment_type': 'project',
                'instructions': '',
                'max_points': 100,
                'penalty_type': 'none',
                'penalty_percent': 0,
            },
        )
        return assignment

    def perform_create(self, serializer):
        course = serializer.validated_data.get('course')
        user = self.request.user
        role = getattr(user, 'role', None)
        if role == User.Role.INSTRUCTOR and course.instructor_id != user.id:
            raise PermissionDenied('You can only create sessions in your own courses.')
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        old_key = (instance.asset_object_key or "").strip()
        old_bucket = (instance.asset_bucket or "").strip()

        serializer.save()

        new_key = (instance.asset_object_key or "").strip()
        if old_key and old_key != new_key:
            bucket = old_bucket or getattr(settings, "DO_SPACES_PRIVATE_BUCKET", "")
            if bucket:
                delete_spaces_object(bucket, old_key)

    def perform_destroy(self, instance):
        old_key = (instance.asset_object_key or "").strip()
        old_bucket = (instance.asset_bucket or "").strip()

        instance.delete()

        if old_key:
            bucket = old_bucket or getattr(settings, "DO_SPACES_PRIVATE_BUCKET", "")
            if bucket:
                delete_spaces_object(bucket, old_key)

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
        responses={201: SessionSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        read_serializer = SessionSerializer(serializer.instance)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        return Response(SessionSerializer(serializer.instance).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary='Get presigned URL for session asset',
        description='Returns a short-lived presigned GET URL for the session private asset in Spaces.',
        responses={
            200: OpenApiResponse(
                description='Presigned URL',
                response=dict,
                examples=[OpenApiExample(
                    'Asset URL response',
                    value={'url': 'https://bucket.region.digitaloceanspaces.com/key?X-Amz-...', 'expires_in': 300, 'method': 'GET'},
                    response_only=True,
                )],
            ),
            403: OpenApiResponse(description='Not allowed to access this session asset'),
            404: OpenApiResponse(description='Session has no asset or session not found'),
            503: OpenApiResponse(description='Spaces not configured'),
        },
    )
    @action(detail=True, methods=['get'], url_path='asset-url')
    def asset_url(self, request, pk=None):
        session = get_object_or_404(Session, pk=pk)
        user = request.user

        # Access control: LMS_MANAGER and TASC_ADMIN always; INSTRUCTOR if course owner; LEARNER if enrolled
        if is_admin_like(user):
            pass
        elif user.role == User.Role.INSTRUCTOR:
            if session.course.instructor_id != user.id:
                return Response(
                    {'detail': 'You do not have permission to access this session asset.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif user.role == User.Role.LEARNER:
            if not Enrollment.objects.filter(user=user, course=session.course).exists():
                return Response(
                    {'detail': 'You must be enrolled in this course to access session assets.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            return Response(
                {'detail': 'You do not have permission to access this session asset.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not (session.asset_object_key or '').strip():
            return Response(
                {'detail': 'This session has no uploaded asset.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        bucket = (session.asset_bucket or '').strip() or getattr(settings, 'DO_SPACES_PRIVATE_BUCKET', None)
        if not bucket:
            return Response(
                {'detail': 'Spaces private bucket is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        required = ('DO_SPACES_ENDPOINT', 'DO_SPACES_ACCESS_KEY_ID', 'DO_SPACES_SECRET_ACCESS_KEY')
        if not all(getattr(settings, k, None) for k in required):
            return Response(
                {'detail': 'Spaces is not configured for presigned URLs.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        expires_in = getattr(settings, 'DO_SPACES_PRESIGN_EXPIRY_SECONDS', 300)
        s3_client = create_boto3_client()
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': session.asset_object_key},
            ExpiresIn=expires_in,
        )

        return Response({
            'url': url,
            'expires_in': expires_in,
            'method': 'GET',
        })

    @extend_schema(
        summary='Submit quiz or assignment (Learner)',
        description='Learner-facing endpoint to submit work for this session. '
                    'Infers Enrollment and Quiz/Assignment from session context.',
        request=None,
        responses={201: dict, 403: dict, 404: dict},
    )
    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        session = self.get_object()
        user = request.user

        # 1. Find Enrollment
        enrollment = Enrollment.objects.filter(user=user, course=session.course).first()
        if not enrollment:
            return Response(
                {'detail': 'You must be enrolled in this course to submit work.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Identify Work Type and Submit
        if session.session_type == Session.SessionType.QUIZ:
            quiz = self._get_or_create_quiz(session)
            if not quiz:
                return Response({'detail': 'Quiz not found for this session.'}, status=status.HTTP_404_NOT_FOUND)

            data = request.data.copy()
            data['quiz'] = quiz.id
            data['enrollment'] = enrollment.id

            serializer = QuizSubmissionCreateSerializer(data=data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            submission = serializer.save()
            return Response(QuizSubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)

        elif session.session_type == Session.SessionType.ASSIGNMENT:
            assignment = self._get_assignment(session)
            if not assignment:
                return Response({'detail': 'Assignment not found for this session.'}, status=status.HTTP_404_NOT_FOUND)

            data = request.data.copy()
            data['assignment'] = assignment.id
            data['enrollment'] = enrollment.id

            serializer = SubmissionCreateSerializer(data=data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            submission = serializer.save()
            return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)

        else:
            return Response(
                {'detail': 'This session type does not support submissions.'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _build_quiz_detail_response(self, session, quiz):
        """Build QuizDetailSerializer payload for GET/PATCH responses."""
        session_data = {
            'id': session.id,
            'title': session.title,
            'description': session.description or '',
            'status': session.status,
        }
        questions = quiz.questions.all().order_by('order', 'id')
        return {
            'quiz_id': quiz.id,
            'session': session_data,
            'settings': quiz.settings or {},
            'questions': QuizQuestionSerializer(questions, many=True).data,
        }

    @extend_schema(
        summary='Get or update quiz for a session',
        description='GET: Returns quiz detail. POST: Create quiz. PATCH: Merges settings. Only for session_type=quiz.',
        request=QuizSettingsUpdateSerializer,
        responses={
            200: OpenApiResponse(description='Quiz detail'),
            201: OpenApiResponse(description='Quiz created'),
            400: OpenApiResponse(description='Quiz already exists'),
            404: OpenApiResponse(description='Session not found or not a quiz session'),
        },
    )
    @action(detail=True, methods=['get', 'post', 'patch'], url_path='quiz')
    def quiz(self, request, pk=None):
        session = self.get_object()
        if session.session_type != Session.SessionType.QUIZ:
            return Response(
                {'detail': 'Session is not a quiz session.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == 'GET':
            quiz = self._get_or_create_quiz(session)
            return Response(self._build_quiz_detail_response(session, quiz))

        if request.method == 'POST':
            if Quiz.objects.filter(session=session).exists():
                return Response(
                    {'detail': 'Quiz already exists for this session.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            quiz = Quiz.objects.create(session=session, settings=request.data.get('settings', {}))
            return Response(self._build_quiz_detail_response(session, quiz), status=status.HTTP_201_CREATED)

        # PATCH
        quiz = self._get_or_create_quiz(session)
        serializer = QuizSettingsUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        incoming = serializer.validated_data.get('settings', {})
        if isinstance(incoming, dict):
            current = dict(quiz.settings or {})
            current.update(incoming)
            quiz.settings = current
            quiz.save(update_fields=['settings', 'updated_at'])
        return Response(self._build_quiz_detail_response(session, quiz))

    @extend_schema(
        summary='Replace all quiz questions',
        description='PUT: Replace all questions. Create new, update existing, delete omitted. Only for session_type=quiz.',
        request=QuizQuestionListWriteSerializer,
        responses={
            200: OpenApiResponse(description='Updated questions list'),
            404: OpenApiResponse(description='Session not found or not a quiz session'),
        },
    )
    @action(detail=True, methods=['put'], url_path='quiz/questions')
    def quiz_questions(self, request, pk=None):
        session = self.get_object()
        quiz = self._get_or_create_quiz(session)
        if quiz is None:
            return Response(
                {'detail': 'Session is not a quiz session.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = QuizQuestionListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data['questions']
        existing_ids = {q.id for q in quiz.questions.all()}
        seen_ids = set()

        with transaction.atomic():
            for i, item in enumerate(payload):
                qid = item.get('id')
                order_val = item.get('order')
                if order_val is None:
                    order_val = i
                qt = item.get('question_type', 'multiple-choice')
                qtext = (item.get('question_text') or '').strip() or ''
                pts = item.get('points', 10)
                ap = item.get('answer_payload')
                if ap is None:
                    ap = {}
                expl = (item.get('explanation') or '').strip()

                if qid is not None:
                    try:
                        qid = int(qid) if not isinstance(qid, int) else qid
                    except (TypeError, ValueError):
                        raise ValidationError(
                            {'questions': [f'Invalid question id: {qid!r}']}
                        )
                    if qid not in existing_ids:
                        raise ValidationError(
                            {'questions': [f'Question id {qid} does not belong to this quiz.']}
                        )
                    if qid in seen_ids:
                        raise ValidationError(
                            {'questions': [f'Duplicate question id {qid} in payload.']}
                        )
                    seen_ids.add(qid)
                    qobj = QuizQuestion.objects.get(quiz=quiz, id=qid)
                    qobj.order = order_val
                    qobj.question_type = qt
                    qobj.question_text = qtext
                    qobj.points = _coerce_quiz_question_points(pts, existing_points=qobj.points)
                    qobj.answer_payload = ap if isinstance(ap, dict) else {}
                    qobj.explanation = expl
                    qobj.save()
                else:
                    QuizQuestion.objects.create(
                        quiz=quiz,
                        order=order_val,
                        question_type=qt,
                        question_text=qtext,
                        points=_coerce_quiz_question_points(pts, existing_points=None),
                        answer_payload=ap if isinstance(ap, dict) else {},
                        explanation=expl,
                    )
            to_delete = existing_ids - seen_ids
            if to_delete:
                QuizQuestion.objects.filter(quiz=quiz, id__in=to_delete).delete()

        questions = quiz.questions.all().order_by('order', 'id')
        return Response({
            'questions': QuizQuestionSerializer(questions, many=True).data,
        })

    @extend_schema(
        summary='Add bank questions to quiz',
        description='POST: Copy bank questions into quiz as new QuizQuestion rows. Only for session_type=quiz.',
        request=AddFromBankSerializer,
        responses={
            200: OpenApiResponse(description='List of newly added questions'),
            404: OpenApiResponse(description='Session not found or not a quiz session'),
        },
    )
    @action(detail=True, methods=['post'], url_path='quiz/questions/add-from-bank')
    def add_from_bank(self, request, pk=None):
        session = self.get_object()
        quiz = self._get_or_create_quiz(session)
        if quiz is None:
            return Response(
                {'detail': 'Session is not a quiz session.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = AddFromBankSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data['bank_question_ids']
        user = request.user
        role = getattr(user, 'role', None)
        if role == User.Role.INSTRUCTOR:
            bank_questions = BankQuestion.objects.filter(id__in=ids, owner_id=user.id)
        else:
            bank_questions = BankQuestion.objects.filter(id__in=ids)
        bank_questions = list(bank_questions)
        if len(bank_questions) != len(ids):
            seen = {bq.id for bq in bank_questions}
            missing = [i for i in ids if i not in seen]
            return Response(
                {'detail': f'Bank question(s) not found or not accessible: {missing}'},
                status=status.HTTP_404_NOT_FOUND,
            )
        max_order = quiz.questions.aggregate(m=Max('order'))['m']
        next_order = (max_order + 1) if max_order is not None else 0
        created = []
        with transaction.atomic():
            for bq in bank_questions:
                qq = QuizQuestion.objects.create(
                    quiz=quiz,
                    order=next_order,
                    question_type=bq.question_type,
                    question_text=bq.question_text,
                    points=bq.points,
                    answer_payload=dict(bq.answer_payload or {}),
                    explanation=bq.explanation or '',
                    source_bank_question=bq,
                )
                created.append(qq)
                next_order += 1
        questions = quiz.questions.filter(id__in=[q.id for q in created]).order_by('order', 'id')
        return Response({
            'questions': QuizQuestionSerializer(questions, many=True).data,
        })

    @extend_schema(
        summary='Assignment config',
        description='GET: Return assignment config. 404 if not assignment session. '
                    'POST: Create config. PUT: Replace config. PATCH: Partial update.',
        request=AssignmentCreateUpdateSerializer,
        responses={
            200: AssignmentSerializer,
            201: AssignmentSerializer,
            400: OpenApiResponse(description='Validation error or Assignment already exists'),
            404: OpenApiResponse(description='Session not assignment type'),
        },
    )
    @action(detail=True, methods=['get', 'post', 'put', 'patch'], url_path='assignment')
    def assignment(self, request, pk=None):
        session = self.get_object()
        if session.session_type != Session.SessionType.ASSIGNMENT:
            return Response(
                {'detail': 'Session is not an assignment session.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == 'GET':
            assignment = self._get_assignment(session)
            if assignment is None:
                return Response(
                    {'detail': 'Assignment config not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(AssignmentSerializer(assignment).data)

        if request.method == 'POST':
            if hasattr(session, 'assignment'):
                return Response(
                    {'detail': 'Assignment already exists for this session.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer = AssignmentCreateUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            assignment = Assignment.objects.create(session=session, **serializer.validated_data)
            return Response(AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

        # PUT / PATCH: create if missing, then update
        assignment = self._get_or_create_assignment(session)
        partial = request.method == 'PATCH'
        serializer = AssignmentCreateUpdateSerializer(assignment, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        return Response(AssignmentSerializer(assignment).data)


@extend_schema(
    tags=['Catalogue - Course Reviews'],
    description='Manage course reviews',
)
class CourseReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing course reviews.
    - GET: List reviews for a course
    - POST: Create a review (learners only, must be enrolled)
    - GET /{id}/: Get single review
    """
    queryset = CourseReview.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return CourseReviewCreateSerializer
        return CourseReviewSerializer

    def get_queryset(self):
        queryset = CourseReview.objects.filter(is_approved=True).select_related('course', 'user')
        
        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
            
        rating = self.request.query_params.get('rating')
        if rating:
            queryset = queryset.filter(rating=rating)
            
        return queryset

    @extend_schema(
        summary="Mark review as helpful",
        description="Increments the helpful count for a review.",
        responses={200: CourseReviewSerializer}
    )
    @action(detail=True, methods=['post'])
    def helpful(self, request, pk=None):
        review = self.get_object()
        from django.db.models import F
        CourseReview.objects.filter(pk=review.pk).update(helpful_count=F('helpful_count') + 1)
        review.refresh_from_db()
        return Response(CourseReviewSerializer(review).data)

    @extend_schema(
        summary="Report a review",
        description="Increments the report count for a review.",
        responses={200: CourseReviewSerializer}
    )
    @action(detail=True, methods=['post'])
    def report(self, request, pk=None):
        review = self.get_object()
        from django.db.models import F
        CourseReview.objects.filter(pk=review.pk).update(report_count=F('report_count') + 1)
        review.refresh_from_db()
        return Response(CourseReviewSerializer(review).data)


    def create(self, request, *args, **kwargs):
        course_id = request.data.get('course')
        if not course_id:
            return Response(
                {'course': 'This field is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {'course': 'Course not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()
        if not enrollment:
            return Response(
                {'error': 'You must be enrolled to review this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        existing = CourseReview.objects.filter(course=course, user=request.user).first()
        if existing:
            return Response(
                {'error': 'You have already reviewed this course.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        review = CourseReview.objects.create(
            course=course,
            user=request.user,
            rating=request.data.get('rating'),
            content=request.data.get('content', '')
        )

        return Response(
            CourseReviewSerializer(review).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary='Get course review summary',
        description='Returns review summary with average rating and distribution',
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        course_id = request.query_params.get('course')
        if not course_id:
            return Response(
                {'course': 'This field is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {'course': 'Course not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        reviews = CourseReview.objects.filter(course=course, is_approved=True)
        total = reviews.count()
        
        if total == 0:
            return Response({
                'average': 0,
                'total': 0,
                'distribution': [0, 0, 0, 0, 0],
                'reviews': []
            })

        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        
        distribution = [
            reviews.filter(rating=5).count(),
            reviews.filter(rating=4).count(),
            reviews.filter(rating=3).count(),
            reviews.filter(rating=2).count(),
            reviews.filter(rating=1).count(),
        ]

        reviews_list = reviews.order_by('-created_at')[:20]
        
        return Response({
            'average': round(avg_rating, 1),
            'total': total,
            'distribution': distribution,
            'reviews': CourseReviewSerializer(reviews_list, many=True).data
        })


from django.db.models import Avg, Count, Q

@extend_schema(tags=['Catalogue - Analytics'])
class CatalogueAnalyticsViewSet(viewsets.ViewSet):
    """ViewSet for dashboard analytics regarding catalogue."""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='courses-by-category')
    def courses_by_category(self, request):
        user = request.user
        
        course_filter = Q(courses__status='published')
        
        if user.role == 'lms_manager' and hasattr(user, 'organization') and user.organization:
            course_filter &= Q(courses__organization=user.organization)
        elif user.role == 'instructor':
            course_filter &= Q(courses__instructor=user)
            # Instructors might want to see drafts too in their analytics
            course_filter = Q(courses__instructor=user) & ~Q(courses__status='archived')

        categories = Category.objects.annotate(
            course_count=Count('courses', filter=course_filter)
        ).filter(course_count__gt=0).order_by('-course_count')[:10]

        data = [
            {"name": c.name, "count": c.course_count}
            for c in categories
        ]

        return Response(data)


@extend_schema(tags=['Catalogue - Attachments'])
class SessionAttachmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing session attachments (resources)."""
    serializer_class = SessionAttachmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = SessionAttachment.objects.all().select_related('uploaded_by')
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs

    def perform_create(self, serializer):
        from rest_framework.exceptions import PermissionDenied
        session = serializer.validated_data['session']
        course = session.module.course
        user = self.request.user
        
        is_owner = course.instructor == user
        from apps.accounts.rbac import is_admin_like, is_lms_manager
        if not (is_owner or is_admin_like(user) or is_lms_manager(user)):
             raise PermissionDenied("You do not have permission to add attachments to this course.")

        file_obj = self.request.FILES.get('file')
        file_size = file_obj.size if file_obj else 0
        file_name = file_obj.name.lower() if file_obj else ''
        file_type = file_name.split('.')[-1] if '.' in file_name else 'unknown'

        serializer.save(
            uploaded_by=user,
            file_size=file_size,
            file_type=file_type
        )

    def perform_destroy(self, instance):
        from rest_framework.exceptions import PermissionDenied
        course = instance.session.module.course
        user = self.request.user
        is_owner = course.instructor == user
        from apps.accounts.rbac import is_admin_like, is_lms_manager
        if not (is_owner or is_admin_like(user) or is_lms_manager(user)):
             raise PermissionDenied("You do not have permission to delete this attachment.")
        instance.delete()
