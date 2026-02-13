# apps/catalogue/views_public.py
"""
Public (unauthenticated) read-only views for course catalogue.
These endpoints are accessible without authentication for public browsing.
"""

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework import viewsets, filters
from rest_framework.permissions import AllowAny

from .models import Category, Course, Tag
from .serializers import (
    CategorySerializer,
    TagSerializer,
    CourseListSerializer,
    PublicCourseDetailSerializer,
)


@extend_schema(
    tags=['Public Catalogue - Courses'],
    description='Public read-only access to published courses',
)
class PublicCourseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public ViewSet for browsing published courses.
    
    - No authentication required
    - Returns only published courses
    - Lookup by slug for SEO-friendly URLs
    - Supports filtering by: featured, category, level
    """
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    
    def get_queryset(self):
        """Return only published courses with optional filtering."""
        queryset = Course.objects.filter(status='published').select_related(
            'category', 'instructor'
        ).prefetch_related('tags')
        
        # Filter by featured
        featured = self.request.query_params.get('featured', None)
        if featured is not None and featured.lower() == 'true':
            queryset = queryset.filter(featured=True)
        
        # Filter by category
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category_id=category)
        
        # Filter by level
        level = self.request.query_params.get('level', None)
        if level and level in ['beginner', 'intermediate', 'advanced', 'all_levels']:
            queryset = queryset.filter(level=level)
        
        return queryset.distinct()
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve, list serializer for list."""
        if self.action == 'retrieve':
            return PublicCourseDetailSerializer
        return CourseListSerializer
    
    @extend_schema(
        summary='List published courses',
        description='Returns paginated list of published courses. No authentication required.',
        parameters=[
            OpenApiParameter(
                name='featured',
                type=bool,
                description='Filter by featured courses (true/false)',
                required=False
            ),
            OpenApiParameter(
                name='category',
                type=int,
                description='Filter by category ID',
                required=False
            ),
            OpenApiParameter(
                name='level',
                type=str,
                description='Filter by level: beginner, intermediate, advanced, all_levels',
                required=False
            ),
        ],
        responses={200: CourseListSerializer(many=True)},
        examples=[
            OpenApiExample(
                'Success',
                value={
                    'count': 42,
                    'next': 'http://127.0.0.1:8000/api/v1/public/courses/?page=2',
                    'previous': None,
                    'results': [
                        {
                            'id': 1,
                            'title': 'Advanced React Patterns',
                            'slug': 'advanced-react-patterns',
                            'subtitle': 'Master advanced React patterns',
                            'short_description': 'Learn advanced React patterns...',
                            'thumbnail': 'https://example.com/thumb.jpg',
                            'category': {
                                'id': 1,
                                'name': 'Web Development',
                                'slug': 'web-development'
                            },
                            'tags': [{'id': 1, 'name': 'React', 'slug': 'react'}],
                            'level': 'advanced',
                            'price': '129.99',
                            'discounted_price': '129.99',
                            'discount_percentage': 0,
                            'duration_hours': 24,
                            'duration_weeks': 8,
                            'total_sessions': 48,
                            'instructor': 1,
                            'instructor_name': 'Michael Rodriguez',
                            'enrollment_count': 1234,
                            'featured': True,
                            'status': 'published',
                            'published_at': '2025-01-15T10:00:00Z'
                        }
                    ]
                },
                response_only=True,
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get course detail by slug',
        description='Returns detailed information about a published course including session structure (but not content URLs). No authentication required.',
        responses={
            200: PublicCourseDetailSerializer,
            404: {'description': 'Course not found or not published'}
        },
        examples=[
            OpenApiExample(
                'Success',
                value={
                    'id': 1,
                    'title': 'Advanced React Patterns',
                    'slug': 'advanced-react-patterns',
                    'description': 'Full course description...',
                    'prerequisites': 'Basic React knowledge...',
                    'learning_objectives': 'You will learn...',
                    'target_audience': 'Intermediate developers...',
                    'trailer_video_url': 'https://example.com/trailer.mp4',
                    'sessions': [
                        {
                            'id': 1,
                            'title': 'Introduction to Hooks',
                            'description': 'Learn React Hooks basics',
                            'session_type': 'video',
                            'order': 1,
                            'video_duration_seconds': 900,
                            'duration_minutes': 15,
                            'is_free_preview': True,
                            'is_mandatory': True
                        }
                    ],
                    'instructor': {
                        'id': 1,
                        'name': 'Michael Rodriguez',
                        'avatar': 'https://example.com/avatar.jpg'
                    },
                    'category': {'id': 1, 'name': 'Web Development', 'slug': 'web-development'},
                    'tags': [{'id': 1, 'name': 'React', 'slug': 'react'}],
                    'level': 'advanced',
                    'price': '129.99',
                    'featured': True,
                    'created_at': '2025-01-10T10:00:00Z',
                    'updated_at': '2025-01-15T10:00:00Z'
                },
                response_only=True,
            )
        ]
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


@extend_schema(
    tags=['Public Catalogue - Categories'],
    description='Public read-only access to active course categories',
)
class PublicCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public ViewSet for browsing active categories.
    
    - No authentication required
    - Returns only active categories
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary='List active categories',
        description='Returns list of all active course categories. No authentication required.',
        responses={200: CategorySerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get category detail',
        description='Returns detailed information about a category. No authentication required.',
        responses={200: CategorySerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


@extend_schema(
    tags=['Public Catalogue - Tags'],
    description='Public read-only access to course tags',
)
class PublicTagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public ViewSet for browsing course tags.
    
    - No authentication required
    - Returns all tags
    """
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary='List all tags',
        description='Returns list of all course tags. No authentication required.',
        responses={200: TagSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Get tag detail',
        description='Returns detailed information about a tag. No authentication required.',
        responses={200: TagSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
