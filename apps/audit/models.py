from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Centralized audit log for system activities."""

    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"

    class Resource(models.TextChoices):
        USER = "user", "User"
        COURSE = "course", "Course"
        ORGANIZATION = "organization", "Organization"
        PAYMENT = "payment", "Payment"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_name = models.CharField(max_length=255, blank=True)
    actor_email = models.EmailField(blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    resource = models.CharField(max_length=30, choices=Resource.choices)
    resource_id = models.CharField(max_length=255, null=True, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["action"]),
            models.Index(fields=["resource"]),
            models.Index(fields=["organization"]),
            models.Index(fields=["actor"]),
        ]

    def __str__(self):
        return f"{self.action} {self.resource} by {self.actor_email or 'system'} at {self.created_at}"
