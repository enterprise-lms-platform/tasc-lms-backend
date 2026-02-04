from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import (
    Category, Course, Session, Tag
)
from .serializers import (
    TagSerializer, CategorySerializer, CategoryDetailSerializer,
    SessionSerializer, SessionCreateSerializer,
    CourseListSerializer, CourseDetailSerializer, CourseCreateSerializer
)


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
    permission_classes = [IsAuthenticated]
    
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
        is_published = self.request.query_params.get('is_published', None)
        
        if category:
            queryset = queryset.filter(category_id=category)
        if instructor:
            queryset = queryset.filter(instructor_id=instructor)
        if tag:
            queryset = queryset.filter(tags__name=tag)
        if is_published is not None:
            queryset = queryset.filter(is_published=is_published.lower() == 'true')
        
        return queryset.distinct()
    
    @extend_schema(
        summary='List courses',
        description='Returns paginated list of courses with filtering options',
        parameters=[
            OpenApiParameter(name='category', type=int, description='Filter by category ID'),
            OpenApiParameter(name='instructor', type=int, description='Filter by instructor ID'),
            OpenApiParameter(name='tag', type=str, description='Filter by tag name'),
            OpenApiParameter(name='is_published', type=bool, description='Filter by published status'),
        ],
        responses={200: CourseListSerializer},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Create course',
        description='Create a new course. Requires instructor or admin permissions.',
        request=CourseCreateSerializer,
        responses={201: CourseDetailSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get course details',
        description='Returns detailed information about a course including sessions',
        responses={200: CourseDetailSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        summary='Update course',
        description='Update course information. Only instructor or admin can update.',
        request=CourseCreateSerializer,
        responses={200: CourseDetailSerializer},
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @extend_schema(
        summary='Delete course',
        description='Delete a course. Only instructor or admin can delete.',
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
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