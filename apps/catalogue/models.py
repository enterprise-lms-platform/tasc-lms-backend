import uuid
from decimal import Decimal, InvalidOperation
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
        PENDING_APPROVAL = 'pending_approval', 'Pending Approval'
        PUBLISHED = 'published', 'Published'
        REJECTED = 'rejected', 'Rejected'
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
    access_duration = models.CharField(max_length=50, default='lifetime', blank=True)
    allow_self_enrollment = models.BooleanField(default=True)

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
        price = self.price if self.price is not None else Decimal("0")
        try:
            discount = Decimal(str(self.discount_percentage or 0))
        except (InvalidOperation, TypeError, ValueError):
            discount = Decimal("0")

        if discount <= Decimal("0"):
            return price

        discount_factor = Decimal("1") - (discount / Decimal("100"))
        return price * discount_factor

    @property
    def enrollment_count(self):
        return self.enrollments.count()


class CourseApprovalRequest(models.Model):
    """
    Represents a request to publish or modify a course, reviewed by LMS Manager or TASC Admin.
    """
    class RequestType(models.TextChoices):
        CREATE = 'create', 'Create'
        EDIT = 'edit', 'Edit'
        DELETE = 'delete', 'Delete'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='approval_requests',
    )
    request_type = models.CharField(
        max_length=20,
        choices=RequestType.choices,
        default=RequestType.CREATE,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='course_approval_requests',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewer_comments = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_approval_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['course', 'status']),
        ]

    def __str__(self):
        return f"{self.get_request_type_display()} for {self.course.title} ({self.status})"


class Module(models.Model):
    """
    Module represents a grouping of sessions within a course.
    Sessions may optionally belong to a module; existing sessions can remain unassigned.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        HIDDEN = 'hidden', 'Hidden'

    class Icon(models.TextChoices):
        PLAY_CIRCLE = 'play-circle', 'Play Circle'
        LAYER_GROUP = 'layer-group', 'Layers'
        PUZZLE_PIECE = 'puzzle-piece', 'Puzzle'
        SHARE_ALT = 'share-alt', 'Share'
        TROPHY = 'trophy', 'Trophy'
        BOOK = 'book', 'Book'
        CODE = 'code', 'Code'

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    icon = models.CharField(max_length=50, choices=Icon.choices, default=Icon.PLAY_CIRCLE, blank=True)
    order = models.PositiveIntegerField(default=0)
    require_sequential = models.BooleanField(default=False)
    allow_preview = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['course', 'order'], name='catalogue_module_course_order_unique'),
        ]
        indexes = [
            models.Index(fields=['course', 'order']),
        ]

    def __str__(self):
        return f"{self.title} ({self.course.title})"


class Session(models.Model):
    """
    Session represents an individual learning session within a course.
    """
    class ContentSource(models.TextChoices):
        INLINE = 'inline', 'Inline'
        UPLOAD = 'upload', 'Uploaded Asset'
        EXTERNAL = 'external', 'External Video'

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
    module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions',
    )

    # Basic Information
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    session_type = models.CharField(max_length=20, choices=SessionType.choices, default=SessionType.VIDEO)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Order and Duration
    order = models.PositiveIntegerField(default=0)
    video_duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    # Content
    content_source = models.CharField(
        max_length=20, choices=ContentSource.choices, blank=True, null=True
    )
    video_url = models.URLField(blank=True, null=True)
    content_text = models.TextField(blank=True)

    # External video (YouTube, Vimeo, Loom)
    external_video_url = models.URLField(blank=True, null=True)
    external_video_provider = models.CharField(max_length=50, blank=True, null=True)
    external_video_embed_url = models.URLField(blank=True, null=True)

    # Uploaded asset metadata (videos, PDFs, SCORM zips)
    asset_object_key = models.CharField(max_length=512, blank=True, null=True)
    asset_bucket = models.CharField(max_length=128, blank=True, null=True)
    asset_mime_type = models.CharField(max_length=100, blank=True, null=True)
    asset_size_bytes = models.BigIntegerField(blank=True, null=True)
    asset_original_filename = models.CharField(max_length=255, blank=True, null=True)

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


# Shared question type choices for QuizQuestion and BankQuestion
QUESTION_TYPE_CHOICES = [
    ('multiple-choice', 'Multiple Choice'),
    ('true-false', 'True/False'),
    ('short-answer', 'Short Answer'),
    ('essay', 'Essay'),
    ('matching', 'Matching'),
    ('fill-blank', 'Fill in the Blank'),
]


class QuestionCategory(models.Model):
    """
    Instructor-owned category for organizing bank questions.
    """
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='question_categories',
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'name'],
                name='catalogue_questioncategory_owner_name_unique',
            ),
        ]

    def __str__(self):
        return f"{self.name} (owner={self.owner_id})"


class BankQuestion(models.Model):
    """
    Instructor-owned reusable question for the question bank.
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bank_questions',
    )
    category = models.ForeignKey(
        QuestionCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='questions',
    )
    question_type = models.CharField(max_length=32, choices=QUESTION_TYPE_CHOICES)
    question_text = models.TextField()
    points = models.PositiveIntegerField(default=10)
    answer_payload = models.JSONField(default=dict, blank=True)
    difficulty = models.CharField(max_length=16, blank=True, default='')
    tags = models.JSONField(default=list, blank=True)
    explanation = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"BankQ{self.id}: {self.question_text[:50]}..."


