from time import timezone
import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.postgres.fields import ArrayField
import hmac
import hashlib


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

class LivestreamSession(models.Model):
    """
    Model for livestream sessions with Zoom integration.
    Supports recurring sessions and automatic recording.
    """
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('live', 'Live'),
        ('ended', 'Ended'),
        ('cancelled', 'Cancelled'),
    ]
    
    RECURRENCE_CHOICES = [
        ('none', 'No Recurrence'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Bi-Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    PLATFORM_CHOICES = [
        ('zoom', 'Zoom'),
        ('custom', 'Custom RTMP'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Course relationship
    course = models.ForeignKey(
        'catalogue.Course',
        on_delete=models.CASCADE,
        related_name='livestream_sessions'
    )
    
    # Instructor
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='instructed_livestreams'
    )
    
    # Basic Info
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Scheduling - Core fields
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(
        help_text="Duration in minutes",
        validators=[MinValueValidator(15), MaxValueValidator(480)]
    )
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Recurring sessions
    is_recurring = models.BooleanField(default=False)
    recurrence_pattern = models.CharField(
        max_length=20, 
        choices=RECURRENCE_CHOICES, 
        default='none'
    )
    recurrence_end_date = models.DateTimeField(null=True, blank=True)
    recurrence_days = ArrayField(
        models.CharField(max_length=3, choices=[
            ('mon', 'Monday'), ('tue', 'Tuesday'), ('wed', 'Wednesday'),
            ('thu', 'Thursday'), ('fri', 'Friday'), ('sat', 'Saturday'),
            ('sun', 'Sunday')
        ]),
        blank=True,
        default=list,
        help_text="Days of week for weekly recurrence"
    )
    parent_session = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_sessions'
    )
    recurrence_order = models.PositiveIntegerField(default=0)
    
    # Livestream Platform - Zoom focused
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='zoom')
    
    # Zoom Meeting Details - Auto-generated
    zoom_meeting_id = models.CharField(max_length=255, blank=True, help_text="Zoom Meeting ID")
    zoom_meeting_uuid = models.CharField(max_length=255, blank=True, help_text="Zoom Meeting UUID")
    zoom_host_id = models.CharField(max_length=255, blank=True, help_text="Zoom Host ID")
    zoom_topic = models.CharField(max_length=255, blank=True)
    
    # Auto-generated links
    join_url = models.URLField(blank=True, help_text="URL for learners to join")
    start_url = models.URLField(blank=True, help_text="URL for instructor to start (contains auth)")
    instructor_join_url = models.URLField(blank=True, help_text="Alternative join URL for instructor")
    
    # Meeting security
    password = models.CharField(max_length=50, blank=True, help_text="Meeting password")
    encrypted_password = models.CharField(max_length=255, blank=True)
    
    # Recording - Automatic
    auto_recording = models.BooleanField(
        default=True,
        help_text="Automatically record the session"
    )
    recording_url = models.URLField(blank=True, help_text="URL of recorded session")
    recording_start_time = models.DateTimeField(null=True, blank=True)
    recording_end_time = models.DateTimeField(null=True, blank=True)
    recording_duration = models.PositiveIntegerField(default=0, help_text="Recording duration in seconds")
    recording_file_size = models.PositiveIntegerField(default=0, help_text="Recording file size in bytes")
    recording_download_url = models.URLField(blank=True, help_text="Download URL for recording")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Settings
    max_attendees = models.PositiveIntegerField(null=True, blank=True)
    waiting_room = models.BooleanField(default=True, help_text="Enable waiting room")
    mute_on_entry = models.BooleanField(default=True)
    allow_chat = models.BooleanField(default=True)
    allow_questions = models.BooleanField(default=True)
    host_video = models.BooleanField(default=True)
    participant_video = models.BooleanField(default=False)
    
    # Calendar Integration
    calendar_event_id = models.CharField(max_length=255, blank=True)
    calendar_provider = models.CharField(max_length=50, blank=True, default='google')
    calendar_etag = models.CharField(max_length=255, blank=True)
    
    # Attendance tracking
    total_attendees = models.PositiveIntegerField(default=0)
    peak_attendees = models.PositiveIntegerField(default=0)
    
    # Notifications
    reminder_sent_24h = models.BooleanField(default=False)
    reminder_sent_1h = models.BooleanField(default=False)
    reminder_sent_15m = models.BooleanField(default=False)
    
    # Webhook verification
    webhook_secret = models.CharField(max_length=255, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_livestreams'
    )
    
    # Zoom webhook tracking
    zoom_webhook_received = models.BooleanField(default=False)
    zoom_webhook_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['course', 'status']),
            models.Index(fields=['instructor', 'start_time']),
            models.Index(fields=['start_time', 'status']),
            models.Index(fields=['zoom_meeting_id']),
        ]
        verbose_name = "Livestream Session"
        verbose_name_plural = "Livestream Sessions"
    
    def __str__(self):
        return f"{self.course.title} - {self.title} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"
    
    @property
    def is_live(self):
        now = timezone.now()
        return self.status == 'live' and self.start_time <= now <= self.end_time
    
    @property
    def is_upcoming(self):
        return self.status == 'scheduled' and self.start_time > timezone.now()
    
    @property
    def has_ended(self):
        return self.status == 'ended' or self.end_time < timezone.now()
    
    @property
    def formatted_start_time(self):
        """Return start time in ISO format for APIs"""
        return self.start_time.isoformat()
    
    @property
    def formatted_end_time(self):
        """Return end time in ISO format for APIs"""
        return self.end_time.isoformat()
    
    def start_session(self):
        """Start the livestream session"""
        self.status = 'live'
        self.save(update_fields=['status'])
        
        # # Notify enrolled learners via WebSocket/Notification
        # from .tasks import notify_session_started
        # notify_session_started.delay(self.id)
    
    def end_session(self):
        """End the livestream session"""
        self.status = 'ended'
        self.save(update_fields=['status'])
        
        # # Process attendance and generate reports
        # from .tasks import process_session_attendance
        # process_session_attendance.delay(self.id)
    
    def cancel_session(self, reason=""):
        """Cancel the session"""
        self.status = 'cancelled'
        self.save(update_fields=['status'])
        
        # # Notify enrolled learners
        # from .tasks import notify_session_cancelled
        # notify_session_cancelled.delay(self.id, reason)
    
    def update_recording(self, recording_data):
        """Update recording information after session ends"""
        self.recording_url = recording_data.get('share_url', '')
        self.recording_start_time = recording_data.get('recording_start')
        self.recording_end_time = recording_data.get('recording_end')
        self.recording_duration = recording_data.get('duration', 0)
        self.recording_download_url = recording_data.get('download_url', '')
        self.save(update_fields=[
            'recording_url', 'recording_start_time', 'recording_end_time',
            'recording_duration', 'recording_download_url'
        ])
    
    def verify_webhook(self, signature, payload):
        """Verify Zoom webhook signature"""
        secret = settings.ZOOM_WEBHOOK_SECRET.encode('utf-8')
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    
    def get_timezone_aware_time(self, user_timezone='UTC'):
        """Get start time converted to user's timezone"""
        import pytz
        try:
            user_tz = pytz.timezone(user_timezone)
            return self.start_time.astimezone(user_tz)
        except:
            return self.start_time


