import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Category(models.Model):
    """
    Category represents a classification for courses.
    """
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    icon = models.URLField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name


class Course(models.Model):
    """
    Course represents a full learning course with multiple sessions.
    """
    class Level(models.TextChoices):
        BEGINNER = 'beginner', 'Beginner'
        INTERMEDIATE = 'intermediate', 'Intermediate'
        ADVANCED = 'advanced', 'Advanced'
        ALL_LEVELS = 'all_levels', 'All Levels'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    # Basic Information
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    subtitle = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    short_description = models.CharField(max_length=500, blank=True)
    subcategory = models.CharField(max_length=255, blank=True, help_text="Sub-classification within the category")

    # Classification
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='courses')
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.ALL_LEVELS)
    tags = models.ManyToManyField('Tag', blank=True, related_name='courses')

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    discount_percentage = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Duration and Effort
    duration_hours = models.PositiveIntegerField(default=0, help_text="Total duration in hours")
    duration_minutes = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Remaining minutes within the hour (0–59)"
    )
    duration_weeks = models.PositiveIntegerField(default=0, help_text="Recommended weeks to complete")
    total_sessions = models.PositiveIntegerField(default=0)

    # Instructor and Creator
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='instructed_courses'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_courses'
    )

    # Media
    thumbnail = models.URLField(blank=True, null=True)
    banner = models.URLField(blank=True, null=True, help_text="Wide banner image for the course detail page")
    trailer_video_url = models.URLField(blank=True, null=True)

    # Requirements and Objectives
    prerequisites = models.TextField(blank=True, help_text="What learners should know before starting")
    learning_objectives = models.TextField(blank=True, help_text="What learners will achieve")
    target_audience = models.TextField(blank=True, help_text="Who this course is for")

    # Settings
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    featured = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    # Course behaviour settings
    is_public = models.BooleanField(default=False)
    allow_self_enrollment = models.BooleanField(default=True)
    certificate_on_completion = models.BooleanField(default=False)
    enable_discussions = models.BooleanField(default=False)
    sequential_learning = models.BooleanField(default=False)
    enrollment_limit = models.PositiveIntegerField(null=True, blank=True)
    access_duration = models.CharField(max_length=20, blank=True, default='lifetime')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # Grading & Objectives (structured)
    grading_config = models.JSONField(default=dict, blank=True)
    learning_objectives_list = models.JSONField(
        default=list, blank=True,
        help_text="Structured list of learning objective strings; mirrors learning_objectives as newline-joined text"
    )

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['status']),
            models.Index(fields=['featured']),
            models.Index(fields=['level']),
        ]

    def __str__(self):
        return self.title

    @property
    def discounted_price(self):
        if self.discount_percentage > 0:
            return self.price * (1 - self.discount_percentage / 100)
        return self.price

    @property
    def enrollment_count(self):
        return self.enrollments.count()


class Session(models.Model):
    """
    Session represents an individual learning session within a course.
    """
    class SessionType(models.TextChoices):
        VIDEO      = 'video',      'Video'
        TEXT       = 'text',       'Text'
        LIVE       = 'live',       'Live Session'
        DOCUMENT   = 'document',   'Document'
        HTML       = 'html',       'HTML / Rich Text'
        QUIZ       = 'quiz',       'Quiz'
        ASSIGNMENT = 'assignment', 'Assignment'
        SCORM      = 'scorm',      'SCORM Package'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')

    # Basic Information
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    session_type = models.CharField(max_length=20, choices=SessionType.choices, default=SessionType.VIDEO)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Order and Duration
    order = models.PositiveIntegerField(default=0)
    video_duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    # Content
    video_url = models.URLField(blank=True, null=True)
    content_text = models.TextField(blank=True)

    # Settings
    is_free_preview = models.BooleanField(default=False)
    is_mandatory = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        unique_together = ('course', 'order')
        indexes = [
            models.Index(fields=['course', 'order']),
        ]

    def __str__(self):
        return f"{self.order}. {self.title} ({self.course.title})"

    @property
    def duration_minutes(self):
        if self.video_duration_seconds:
            return self.video_duration_seconds // 60
        return 0


class Tag(models.Model):
    """
    Tag represents keywords for categorizing courses.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
