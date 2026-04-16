from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    Notification model for user notifications.
    """

    class Type(models.TextChoices):
        APPROVAL = "approval", "Approval"
        REGISTRATION = "registration", "Registration"
        SYSTEM = "system", "System"
        MILESTONE = "milestone", "Milestone"
        COURSE_UPDATE = "course_update", "Course Update"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )

    # Notification content
    type = models.CharField(max_length=20, choices=Type.choices)
    title = models.CharField(max_length=255)
    description = models.TextField()

    # Status
    is_read = models.BooleanField(default=False)

    # Optional link
    link = models.CharField(max_length=500, blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.title}"


def notify_enrolled_learners(course, title, description, link=None):
    """
    Notify all learners enrolled in a course about an update.
    Used when course content changes (new sessions, quiz updates, etc.)
    """
    from apps.learning.models import Enrollment

    enrolled_user_ids = (
        Enrollment.objects.filter(course=course, is_active=True)
        .values_list("user_id", flat=True)
        .distinct()
    )

    notifications = []
    for user_id in enrolled_user_ids:
        notifications.append(
            Notification(
                user_id=user_id,
                type=Notification.Type.COURSE_UPDATE,
                title=title,
                description=description,
                link=link or f"/learner/courses/{course.id}",
            )
        )

    if notifications:
        Notification.objects.bulk_create(notifications, ignore_conflicts=True)

    return len(notifications)
