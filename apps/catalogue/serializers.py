from rest_framework import serializers
from django.utils.text import slugify

from .models import (
    Category, Course, Session, Tag
)


class TagSerializer(serializers.ModelSerializer):
    """Serializer for Tag model."""
    
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Category model."""
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'icon',
            'parent', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CategoryDetailSerializer(CategorySerializer):
    """Detailed serializer for Category with children."""
    children = CategorySerializer(many=True, read_only=True)
    
    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ['children']


class SessionSerializer(serializers.ModelSerializer):
    """Serializer for Session model."""
    duration_minutes = serializers.ReadOnlyField()
    
    class Meta:
        model = Session
        fields = [
            'id', 'course', 'title', 'description', 'session_type', 'status',
            'order', 'video_duration_seconds', 'duration_minutes',
            'video_url', 'content_text',
            'is_free_preview', 'is_mandatory',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SessionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating sessions."""
    
    class Meta:
        model = Session
        fields = [
            'course', 'title', 'description', 'session_type', 'status',
            'order', 'video_duration_seconds',
            'video_url', 'content_text', 'is_free_preview', 'is_mandatory'
        ]


class CourseListSerializer(serializers.ModelSerializer):
    """Serializer for Course list view (minimal data)."""
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    instructor_name = serializers.SerializerMethodField()
    discounted_price = serializers.ReadOnlyField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'subtitle', 'short_description',
            'thumbnail', 'category', 'tags',
            'level',
            'price', 'discounted_price', 'discount_percentage',
            'duration_hours', 'duration_weeks', 'total_sessions',
            'instructor', 'instructor_name',
            'enrollment_count',
            'featured', 'status', 'published_at'
        ]
        read_only_fields = ['id', 'enrollment_count']
    
    def get_instructor_name(self, obj):
        return obj.instructor.get_full_name() or obj.instructor.email if obj.instructor else None


class CourseDetailSerializer(CourseListSerializer):
    """Serializer for Course detail view (full data)."""
    sessions = SessionSerializer(many=True, read_only=True)
    instructor = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    
    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + [
            'description', 'prerequisites', 'learning_objectives',
            'target_audience', 'trailer_video_url',
            'meta_title', 'meta_description', 'meta_keywords',
            'created_by', 'sessions',
            'created_at', 'updated_at'
        ]
        read_only_fields = CourseListSerializer.Meta.read_only_fields + ['created_at', 'updated_at']
    
    def get_instructor(self, obj):
        if obj.instructor:
            return {
                'id': obj.instructor.id,
                'name': obj.instructor.get_full_name() or obj.instructor.email,
                'email': obj.instructor.email,
                'avatar': obj.instructor.avatar
            }
        return None
    
    def get_created_by(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'name': obj.created_by.get_full_name() or obj.created_by.email,
                'email': obj.created_by.email
            }
        return None


class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating courses."""
    slug = serializers.SlugField(required=False, allow_blank=True)
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False
    )

    class Meta:
        model = Course
        fields = [
            'title', 'slug', 'subtitle', 'description', 'short_description',
            'category', 'level', 'tags',
            'price', 'currency', 'discount_percentage',
            'duration_hours', 'duration_weeks', 'total_sessions',
            'instructor',
            'thumbnail', 'trailer_video_url',
            'prerequisites', 'learning_objectives', 'target_audience',
            'status', 'featured',
            'meta_title', 'meta_description', 'meta_keywords'
        ]

    def _unique_slug(self, base):
        if not base:
            base = 'course'
        slug = base
        n = 2
        while Course.objects.filter(slug=slug).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', [])
        slug = validated_data.get('slug') or ''
        if not slug.strip():
            slug = self._unique_slug(slugify(validated_data.get('title', '') or 'course'))
        else:
            slug = self._unique_slug(slugify(slug))
        validated_data['slug'] = slug
        course = Course.objects.create(**validated_data)
        if tags_data:
            course.tags.set(tags_data)
        return course
    
    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        if 'slug' in validated_data and not (validated_data.get('slug') or '').strip():
            validated_data.pop('slug')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tags_data is not None:
            instance.tags.set(tags_data)
        return instance


class CourseCreateSerializer(CourseCreateUpdateSerializer):
    """Alias for course creation serializer."""
    pass


# ========================================
# Public Serializers (for unauthenticated access)
# ========================================

class PublicSessionSerializer(serializers.ModelSerializer):
    """
    Public serializer for Session - excludes video_url and content_text.
    Unauthenticated users can see session structure but not access content.
    """
    duration_minutes = serializers.ReadOnlyField()
    
    class Meta:
        model = Session
        fields = [
            'id', 'title', 'description', 'session_type',
            'order', 'video_duration_seconds', 'duration_minutes',
            'is_free_preview', 'is_mandatory',
        ]
        read_only_fields = fields


class PublicCourseDetailSerializer(CourseListSerializer):
    """
    Public serializer for Course detail view.
    Includes session list but uses PublicSessionSerializer to hide content URLs.
    """
    sessions = PublicSessionSerializer(many=True, read_only=True)
    instructor = serializers.SerializerMethodField()
    
    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + [
            'description', 'prerequisites', 'learning_objectives',
            'target_audience', 'trailer_video_url',
            'sessions',
            'created_at', 'updated_at'
        ]
        read_only_fields = CourseListSerializer.Meta.read_only_fields + ['created_at', 'updated_at']
    
    def get_instructor(self, obj):
        """Return basic instructor info without sensitive data."""
        if obj.instructor:
            return {
                'id': obj.instructor.id,
                'name': obj.instructor.get_full_name() or obj.instructor.email,
                'avatar': obj.instructor.avatar
            }
        return None