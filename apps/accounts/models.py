import uuid

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

    # Profile
    avatar = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Google OAuth
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    google_picture = models.URLField(blank=True, null=True)

    # consent
    marketing_opt_in = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(blank=True, null=True)

    # verification
    email_verified = models.BooleanField(default=False)
    must_set_password = models.BooleanField(default=False)

    # login lockout (US-015)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Ensure Django superusers are always treated as platform super admins
        if self.is_superuser:
            # force app role
            if self.role != self.Role.TASC_ADMIN:
                self.role = self.Role.TASC_ADMIN

            # superuser bootstrap should not be blocked by verification
            if not self.email_verified:
                self.email_verified = True

            # safety: make sure the account can log in
            if not self.is_active:
                self.is_active = True

        super().save(*args, **kwargs)


    def __str__(self) -> str:
        return self.email or self.username


class LoginOTPChallenge(models.Model):
    """
    OTP challenge for mandatory email OTP on every login.
    Stores hashed OTP only; plain OTP is never persisted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_otp_challenges",
    )
    otp_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    send_count = models.PositiveSmallIntegerField(default=1)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]


class Organization(models.Model):
    """
    Represents an organization that can enroll staff to consume TASC courses.
    Organizations do NOT create courses; they only manage staff + reporting + billing context.
    """

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    description = models.TextField(blank=True)
    logo = models.URLField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    # Contact
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=32, blank=True, null=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True)
    max_seats = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum number of seats")
    
    # Billing
    billing_email = models.EmailField(blank=True, null=True)
    billing_address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]

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
    
    # Job details
    job_title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_memberships'
    )

    class Meta:
        unique_together = ("user", "organization")
        indexes = [
            models.Index(fields=['organization', 'is_active']),
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.organization} ({self.role})"
