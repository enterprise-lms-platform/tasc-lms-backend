"""Permissions for subscription-gated content access."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import BasePermission

from apps.accounts.rbac import is_admin_like, is_instructor
from .models import UserSubscription

GRACE_PERIOD_DAYS = 7


def user_has_active_subscription(user, include_grace_period=True):
    """
    Check if user has an active UserSubscription.
    Uses is_active logic: status=='active' and end_date is null or in the future.
    Includes grace period if include_grace_period=True.
    """
    if not user or not user.is_authenticated:
        return False

    now = timezone.now()

    # Check for active subscription with no expiry or future expiry
    qs = UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.Status.ACTIVE,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=now))

    if qs.exists():
        return True

    # Check grace period
    if include_grace_period:
        grace_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)
        grace_qs = UserSubscription.objects.filter(
            user=user,
            status=UserSubscription.Status.ACTIVE,
            end_date__gt=grace_cutoff,
            end_date__lte=now,
        )
        return grace_qs.exists()

    return False


def organization_has_active_subscription(organization, include_grace_period=True):
    """Check if organization has an active subscription (for org learners)."""
    if not organization:
        return False

    now = timezone.now()

    qs = UserSubscription.objects.filter(
        organization=organization,
        status=UserSubscription.Status.ACTIVE,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=now))

    if qs.exists():
        return True

    if include_grace_period:
        grace_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)
        grace_qs = UserSubscription.objects.filter(
            organization=organization,
            status=UserSubscription.Status.ACTIVE,
            end_date__gt=grace_cutoff,
            end_date__lte=now,
        )
        return grace_qs.exists()

    return False


def get_best_active_subscription(user):
    """
    Return the best active UserSubscription for the user, or None.
    Selection: prefer end_date null (never expires), else latest end_date.
    """
    if not user or not user.is_authenticated:
        return None
    qs = (
        UserSubscription.objects.filter(
            user=user,
            status=UserSubscription.Status.ACTIVE,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=timezone.now()))
        .select_related("subscription")
    )
    # Prefer null end_date, then order by end_date descending
    with_null = qs.filter(end_date__isnull=True).first()
    if with_null:
        return with_null
    return qs.filter(end_date__isnull=False).order_by("-end_date").first()


def get_subscription_status(user, organization=None):
    """
    Return detailed subscription status for a user.
    Includes grace period info for UI display.
    """
    now = timezone.now()
    grace_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)

    # Check personal subscription
    personal_sub = (
        UserSubscription.objects.filter(
            user=user,
            status=UserSubscription.Status.ACTIVE,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
        .select_related("subscription")
        .first()
    )

    if personal_sub:
        return {
            "has_subscription": True,
            "type": "personal",
            "subscription": personal_sub,
            "in_grace_period": False,
        }

    # Check grace period
    grace_sub = (
        UserSubscription.objects.filter(
            user=user,
            status=UserSubscription.Status.ACTIVE,
            end_date__gt=grace_cutoff,
            end_date__lte=now,
        )
        .select_related("subscription")
        .first()
    )

    if grace_sub:
        days_expired = (now - grace_sub.end_date).days
        return {
            "has_subscription": False,
            "type": "personal",
            "subscription": grace_sub,
            "in_grace_period": True,
            "days_in_grace_period": days_expired,
            "grace_days_remaining": GRACE_PERIOD_DAYS - days_expired,
        }

    # Check org subscription
    if organization:
        org_active = (
            UserSubscription.objects.filter(
                organization=organization,
                status=UserSubscription.Status.ACTIVE,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
            .first()
        )

        if org_active:
            return {
                "has_subscription": True,
                "type": "organization",
                "subscription": org_active,
                "in_grace_period": False,
            }

        # Check org grace period
        org_grace = UserSubscription.objects.filter(
            organization=organization,
            status=UserSubscription.Status.ACTIVE,
            end_date__gt=grace_cutoff,
            end_date__lte=now,
        ).first()

        if org_grace:
            days_expired = (now - org_grace.end_date).days
            return {
                "has_subscription": False,
                "type": "organization",
                "subscription": org_grace,
                "in_grace_period": True,
                "days_in_grace_period": days_expired,
                "grace_days_remaining": GRACE_PERIOD_DAYS - days_expired,
            }

    return {
        "has_subscription": False,
        "type": None,
        "subscription": None,
        "in_grace_period": False,
    }


class HasActiveSubscription(BasePermission):
    """
    Allow access only if user has an active subscription.
    - Unauthenticated -> False
    - Admin-like (TASC_ADMIN, LMS_MANAGER) or Instructor -> True (bypass)
    - Else -> user must have active UserSubscription (with grace period)
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if is_admin_like(request.user) or is_instructor(request.user):
            return True
        if user_has_active_subscription(request.user):
            return True
        org = getattr(request.user, 'organization', None)
        if org and organization_has_active_subscription(org):
            return True
        return False
