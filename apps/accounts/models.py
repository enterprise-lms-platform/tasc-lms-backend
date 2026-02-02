from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Core user account.
    - Individuals can self-signup and exist without any organization.
    - Organization membership is optional and handled via Membership.
    """

    class Role(models.TextChoices):
        LEARNER = "learner", "Learner"
        ORG_ADMIN = "org_admin", "Org Admin"
        INSTRUCTOR = "instructor", "Instructor"
        FINANCE = "finance", "Finance"
        TASC_ADMIN = "tasc_admin", "TASC Admin"
        LMS_MANAGER = "lms_manager", "LMS Manager"



    email = models.EmailField(unique=True)
    # signup profile
    phone_number = models.CharField(max_length=32, blank=True, null=True)
    country = models.CharField(max_length=80, blank=True, null=True)
    timezone = models.CharField(max_length=80, blank=True, null=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.LEARNER)


    # consent
    marketing_opt_in = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(blank=True, null=True)

    # verification
    email_verified = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.email or self.username


class Organization(models.Model):
    """
    Represents an organization that can enroll staff to consume TASC courses.
    Organizations do NOT create courses; they only manage staff + reporting + billing context.
    """

    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    """
    Links a user to an organization with an org-specific role.
    A user may have no membership (pure individual).
    """

    class Role(models.TextChoices):
        ORG_ADMIN = "ORG_ADMIN", "Org Admin"
        ORG_MANAGER = "ORG_MANAGER", "Org Manager"
        ORG_LEARNER = "ORG_LEARNER", "Org Learner"

        # Platform roles (TASC team)
        TASC_ADMIN = "TASC_ADMIN", "TASC Admin"
        FINANCE = "FINANCE", "Finance"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.ORG_LEARNER
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "organization")

    def __str__(self) -> str:
        return f"{self.user} -> {self.organization} ({self.role})"
