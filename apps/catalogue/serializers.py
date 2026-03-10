from rest_framework import serializers
from django.utils.text import slugify

from .models import BankQuestion, Category, Course, Module, Quiz, QuizQuestion, QuestionCategory, Session, Tag
from .utils.video_embed import validate_external_video_url


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


class ModuleSerializer(serializers.ModelSerializer):
    """Serializer for Module model."""

    class Meta:
        model = Module
        fields = [
            'id', 'course', 'title', 'description', 'status', 'icon',
            'order', 'require_sequential', 'allow_preview',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SessionSerializer(serializers.ModelSerializer):
    """Serializer for Session model."""
    duration_minutes = serializers.ReadOnlyField()

    class Meta:
        model = Session
        fields = [
            'id', 'course', 'module', 'title', 'description', 'session_type', 'status',
            'order', 'video_duration_seconds', 'duration_minutes',
            'content_source',
            'video_url', 'content_text',
            'external_video_url', 'external_video_provider', 'external_video_embed_url',
            'asset_object_key', 'asset_bucket', 'asset_mime_type',
            'asset_size_bytes', 'asset_original_filename',
            'is_free_preview', 'is_mandatory',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SessionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating sessions."""

    class Meta:
        model = Session
        fields = [
            'course', 'module', 'title', 'description', 'session_type', 'status',
            'order', 'video_duration_seconds',
            'content_source',
            'video_url', 'content_text',
            'external_video_url', 'external_video_provider', 'external_video_embed_url',
            'asset_object_key', 'asset_bucket', 'asset_mime_type',
            'asset_size_bytes', 'asset_original_filename',
            'is_free_preview', 'is_mandatory'
        ]

    def validate(self, attrs):
        instance = self.instance

        # Resolve effective values (incoming or existing)
        def _get(key, default=None):
            if key in attrs:
                return attrs[key]
            if instance is not None:
                return getattr(instance, key, default)
            return default

        incoming_source = attrs.get(
            'content_source', instance.content_source if instance else None
        )
        incoming_type = attrs.get(
            'session_type', instance.session_type if instance else None
        )

        # Legacy: treat video_url as external_video_url when external_video_url absent
        ext_url_from_attrs = attrs.get('external_video_url') or attrs.get('video_url')
        ext_url_from_instance = (
            (instance.external_video_url or instance.video_url) if instance else None
        )
        effective_external_url = ext_url_from_attrs or ext_url_from_instance

        # Infer content_source when not provided
        if incoming_source is None or incoming_source == '':
            if instance is None:
                # Create: infer from attrs
                if attrs.get('asset_object_key'):
                    attrs['content_source'] = Session.ContentSource.UPLOAD
                    incoming_source = Session.ContentSource.UPLOAD
                elif attrs.get('external_video_url') or attrs.get('video_url'):
                    attrs['content_source'] = Session.ContentSource.EXTERNAL
                    incoming_source = Session.ContentSource.EXTERNAL
                else:
                    attrs['content_source'] = Session.ContentSource.INLINE
                    incoming_source = Session.ContentSource.INLINE
            else:
                # Update: leave content_source unchanged
                incoming_source = instance.content_source

        # Normalize to string for comparison
        src = (incoming_source or '').strip() or None
        typ = (incoming_type or '').strip() or None

        if src == Session.ContentSource.EXTERNAL:
            if typ != 'video':
                raise serializers.ValidationError({
                    'session_type': 'External video is only supported for video sessions.',
                })
            if not effective_external_url or not str(effective_external_url).strip():
                raise serializers.ValidationError({
                    'external_video_url': 'external_video_url is required when content_source is external.',
                })
            try:
                provider, embed_url = validate_external_video_url(str(effective_external_url))
                attrs['external_video_provider'] = provider
                attrs['external_video_embed_url'] = embed_url
                attrs['external_video_url'] = str(effective_external_url).strip()
            except ValueError as e:
                raise serializers.ValidationError({'external_video_url': str(e)})

            attrs['asset_object_key'] = None
            attrs['asset_bucket'] = None
            attrs['asset_mime_type'] = None
            attrs['asset_size_bytes'] = None
            attrs['asset_original_filename'] = None

        elif src == Session.ContentSource.UPLOAD:
            asset_key = attrs.get('asset_object_key') or _get('asset_object_key')
            if not asset_key or not str(asset_key).strip():
                raise serializers.ValidationError({
                    'asset_object_key': 'asset_object_key is required when content_source is upload.',
                })

            attrs['external_video_url'] = None
            attrs['external_video_provider'] = None
            attrs['external_video_embed_url'] = None

        elif src == Session.ContentSource.INLINE:
            attrs['asset_object_key'] = None
            attrs['asset_bucket'] = None
            attrs['asset_mime_type'] = None
            attrs['asset_size_bytes'] = None
            attrs['asset_original_filename'] = None
            attrs['external_video_url'] = None
            attrs['external_video_provider'] = None
            attrs['external_video_embed_url'] = None

        # Validate module belongs to the same course as session
        course = attrs.get('course') or (instance.course if instance else None)
        module = attrs.get('module') or (instance.module if instance else None)
        if course is not None and module is not None:
            course_id = course.id if hasattr(course, 'id') else course
            if module.course_id != course_id:
                raise serializers.ValidationError({
                    'module': 'Module must belong to the same course as the session.',
                })

        return attrs


# ========================================
# Quiz Authoring Serializers (session-scoped quiz API only)
# ========================================

QUIZ_QUESTION_TYPES = ['multiple-choice', 'true-false', 'short-answer', 'essay', 'matching', 'fill-blank']


class QuizQuestionSerializer(serializers.ModelSerializer):
    """Serializer for QuizQuestion in quiz detail and write payloads."""
    class Meta:
        model = QuizQuestion
        fields = ['id', 'order', 'question_type', 'question_text', 'points', 'answer_payload']
        read_only_fields = ['id']

    def validate_question_type(self, value):
        if value not in QUIZ_QUESTION_TYPES:
            raise serializers.ValidationError(
                f'Invalid question_type. Must be one of: {", ".join(QUIZ_QUESTION_TYPES)}'
            )
        return value

    def validate_question_text(self, value):
        if not (value and str(value).strip()):
            raise serializers.ValidationError('question_text is required.')
        return value

    def validate_points(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('points must be >= 0.')
        return value

    def validate_answer_payload(self, value):
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError('answer_payload must be a JSON object.')
        return value or {}


class QuizSettingsUpdateSerializer(serializers.Serializer):
    """Accepts partial settings dict for PATCH."""
    settings = serializers.JSONField(required=True)

    def validate_settings(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('settings must be a JSON object.')
        return value


class QuizSessionSummarySerializer(serializers.Serializer):
    """Minimal session info for quiz detail response."""
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)


class QuizDetailSerializer(serializers.Serializer):
    """Response shape for GET/PATCH /sessions/{id}/quiz/."""
    session = QuizSessionSummarySerializer(read_only=True)
    settings = serializers.JSONField(read_only=True)
    questions = QuizQuestionSerializer(many=True, read_only=True)


class QuizQuestionListWriteSerializer(serializers.Serializer):
    """Input shape for PUT /sessions/{id}/quiz/questions/."""
    questions = serializers.ListField(
        child=serializers.DictField(),
        required=True,
    )

    def validate_questions(self, value):
        for i, q in enumerate(value):
            if not isinstance(q, dict):
                raise serializers.ValidationError(
                    f'questions[{i}]: each item must be a JSON object.'
                )
            qt = q.get('question_type')
            if qt and qt not in QUIZ_QUESTION_TYPES:
                raise serializers.ValidationError(
                    f'questions[{i}]: invalid question_type "{qt}". '
                    f'Must be one of: {", ".join(QUIZ_QUESTION_TYPES)}'
                )
            if not (q.get('question_text') or str(q.get('question_text', '')).strip()):
                raise serializers.ValidationError(
                    f'questions[{i}]: question_text is required.'
                )
            pts = q.get('points')
            if pts is not None and (not isinstance(pts, (int, float)) or pts < 0):
                raise serializers.ValidationError(
                    f'questions[{i}]: points must be >= 0.'
                )
            ap = q.get('answer_payload')
            if ap is not None and not isinstance(ap, dict):
                raise serializers.ValidationError(
                    f'questions[{i}]: answer_payload must be a JSON object.'
                )
        return value


# ========================================
# Question Bank Serializers
# ========================================

class AddFromBankSerializer(serializers.Serializer):
    """Input shape for POST /sessions/{id}/quiz/questions/add-from-bank/."""
    bank_question_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class QuestionCategorySerializer(serializers.ModelSerializer):
    """Serializer for QuestionCategory list/create/update."""
    class Meta:
        model = QuestionCategory
        fields = ['id', 'name', 'order']
        read_only_fields = ['id']


class BankQuestionSerializer(serializers.ModelSerializer):
    """Serializer for BankQuestion retrieve/create/update."""
    class Meta:
        model = BankQuestion
        fields = [
            'id', 'category', 'question_type', 'question_text', 'points',
            'answer_payload', 'difficulty', 'tags', 'explanation',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_question_type(self, value):
        if value not in QUIZ_QUESTION_TYPES:
            raise serializers.ValidationError(
                f'Invalid question_type. Must be one of: {", ".join(QUIZ_QUESTION_TYPES)}'
            )
        return value

    def validate_question_text(self, value):
        if not (value and str(value).strip()):
            raise serializers.ValidationError('question_text is required.')
        return value

    def validate_points(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('points must be >= 0.')
        return value

    def validate_answer_payload(self, value):
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError('answer_payload must be a JSON object.')
        return value or {}

    def validate_tags(self, value):
        if value is not None and not isinstance(value, list):
            raise serializers.ValidationError('tags must be a list.')
        return value or []


class BankQuestionListSerializer(serializers.ModelSerializer):
    """Optimized serializer for BankQuestion list view."""
    category = serializers.SerializerMethodField()

    class Meta:
        model = BankQuestion
        fields = [
            'id', 'question_type', 'question_text', 'points', 'difficulty',
            'tags', 'category', 'created_at',
        ]

    def get_category(self, obj):
        if obj.category_id is None:
            return None
        return {'id': obj.category.id, 'name': obj.category.name}


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
            'featured', 'status', 'published_at', 'access_duration', 'allow_self_enrollment'
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
            'description', 'prerequisites', 'learning_objectives', 'learning_objectives_list',
            'target_audience', 'trailer_video_url',
            'banner', 'subcategory',
            'duration_minutes',
            'is_public', 'allow_self_enrollment', 'certificate_on_completion',
            'enable_discussions', 'sequential_learning',
            'enrollment_limit', 'access_duration', 'start_date', 'end_date',
            'grading_config',
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


def _count_objectives(attrs, instance):
    """
    Return the number of non-empty objectives from either source.

    Priority:
    1. learning_objectives_list in incoming attrs (if present and non-empty list)
    2. learning_objectives_list on the existing instance (for PATCH without list)
    3. learning_objectives string: split by newline, count non-empty lines
    """
    # Source 1: list in incoming payload
    if 'learning_objectives_list' in attrs:
        obj_list = attrs['learning_objectives_list']
        if obj_list:
            return len([o for o in obj_list if o and o.strip()])

    # Source 2: existing instance list (PATCH without new list)
    if instance is not None and instance.learning_objectives_list:
        return len([o for o in instance.learning_objectives_list if o and o.strip()])

    # Source 3: fall back to string field (either incoming or existing)
    obj_str = attrs.get('learning_objectives') or (instance.learning_objectives if instance else '')
    if obj_str:
        return len([line for line in obj_str.splitlines() if line.strip()])

    return 0


class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating courses."""
    slug = serializers.SlugField(required=False, allow_blank=True)
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False
    )
    learning_objectives_list = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
    )

    class Meta:
        model = Course
        fields = [
            'title', 'slug', 'subtitle', 'description', 'short_description',
            'subcategory',
            'category', 'level', 'tags',
            'price', 'currency', 'discount_percentage',
            'duration_hours', 'duration_minutes', 'duration_weeks', 'total_sessions',
            'instructor',
            'thumbnail', 'banner', 'trailer_video_url',
            'prerequisites', 'learning_objectives', 'learning_objectives_list',
            'target_audience',
            'status', 'featured', 'access_duration', 'allow_self_enrollment',
            'is_public', 'certificate_on_completion', 'enable_discussions',
            'sequential_learning', 'enrollment_limit', 'start_date', 'end_date',
            'grading_config',
            'meta_title', 'meta_description', 'meta_keywords'
        ]

    def validate(self, attrs):
        if self.instance is not None:
            # UPDATE / PATCH: only run publish checks when status is explicitly
            # set to 'published' in this request. If status is absent, the
            # course status is not changing, so skip validation entirely —
            # this prevents blocking PATCH on legacy published courses that
            # were created before thumbnail/objectives were required.
            if 'status' not in attrs:
                return attrs
            effective_status = attrs['status']
        else:
            # CREATE: default to draft when status is omitted.
            effective_status = attrs.get('status', Course.Status.DRAFT)

        if effective_status == Course.Status.PUBLISHED:
            # Thumbnail check
            thumbnail = attrs.get('thumbnail') or (self.instance.thumbnail if self.instance else None)
            if not thumbnail or not str(thumbnail).strip():
                raise serializers.ValidationError(
                    {'thumbnail': 'A thumbnail URL is required before publishing.'}
                )

            # Objectives check — accept either source
            count = _count_objectives(attrs, self.instance)
            if count < 4:
                raise serializers.ValidationError({
                    'learning_objectives_list': (
                        'At least 4 non-empty learning objectives are required to publish. '
                        f'Found {count}. Provide them via learning_objectives_list (array) '
                        'or learning_objectives (newline-separated string).'
                    )
                })

        return attrs

    def _unique_slug(self, base):
        if not base:
            base = 'course'
        slug = base
        n = 2
        qs = Course.objects.filter(slug=slug)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        while qs.exists():
            slug = f'{base}-{n}'
            n += 1
            qs = Course.objects.filter(slug=slug)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
        return slug

    def _sync_objectives(self, validated_data):
        """If learning_objectives_list is provided, sync learning_objectives string."""
        objectives_list = validated_data.get('learning_objectives_list')
        if objectives_list is not None:
            validated_data['learning_objectives'] = '\n'.join(
                o for o in objectives_list if o and o.strip()
            )

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', [])
        self._sync_objectives(validated_data)
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
        self._sync_objectives(validated_data)
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
            'description', 'prerequisites', 'learning_objectives', 'learning_objectives_list',
            'target_audience', 'trailer_video_url',
            'banner', 'subcategory',
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
