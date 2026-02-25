# apps/catalogue/views_public.py
"""
Public (unauthenticated) read-only views for course catalogue.
These endpoints are accessible without authentication for public browsing.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema, OpenApiParameter, OpenApiExample
from rest_framework import viewsets, filters
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.db import transaction
from drf_spectacular.types import OpenApiTypes

from .models import Category, Course, Tag
from .serializers import (
    CategorySerializer,
    CategoryDetailSerializer,
    CategoryCreateUpdateSerializer,
    CategoryTreeSerializer,
    CategoryBulkActionSerializer,
    TagSerializer,
    CourseListSerializer,
    PublicCourseDetailSerializer,
)
from .permissions import IsLMSManager


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

@extend_schema(tags=['Categories - Management'])
class CategoryManagementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for LMS Managers to manage categories.
    
    Provides full CRUD operations for categories.
    Requires LMS Manager or Admin permissions.
    """
    
    queryset = Category.objects.all()
    permission_classes = [IsAuthenticated, IsLMSManager]
    
    def get_serializer_class(self):
        """Return different serializers for different actions"""
        if self.action in ['create', 'update', 'partial_update']:
            return CategoryCreateUpdateSerializer
        elif self.action == 'retrieve':
            return CategoryDetailSerializer
        elif self.action == 'tree':
            return CategoryTreeSerializer
        return CategorySerializer
    
    def get_queryset(self):
        """
        Get all categories (including inactive) for managers.
        Supports filtering.
        """
        queryset = Category.objects.all()
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active_bool)
        
        # Filter by parent
        parent = self.request.query_params.get('parent')
        if parent == 'null' or parent == 'none':
            queryset = queryset.filter(parent__isnull=True)
        elif parent:
            queryset = queryset.filter(parent_id=parent)
        
        # Search by name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Ordering
        ordering = self.request.query_params.get('ordering', 'name')
        queryset = queryset.order_by(ordering)
        
        return queryset
    
    @extend_schema(
        summary='List all categories',
        description='Get all categories (including inactive) with filtering options',
        parameters=[
            OpenApiParameter(name='is_active', type=bool, description='Filter by active status'),
            OpenApiParameter(name='parent', type=str, description='Filter by parent ID (use "null" for root)'),
            OpenApiParameter(name='search', type=str, description='Search by name'),
            OpenApiParameter(name='ordering', type=str, description='Order by field (e.g., "name" or "-name")'),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary='Create category',
        description='Create a new category (LMS Manager only)',
        request=CategoryCreateUpdateSerializer,
        responses={201: CategorySerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new category"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return Response(
            CategorySerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED
        )
    
    @extend_schema(
        summary='Get category details',
        description='Get detailed category information including child categories'
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        summary='Update category',
        description='Update an existing category (LMS Manager only)',
        request=CategoryCreateUpdateSerializer,
        responses={200: CategorySerializer}
    )
    def update(self, request, *args, **kwargs):
        """Update a category"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response(CategorySerializer(serializer.instance).data)
    
    @extend_schema(
        summary='Delete category',
        description='Delete a category (LMS Manager only)',
        responses={
            204: OpenApiResponse(description='Category deleted'),
            400: OpenApiResponse(description='Category has child categories')
        }
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a category"""
        instance = self.get_object()
        
        # Check if category has children
        if instance.children.exists():
            return Response(
                {'error': 'Cannot delete category with child categories. Move or delete children first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @extend_schema(
        summary='Get category tree',
        description='Get hierarchical tree of all categories'
    )
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Get hierarchical category tree"""
        # Get root categories (no parent)
        root_categories = Category.objects.filter(parent__isnull=True)
        
        # Optionally filter by active status
        show_all = request.query_params.get('all', 'false').lower() == 'true'
        if not show_all:
            root_categories = root_categories.filter(is_active=True)
        
        serializer = CategoryTreeSerializer(root_categories, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Bulk operations',
        description='Perform bulk operations on multiple categories',
        request=CategoryBulkActionSerializer,
        responses={200: OpenApiResponse(description='Bulk operation completed')}
    )
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def bulk(self, request):
        """Perform bulk operations on categories"""
        serializer = CategoryBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        action = data['action']
        category_ids = data['category_ids']
        
        categories = Category.objects.filter(id__in=category_ids)
        
        if action == 'activate':
            categories.update(is_active=True)
            message = f"Activated {categories.count()} categories"
            
        elif action == 'deactivate':
            categories.update(is_active=False)
            message = f"Deactivated {categories.count()} categories"
            
        elif action == 'delete':
            # Check if any categories have children
            has_children = any(cat.children.exists() for cat in categories)
            if has_children:
                return Response(
                    {'error': 'Cannot delete categories that have child categories'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            categories.delete()
            message = f"Deleted {len(category_ids)} categories"
            
        elif action == 'move':
            target_parent_id = data.get('target_parent_id')
            if target_parent_id:
                from django.shortcuts import get_object_or_404
                target_parent = get_object_or_404(Category, id=target_parent_id)
                categories.update(parent=target_parent)
            else:
                categories.update(parent=None)
            message = f"Moved {categories.count()} categories"
        
        return Response({
            'success': True,
            'message': message,
            'affected_categories': list(categories.values_list('id', flat=True))
        })
    
    @extend_schema(
        summary='Get category stats',
        description='Get statistics about categories'
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get category statistics"""
        total = Category.objects.count()
        active = Category.objects.filter(is_active=True).count()
        inactive = total - active
        root = Category.objects.filter(parent__isnull=True).count()
        
        return Response({
            'total_categories': total,
            'active_categories': active,
            'inactive_categories': inactive,
            'root_categories': root,
            'categories_with_children': Category.objects.filter(children__isnull=False).distinct().count()
        })

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
