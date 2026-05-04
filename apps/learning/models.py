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
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        DROPPED = "dropped", "Dropped"
        EXPIRED = "expired", "Expired"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments"
    )
    course = models.ForeignKey(
        "catalogue.Course", on_delete=models.CASCADE, related_name="enrollments"
    )

    # Enrollment details
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Progress tracking
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    last_accessed_at = models.DateTimeField(auto_now=True)
    last_accessed_session = models.ForeignKey(
        "catalogue.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_accessed_by",
    )

    # Payment and pricing snapshot
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    payment_transaction = models.ForeignKey(
        "payments.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
    )

    # Certificate
    certificate_issued = models.BooleanField(default=False)
    certificate_issued_at = models.DateTimeField(null=True, blank=True)

    # Organization context
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
    )

    class Meta:
        unique_together = ("user", "course")
        ordering = ["-enrolled_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["course", "status"]),
            models.Index(fields=["-enrolled_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.course.title}"

    def update_progress(self):
        """Update progress based on completed sessions"""
        completed_sessions = (
            SessionProgress.objects.filter(
                enrollment=self,
                is_completed=True,
                session__course=self.course,
            )
            .values("session_id")
            .distinct()
            .count()
        )
        total_sessions = self.course.sessions.count()

        if total_sessions <= 0:
            self.progress_percentage = 0
        else:
            progress = (completed_sessions / total_sessions) * 100
            self.progress_percentage = min(progress, 100)

        # Check if course is completed — all sessions done AND all graded assignments passed
        if self.progress_percentage >= 100 and self.status != self.Status.COMPLETED:
            all_passed = self._all_graded_assignments_passed()
            if all_passed:
                self.status = self.Status.COMPLETED
                self.completed_at = timezone.now()

        self.save()
        return self.progress_percentage

    def _all_graded_assignments_passed(self):
        """Return True if every assignment session with a passing_score set has a passing submission."""
        from apps.catalogue.models import Session as CourseSession
        graded_assignment_sessions = CourseSession.objects.filter(
            course=self.course,
            session_type='assignment',
            assignment__isnull=False,
            assignment__passing_score__isnull=False,
        ).values_list('id', flat=True)

        if not graded_assignment_sessions:
            return True

        passed_count = Submission.objects.filter(
            enrollment=self,
            assignment__session_id__in=graded_assignment_sessions,
            is_passed=True,
        ).values('assignment__session_id').distinct().count()

        return passed_count >= len(graded_assignment_sessions)


class SessionProgress(models.Model):
    """
    SessionProgress tracks a user's progress through individual sessions.
    """

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="session_progress"
    )
    session = models.ForeignKey(
        "catalogue.Session", on_delete=models.CASCADE, related_name="progress"
    )

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

    # Video resume - stores playback position in seconds for cross-device resume
    video_position_seconds = models.PositiveIntegerField(default=0, blank=True)

    class Meta:
        unique_together = ("enrollment", "session")
        ordering = ["-last_accessed_at"]

    def __str__(self):
        return f"{self.enrollment.user.email} - {self.session.title}"

    @property
    def duration_minutes(self):
        return (
            self.session.video_duration_seconds // 60
            if self.session.video_duration_seconds
            else 0
        )

    @property
    def time_spent_minutes(self):
        return self.time_spent_seconds // 60


class Certificate(models.Model):
    """
    Certificate represents completion certificates for courses.
    """

    enrollment = models.OneToOneField(
        Enrollment, on_delete=models.CASCADE, related_name="certificate"
    )

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
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.enrollment.user.email} - {self.enrollment.course.title}"

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            self.certificate_number = self.generate_certificate_number()
        super().save(*args, **kwargs)

    def generate_certificate_number(self):
        """Generate a unique certificate number"""
        prefix = "TASC"
        date_str = timezone.now().strftime("%Y%m%d")
        random_str = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
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
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        GRADED = "graded", "Graded"

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    assignment = models.ForeignKey(
        "catalogue.Assignment",
        on_delete=models.CASCADE,
        related_name="submissions",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    submitted_text = models.TextField(blank=True, default="")
    submitted_file_url = models.URLField(max_length=2048, blank=True, null=True)
    submitted_file_name = models.CharField(max_length=255, blank=True, null=True)

    grade = models.PositiveIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True, default="")
    internal_notes = models.TextField(blank=True, default="")
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_submissions",
    )

    attempt_number = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("enrollment", "assignment", "attempt_number")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["enrollment", "assignment"]),
            models.Index(fields=["assignment", "status"]),
            models.Index(fields=["status"]),
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
        related_name="quiz_submissions",
    )
    quiz = models.ForeignKey(
        "catalogue.Quiz",
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    attempt_number = models.PositiveIntegerField(default=1)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    passed = models.BooleanField(default=False)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["enrollment", "quiz"]),
            models.Index(fields=["quiz", "submitted_at"]),
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
        related_name="answers",
    )
    question = models.ForeignKey(
        "catalogue.QuizQuestion",
        on_delete=models.CASCADE,
    )
    selected_answer = models.JSONField()
    is_correct = models.BooleanField(null=True, blank=True)
    points_awarded = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        indexes = [
            models.Index(fields=["submission", "question"]),
        ]

    def __str__(self):
        return f"Answer for Q{self.question.order} in {self.submission}"