class LivestreamAttendance(models.Model):
    """
    Track learner attendance in livestream sessions.
    Automatically updated via Zoom webhooks.
    """
    
    ATTENDANCE_STATUS = [
        ('registered', 'Registered'),
        ('joined', 'Joined'),
        ('left', 'Left'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    session = models.ForeignKey(
        LivestreamSession,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    
    learner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='livestream_attendances'
    )
    
    # Attendance tracking - Auto populated via Zoom
    zoom_participant_id = models.CharField(max_length=255, blank=True)
    zoom_user_id = models.CharField(max_length=255, blank=True)
    
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    
    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUS, default='registered')
    
    # Engagement tracking
    questions_asked = models.PositiveIntegerField(default=0)
    chat_messages = models.PositiveIntegerField(default=0)
    raised_hand = models.BooleanField(default=False)
    device_info = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Certificate
    certificate_issued = models.BooleanField(default=False)
    certificate_url = models.URLField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['session', 'learner']
        indexes = [
            models.Index(fields=['session', 'status']),
            models.Index(fields=['learner', 'joined_at']),
        ]
        verbose_name = "Livestream Attendance"
        verbose_name_plural = "Livestream Attendances"
    
    def __str__(self):
        return f"{self.learner.email} - {self.session.title}"
    
    def mark_joined(self, participant_data=None):
        """Mark learner as joined"""
        self.status = 'joined'
        self.joined_at = timezone.now()
        
        if participant_data:
            self.zoom_participant_id = participant_data.get('participant_id', '')
            self.device_info = participant_data.get('device', '')
        
        self.save(update_fields=['status', 'joined_at', 'zoom_participant_id', 'device_info'])
        
        # Update session stats
        self.session.total_attendees = self.session.attendances.filter(
            joined_at__isnull=False
        ).count()
        self.session.save(update_fields=['total_attendees'])
    
    def mark_left(self):
        """Mark learner as left"""
        self.status = 'left'
        self.left_at = timezone.now()
        
        if self.joined_at:
            delta = self.left_at - self.joined_at
            self.duration_seconds = int(delta.total_seconds())
        
        self.save(update_fields=['status', 'left_at', 'duration_seconds'])
    
    def mark_completed(self):
        """Mark attendance as completed (attended full session)"""
        self.status = 'completed'
        self.save(update_fields=['status'])
    
    @property
    def attendance_percentage(self):
        """Calculate percentage of session attended"""
        if not self.joined_at or not self.session.duration_minutes:
            return 0
        
        session_duration = self.session.duration_minutes * 60
        if session_duration == 0:
            return 0
        
        return min(100, int((self.duration_seconds / session_duration) * 100))


class LivestreamRecording(models.Model):
    """
    Store recordings of livestream sessions.
    Automatically populated from Zoom cloud recordings.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    session = models.ForeignKey(
        LivestreamSession,
        on_delete=models.CASCADE,
        related_name='recordings'
    )
    
    # Zoom recording data
    zoom_recording_id = models.CharField(max_length=255, unique=True)
    zoom_meeting_id = models.CharField(max_length=255)
    
    # Recording files
    recording_type = models.CharField(max_length=50)  # shared_screen, gallery_view, etc.
    file_url = models.URLField()
    download_url = models.URLField(blank=True)
    file_size = models.PositiveIntegerField(default=0)
    file_extension = models.CharField(max_length=10, default='mp4')
    
    # Timing
    recording_start = models.DateTimeField()
    recording_end = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()
    
    # Status
    is_processed = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    
    # Storage
    storage_path = models.CharField(max_length=500, blank=True)
    thumbnail_url = models.URLField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-recording_start']
        verbose_name = "Livestream Recording"
        verbose_name_plural = "Livestream Recordings"
    
    def __str__(self):
        return f"Recording: {self.session.title} - {self.recording_type}"
    
    def get_download_url(self):
        """Get download URL (with token for authenticated users)"""
        # Implement signed URL logic
        return self.download_url