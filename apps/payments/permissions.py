"""Permissions for subscription-gated content access."""

from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import BasePermission

from apps.accounts.rbac import is_admin_like, is_instructor
from .models import UserSubscription


def user_has_active_subscription(user):
    """
    Check if user has an active UserSubscription.
    Uses is_active logic: status=='active' and end_date is null or in the future.
    """
    if not user or not user.is_authenticated:
        return False
    return UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.Status.ACTIVE,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gt=timezone.now())
    ).exists()


def get_best_active_subscription(user):
    """
    Return the best active UserSubscription for the user, or None.
    Selection: prefer end_date null (never expires), else latest end_date.
    """
    if not user or not user.is_authenticated:
        return None
    qs = UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.Status.ACTIVE,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gt=timezone.now())
    ).select_related('subscription')
    # Prefer null end_date, then order by end_date descending
    with_null = qs.filter(end_date__isnull=True).first()
    if with_null:
        return with_null
    return qs.filter(end_date__isnull=False).order_by('-end_date').first()


class HasActiveSubscription(BasePermission):
    """
    Allow access only if user has an active subscription.
    - Unauthenticated -> False
    - Admin-like (TASC_ADMIN, LMS_MANAGER) or Instructor -> True (bypass)
    - Else -> user must have active UserSubscription
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if is_admin_like(request.user) or is_instructor(request.user):
            return True
        return user_has_active_subscription(request.user)