class Discussion(models.Model):
    """
    Discussion represents discussion threads for courses/sessions.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discussions"
    )
    course = models.ForeignKey(
        "catalogue.Course",
        on_delete=models.CASCADE,
        related_name="discussions",
        null=True,
        blank=True,
    )
    session = models.ForeignKey(
        "catalogue.Session",
        on_delete=models.CASCADE,
        related_name="discussions",
        null=True,
        blank=True,
    )

    # Content
    title = models.CharField(max_length=255)
    content = models.TextField()

    # Moderation
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False, help_text="Hidden pending moderator review")
    report_count = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["course"]),
            models.Index(fields=["session"]),
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

    discussion = models.ForeignKey(
        Discussion, on_delete=models.CASCADE, related_name="replies"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_replies",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )

    # Content
    content = models.TextField()

    # Moderation
    is_deleted = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False, help_text="Hidden pending moderator review")
    report_count = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.discussion.title}"


class DiscussionReport(models.Model):
    """Tracks individual reports against discussions or replies."""

    REASON_CHOICES = [
        ('spam', 'Spam'),
        ('abusive', 'Abusive or Offensive Language'),
        ('off_topic', 'Off-Topic'),
        ('misinformation', 'Misinformation'),
        ('other', 'Other'),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discussion_reports'
    )
    discussion = models.ForeignKey(
        Discussion, on_delete=models.CASCADE, null=True, blank=True, related_name='reports'
    )
    reply = models.ForeignKey(
        DiscussionReply, on_delete=models.CASCADE, null=True, blank=True, related_name='reports'
    )
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        unique_together = [('reporter', 'discussion'), ('reporter', 'reply')]
        ordering = ['-created_at']

    def __str__(self):
        target = f"discussion #{self.discussion_id}" if self.discussion_id else f"reply #{self.reply_id}"
        return f"Report by {self.reporter.email} on {target} ({self.reason})"


class Report(models.Model):
    """
    Report model for generated organization reports.
    """

    class Type(models.TextChoices):
        USER_ACTIVITY = "user_activity", "User Activity"
        COURSE_PERFORMANCE = "course_performance", "Course Performance"
        ENROLLMENT = "enrollment", "Enrollment"
        COMPLETION = "completion", "Completion"
        ASSESSMENT = "assessment", "Assessment"
        REVENUE = "revenue", "Revenue"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    # Report details
    report_type = models.CharField(max_length=30, choices=Type.choices)
    name = models.CharField(max_length=255)

    # Generation info
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="generated_reports",
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    # Status
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROCESSING
    )

    # File
    file = models.FileField(upload_to="reports/", blank=True, null=True)
    file_size = models.CharField(max_length=50, blank=True, null=True)

    # Filter parameters (stored as JSON)
    parameters = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.name} - {self.status}"


class Badge(models.Model):
    """
    Badge represents an achievable badge/award for learners.
    Seeded via `python manage.py seed_badges`.
    """

    class Category(models.TextChoices):
        COURSE_COMPLETION = "course_completion", "Course Completion"
        ENROLLMENT = "enrollment", "Enrollment Milestones"
        SUBSCRIPTION = "subscription", "Subscription Loyalty"
        ASSESSMENT = "assessment", "Assessment Excellence"
        ENGAGEMENT = "engagement", "Engagement"
        MILESTONE = "milestone", "Milestones"

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    icon_url = models.URLField(blank=True, default="")
    category = models.CharField(max_length=50, choices=Category.choices)
    criteria_type = models.CharField(max_length=50)
    criteria_value = models.IntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "order"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class UserBadge(models.Model):
    """
    UserBadge tracks which user has earned which badge.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="earned_badges",
    )
    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name="earners",
    )
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "badge"]
        indexes = [models.Index(fields=["user", "-earned_at"])]
        ordering = ["-earned_at"]

    def __str__(self):
        return f"{self.user} → {self.badge.name}"


class SavedCourse(models.Model):
    """
    SavedCourse represents a user's bookmarked/favorited course.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_courses"
    )
    course = models.ForeignKey(
        "catalogue.Course", on_delete=models.CASCADE, related_name="saved_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "course")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} saved {self.course.title}"


class Workshop(models.Model):
    """
    Workshop represents an in-person training event.
    """

    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"

    class GradingType(models.TextChoices):
        ATTENDANCE = "attendance", "Attendance Only"
        PASS_FAIL = "pass_fail", "Pass / Fail"
        SCORE = "score", "Score (0-100)"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    location = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    max_participants = models.PositiveIntegerField(default=30)
    participants_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UPCOMING
    )
    grading_type = models.CharField(
        max_length=20, choices=GradingType.choices, default=GradingType.ATTENDANCE
    )
    category = models.CharField(max_length=100, default="General")

    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workshops_taught",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.title

    @property
    def participants(self):
        return self.participants_count


class WorkshopAttendance(models.Model):
    """
    Tracks learner attendance for workshops.
    """

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"

    workshop = models.ForeignKey(
        Workshop, on_delete=models.CASCADE, related_name="attendances"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workshop_attendances",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PRESENT
    )
    grade = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    marked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["workshop", "user"]
        ordering = ["-marked_at"]

    def __str__(self):
        return f"{self.user.email} - {self.workshop.title} ({self.status})"
