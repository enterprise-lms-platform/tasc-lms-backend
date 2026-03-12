from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    Notification model for user notifications.
    """

    class Type(models.TextChoices):
        APPROVAL = 'approval', 'Approval'
        REGISTRATION = 'registration', 'Registration'
        SYSTEM = 'system', 'System'
        MILESTONE = 'milestone', 'Milestone'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
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
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.title}"
