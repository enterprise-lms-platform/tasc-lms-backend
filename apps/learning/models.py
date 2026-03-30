from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.text import slugify
import random
import string


class Enrollment(models.Model):
    """
    Enrollment represents a user's enrollment in a course.
    """
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        DROPPED = 'dropped', 'Dropped'
        EXPIRED = 'expired', 'Expired'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    course = models.ForeignKey(
        'catalogue.Course',
        on_delete=models.CASCADE,
        related_name='enrollments'
    )

    # Enrollment details
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Progress tracking
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    last_accessed_at = models.DateTimeField(auto_now=True)
    last_accessed_session = models.ForeignKey(
        'catalogue.Session',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_accessed_by'
    )

    # Payment and pricing snapshot
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    payment_transaction = models.ForeignKey(
        'payments.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='enrollments'
    )

    # Certificate
    certificate_issued = models.BooleanField(default=False)
    certificate_issued_at = models.DateTimeField(null=True, blank=True)

    # Organization context
    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='enrollments'
    )

    class Meta:
        unique_together = ('user', 'course')
        ordering = ['-enrolled_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['course', 'status']),
            models.Index(fields=['-enrolled_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.course.title}"

    def update_progress(self):
        """Update progress based on completed sessions"""
        completed_sessions = SessionProgress.objects.filter(
            enrollment=self,
            is_completed=True,
            session__course=self.course,
        ).values('session_id').distinct().count()
        total_sessions = self.course.sessions.count()

        if total_sessions <= 0:
            self.progress_percentage = 0
        else:
            progress = (completed_sessions / total_sessions) * 100
            self.progress_percentage = min(progress, 100)
        
        # Check if course is completed
        if self.progress_percentage >= 100 and self.status != self.Status.COMPLETED:
            self.status = self.Status.COMPLETED
            self.completed_at = timezone.now()
        
        self.save()
        return self.progress_percentage


class SessionProgress(models.Model):
    """
    SessionProgress tracks a user's progress through individual sessions.
    """
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='session_progress')
    session = models.ForeignKey('catalogue.Session', on_delete=models.CASCADE, related_name='progress')

    # Completion tracking
    is_started = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Time tracking
    time_spent_seconds = models.PositiveIntegerField(default=0)
    last_accessed_at = models.DateTimeField(auto_now=True)

    # Notes
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('enrollment', 'session')
        ordering = ['-last_accessed_at']

    def __str__(self):
        return f"{self.enrollment.user.email} - {self.session.title}"

    @property
    def duration_minutes(self):
        return self.session.video_duration_seconds // 60 if self.session.video_duration_seconds else 0

    @property
    def time_spent_minutes(self):
        return self.time_spent_seconds // 60


class Certificate(models.Model):
    """
    Certificate represents completion certificates for courses.
    """
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='certificate')
    
    # Certificate details
    certificate_number = models.CharField(max_length=100, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    is_valid = models.BooleanField(default=True)
    
    # PDF
    pdf_url = models.URLField(blank=True, null=True)
    
    # Verification
    verification_url = models.URLField(blank=True, null=True)
    
    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f"{self.enrollment.user.email} - {self.enrollment.course.title}"

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            self.certificate_number = self.generate_certificate_number()
        super().save(*args, **kwargs)

    def generate_certificate_number(self):
        """Generate a unique certificate number"""
        prefix = 'TASC'
        date_str = timezone.now().strftime('%Y%m%d')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"{prefix}-{date_str}-{random_str}"

    @property
    def is_expired(self):
        if self.expiry_date:
            return timezone.now() > self.expiry_date
        return False


class Submission(models.Model):
    """
    Submission represents a learner's submission for an assignment.
    V1: one submission per (enrollment, assignment).
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        GRADED = 'graded', 'Graded'

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    assignment = models.ForeignKey(
        'catalogue.Assignment',
        on_delete=models.CASCADE,
        related_name='submissions',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    submitted_text = models.TextField(blank=True, default='')
    submitted_file_url = models.URLField(max_length=2048, blank=True, null=True)
    submitted_file_name = models.CharField(max_length=255, blank=True, null=True)

    grade = models.PositiveIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True, default='')
    internal_notes = models.TextField(blank=True, default='')
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='graded_submissions',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('enrollment', 'assignment')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['enrollment', 'assignment']),
            models.Index(fields=['assignment', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.enrollment.user.email} - {self.assignment.session.title}"


class QuizSubmission(models.Model):
    """
    QuizSubmission stores a learner's attempt at a quiz.
    """
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='quiz_submissions',
    )
    quiz = models.ForeignKey(
        'catalogue.Quiz',
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    attempt_number = models.PositiveIntegerField(default=1)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    passed = models.BooleanField(default=False)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['enrollment', 'quiz']),
            models.Index(fields=['quiz', 'submitted_at']),
        ]

    def __str__(self):
        return f"{self.enrollment.user.email} - {self.quiz.session.title} (Attempt {self.attempt_number})"


class QuizAnswer(models.Model):
    """
    QuizAnswer stores the learner's answer for a single question in a quiz submission.
    """
    submission = models.ForeignKey(
        QuizSubmission,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    question = models.ForeignKey(
        'catalogue.QuizQuestion',
        on_delete=models.CASCADE,
    )
    selected_answer = models.JSONField()
    is_correct = models.BooleanField(null=True, blank=True)
    points_awarded = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        indexes = [
            models.Index(fields=['submission', 'question']),
        ]

    def __str__(self):
        return f"Answer for Q{self.question.order} in {self.submission}"


class Discussion(models.Model):
    """
    Discussion represents discussion threads for courses/sessions.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='discussions'
    )
    course = models.ForeignKey(
        'catalogue.Course',
        on_delete=models.CASCADE,
        related_name='discussions',
        null=True,
        blank=True
    )
    session = models.ForeignKey(
        'catalogue.Session',
        on_delete=models.CASCADE,
        related_name='discussions',
        null=True,
        blank=True
    )
    
    # Content
    title = models.CharField(max_length=255)
    content = models.TextField()
    
    # Moderation
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['course']),
            models.Index(fields=['session']),
        ]

    def __str__(self):
        return self.title

    @property
    def reply_count(self):
        return self.replies.count()


class DiscussionReply(models.Model):
    """
    DiscussionReply represents replies to discussions.
    """
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='discussion_replies'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    
    # Content
    content = models.TextField()
    
    # Moderation
    is_deleted = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.email} - {self.discussion.title}"


class Report(models.Model):
    """
    Report model for generated organization reports.
    """

    class Type(models.TextChoices):
        USER_ACTIVITY = 'user_activity', 'User Activity'
        COURSE_PERFORMANCE = 'course_performance', 'Course Performance'
        ENROLLMENT = 'enrollment', 'Enrollment'
        COMPLETION = 'completion', 'Completion'
        ASSESSMENT = 'assessment', 'Assessment'
        REVENUE = 'revenue', 'Revenue'

    class Status(models.TextChoices):
        PROCESSING = 'processing', 'Processing'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    # Report details
    report_type = models.CharField(max_length=30, choices=Type.choices)
    name = models.CharField(max_length=255)
    
    # Generation info
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_reports'
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSING
    )
    
    # File
    file = models.FileField(upload_to='reports/', blank=True, null=True)
    file_size = models.CharField(max_length=50, blank=True, null=True)
    
    # Filter parameters (stored as JSON)
    parameters = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"{self.name} - {self.status}"
