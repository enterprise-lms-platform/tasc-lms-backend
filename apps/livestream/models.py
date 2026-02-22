from django.utils import timezone
import uuid
import hmac
import hashlib
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


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

    course = models.ForeignKey(
        'catalogue.Course',
        on_delete=models.CASCADE,
        related_name='livestream_sessions'
    )

    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='instructed_livestreams'
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(
        help_text="Duration in minutes",
        validators=[MinValueValidator(15), MaxValueValidator(480)]
    )
    timezone = models.CharField(max_length=50, default='UTC')

    is_recurring = models.BooleanField(default=False)
    recurrence_pattern = models.CharField(
        max_length=20,
        choices=RECURRENCE_CHOICES,
        default='none'
    )
    recurrence_end_date = models.DateTimeField(null=True, blank=True)
    recurrence_days = models.JSONField(
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

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='zoom')

    zoom_meeting_id = models.CharField(max_length=255, blank=True, help_text="Zoom Meeting ID")
    zoom_meeting_uuid = models.CharField(max_length=255, blank=True, help_text="Zoom Meeting UUID")
    zoom_host_id = models.CharField(max_length=255, blank=True, help_text="Zoom Host ID")
    zoom_topic = models.CharField(max_length=255, blank=True)

    join_url = models.URLField(blank=True, help_text="URL for learners to join")
    start_url = models.URLField(blank=True, help_text="URL for instructor to start (contains auth)")
    instructor_join_url = models.URLField(blank=True, help_text="Alternative join URL for instructor")

    password = models.CharField(max_length=50, blank=True, help_text="Meeting password")
    encrypted_password = models.CharField(max_length=255, blank=True)

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

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')

    max_attendees = models.PositiveIntegerField(null=True, blank=True)
    waiting_room = models.BooleanField(default=True, help_text="Enable waiting room")
    mute_on_entry = models.BooleanField(default=True)
    allow_chat = models.BooleanField(default=True)
    allow_questions = models.BooleanField(default=True)
    host_video = models.BooleanField(default=True)
    participant_video = models.BooleanField(default=False)

    calendar_event_id = models.CharField(max_length=255, blank=True)
    calendar_provider = models.CharField(max_length=50, blank=True, default='google')
    calendar_etag = models.CharField(max_length=255, blank=True)

    total_attendees = models.PositiveIntegerField(default=0)
    peak_attendees = models.PositiveIntegerField(default=0)

    reminder_sent_24h = models.BooleanField(default=False)
    reminder_sent_1h = models.BooleanField(default=False)
    reminder_sent_15m = models.BooleanField(default=False)

    webhook_secret = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_livestreams'
    )

    zoom_webhook_received = models.BooleanField(default=False)
    zoom_webhook_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'catalogue_livestreamsession'
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

    def end_session(self):
        """End the livestream session"""
        self.status = 'ended'
        self.save(update_fields=['status'])

    def cancel_session(self, reason=""):
        """Cancel the session"""
        self.status = 'cancelled'
        self.save(update_fields=['status'])

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
        except Exception:
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

    zoom_participant_id = models.CharField(max_length=255, blank=True)
    zoom_user_id = models.CharField(max_length=255, blank=True)

    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUS, default='registered')

    questions_asked = models.PositiveIntegerField(default=0)
    chat_messages = models.PositiveIntegerField(default=0)
    raised_hand = models.BooleanField(default=False)
    device_info = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    certificate_issued = models.BooleanField(default=False)
    certificate_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'catalogue_livestreamattendance'
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

    zoom_recording_id = models.CharField(max_length=255, unique=True)
    zoom_meeting_id = models.CharField(max_length=255)

    recording_type = models.CharField(max_length=50)
    file_url = models.URLField()
    download_url = models.URLField(blank=True)
    file_size = models.PositiveIntegerField(default=0)
    file_extension = models.CharField(max_length=10, default='mp4')

    recording_start = models.DateTimeField()
    recording_end = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()

    is_processed = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    storage_path = models.CharField(max_length=500, blank=True)
    thumbnail_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'catalogue_livestreamrecording'
        ordering = ['-recording_start']
        verbose_name = "Livestream Recording"
        verbose_name_plural = "Livestream Recordings"

    def __str__(self):
        return f"Recording: {self.session.title} - {self.recording_type}"

    def get_download_url(self):
        """Get download URL (with token for authenticated users)"""
        return self.download_url