class Quiz(models.Model):
    """
    Quiz stores authoring data for a Session with session_type='quiz'.
    OneToOne with Session; created lazily on first quiz API access.
    """
    session = models.OneToOneField(
        Session,
        on_delete=models.CASCADE,
        related_name='quiz',
    )
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Quiz for {self.session.title}"


class Assignment(models.Model):
    """
    Assignment stores authoring data for a Session with session_type='assignment'.
    OneToOne with Session; created lazily on first PUT to .../assignment/.
    """
    class AssignmentType(models.TextChoices):
        PROJECT = 'project', 'Project'
        ESSAY = 'essay', 'Essay'
        CODE = 'code', 'Code Submission'
        PRESENTATION = 'presentation', 'Presentation'
        RESEARCH = 'research', 'Research'

    class PenaltyType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage per day'
        FIXED = 'fixed', 'Fixed percentage'
        NONE = 'none', 'No penalty'

    session = models.OneToOneField(
        Session,
        on_delete=models.CASCADE,
        related_name='assignment',
    )
    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
        default=AssignmentType.PROJECT,
    )
    instructions = models.TextField(blank=True, default='')
    max_points = models.PositiveIntegerField(default=100)
    due_date = models.DateTimeField(null=True, blank=True)
    available_from = models.DateTimeField(null=True, blank=True)
    allow_late = models.BooleanField(default=False)
    late_cutoff_date = models.DateTimeField(null=True, blank=True)
    penalty_type = models.CharField(
        max_length=20,
        choices=PenaltyType.choices,
        default=PenaltyType.NONE,
    )
    penalty_percent = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(null=True, blank=True)
    allowed_file_types = models.JSONField(default=list, blank=True)
    max_file_size_mb = models.PositiveIntegerField(null=True, blank=True)
    rubric_criteria = models.JSONField(default=list, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Assignment'
        verbose_name_plural = 'Assignments'

    def __str__(self):
        return f"Assignment for {self.session.title}"


class QuizQuestion(models.Model):
    """
    A single question within a Quiz. Type-specific data stored in answer_payload.
    """
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = 'multiple-choice', 'Multiple Choice'
        TRUE_FALSE = 'true-false', 'True/False'
        SHORT_ANSWER = 'short-answer', 'Short Answer'
        ESSAY = 'essay', 'Essay'
        MATCHING = 'matching', 'Matching'
        FILL_BLANK = 'fill-blank', 'Fill in the Blank'

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    order = models.PositiveIntegerField(default=0)
    question_type = models.CharField(max_length=32, choices=QuestionType.choices)
    question_text = models.TextField()
    points = models.PositiveIntegerField(default=10)
    answer_payload = models.JSONField(default=dict, blank=True)
    source_bank_question = models.ForeignKey(
        BankQuestion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='quiz_question_copies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."


class CourseReview(models.Model):
    """
    CourseReview represents a learner's review of a course.
    """
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='course_reviews'
    )
    rating = models.PositiveSmallIntegerField(
        choices=[
            (1, '1 Star'),
            (2, '2 Stars'),
            (3, '3 Stars'),
            (4, '4 Stars'),
            (5, '5 Stars'),
        ]
    )
    content = models.TextField(blank=True, default='')
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('course', 'user')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'is_approved']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Review by {self.user.email} for {self.course.title}"


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
