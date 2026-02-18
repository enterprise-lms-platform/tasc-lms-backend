from time import timezone
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
    trailer_video_url = models.URLField(blank=True, null=True)

    # Requirements and Objectives
    prerequisites = models.TextField(blank=True, help_text="What learners should know before starting")
    learning_objectives = models.TextField(blank=True, help_text="What learners will achieve")
    target_audience = models.TextField(blank=True, help_text="Who this course is for")

    # Settings
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    featured = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

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
        VIDEO = 'video', 'Video'
        TEXT = 'text', 'Text'
        LIVE = 'live', 'Live Session'

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

class LiveStreamSession(models.Model):
    """
    LiveStreamSession represents a live session for a course that an instructor can schedule and manage.
    """
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('live', 'Live'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
    ]
    PLATFORM_CHOICES = [
        ('zoom', 'Zoom'),
        ('google_meet', 'Google Meet'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='live_stream_sessions')

    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='live_stream_sessions'
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(
        help_text="Duration in minutes",
        validators=[MinValueValidator(15), MaxValueValidator(480)]  # 15 min to 8 hours
    )

    timezone = models.CharField(max_length=50, default='UTC')

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='zoom')
    
    meeting_url = models.URLField(blank=True, help_text="URL for learners to join")
    instructor_url = models.URLField(blank=True, help_text="URL for instructor to start")

    platform_meeting_id = models.CharField(max_length=255, blank=True)
    platform_password = models.CharField(max_length=255, blank=True)

     # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Recording
    recording_url = models.URLField(blank=True, help_text="URL of recorded session")
    
    # Calendar Integration
    calendar_event_id = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Google Calendar or other calendar event ID"
    )

    calendar_provider = models.CharField(
        max_length=50, 
        blank=True,
        help_text="google_calendar, outlook, etc."
    )
    
    # Notifications
    reminder_sent = models.BooleanField(default=False)

     # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_livestreams'
    )
    
    # Settings
    max_attendees = models.PositiveIntegerField(null=True, blank=True)
    allow_chat = models.BooleanField(default=True)
    allow_questions = models.BooleanField(default=True)
    mute_on_entry = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['course', 'status']),
            models.Index(fields=['instructor', 'start_time']),
            models.Index(fields=['start_time', 'status']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title} ({self.start_time})"


    @property
    def isis_live(self):
        now = timezone.now()
        return self.status == 'live' and self.start_time <= now <= self.end_time
    
    @property
    def is_upcoming(self):
        return self.status == 'scheduled' and self.start_time > timezone.now()
    
    @property
    def has_ended(self):
        return self.status == 'ended' or self.end_time < timezone.now()
    
    def start_session(self):
        """Start the livestream session"""
        self.status = 'live'
        self.save()
        
        # Notify enrolled learners
        self.notify_learners('Session started')

    def end_session(self):
        """End the livestream session"""
        self.status = 'ended'
        self.save()
    
    def cancel_session(self, reason=""):
        """Cancel the session"""
        self.status = 'cancelled'
        self.save()
        
        # Notify enrolled learners
        self.notify_learners('Session cancelled', reason)

    # def notify_learners(self, event_type, message=""):
    #     """Send notifications to enrolled learners"""
    #     from .tasks import send_livestream_notification
    #     # Implement async notification task
    #     pass

class LiveStreamAttendance(models.Model):
    """
    Track learner attendance in livestream sessions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    session = models.ForeignKey(
        LiveStreamSession,
        on_delete=models.CASCADE,
        related_name='attendance'
    )
     # Attendance tracking
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    
    # Engagement
    questions_asked = models.PositiveIntegerField(default=0)
    chat_messages = models.PositiveIntegerField(default=0)
    
    # Certificate
    certificate_issued = models.BooleanField(default=False)

    class Meta:
        unique_together = ('session', 'learner')
        indexes = [
            models.Index(fields=['session', 'learner']),
        ]
    def __str__(self):
        return f"{self.learner.username} - {self.session.title}"
    
    def mark_joined(self):
        self.joined_at = timezone.now()
        self.save()

    def mark_left(self):
        self.left_at = timezone.now()
        if self.joined_at:
            self.duration_seconds = int((self.left_at - self.joined_at).total_seconds())
        self.save()

class LiveStreamQuestion(models.Model):
    """
    Represents a question asked by a learner during a livestream session.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    session = models.ForeignKey(
        LiveStreamSession,
        on_delete=models.CASCADE,
        related_name='questions'
    )
     # Question details
    question_text = models.TextField()
    asked_at = models.DateTimeField(auto_now_add=True)
    
    # Engagement
    upvotes = models.PositiveIntegerField(default=0)
    answered = models.BooleanField(default=False)

    class Meta:
        ordering = ['asked_at']
        indexes = [
            models.Index(fields=['session', 'asked_at']),
        ]

    def __str__(self):
        return f"Question in {self.session.title} at {self.asked_at}"
