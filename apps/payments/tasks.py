from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@shared_task
def check_and_notify_expiring_subscriptions():
    from apps.notifications.services import (
        check_and_notify_expiring_subscriptions as _check,
    )

    _check()


@shared_task
def expire_overdue_subscriptions():
    from apps.payments.models import UserSubscription
    from apps.payments.permissions import GRACE_PERIOD_DAYS

    now = timezone.now()
    grace_cutoff = now - __import__('datetime').timedelta(days=GRACE_PERIOD_DAYS)
    expired = UserSubscription.objects.filter(
        status=UserSubscription.Status.ACTIVE,
        end_date__isnull=False,
        end_date__lte=grace_cutoff,
    )
    count = expired.update(status=UserSubscription.Status.EXPIRED)

    # Revoke active enrollments for users whose subscriptions just expired
    try:
        from apps.learning.models import Enrollment
        from django.contrib.auth import get_user_model
        User = get_user_model()
        expired_user_ids = set(expired.values_list('user_id', flat=True))
        if expired_user_ids:
            Enrollment.objects.filter(
                user_id__in=expired_user_ids,
                status=Enrollment.Status.ACTIVE,
            ).update(status=Enrollment.Status.EXPIRED)
    except Exception:
        logger.warning("Failed to revoke enrollments on subscription expiry", exc_info=True)

    # Invalidate certificates for expired enrollments
    try:
        from apps.learning.models import Certificate
        Certificate.objects.filter(
            enrollment__status=Enrollment.Status.EXPIRED,
            is_valid=True,
        ).update(is_valid=False)
    except Exception:
        logger.warning("Failed to invalidate certificates on subscription expiry", exc_info=True)

    # Notify individual learners whose org subscriptions expired
    try:
        from apps.notifications.services import send_learner_org_subscription_expired
        org_ids = set(expired.values_list('organization_id', flat=True))
        from apps.accounts.models import Organization
        for org_id in org_ids:
            if org_id:
                org = Organization.objects.get(pk=org_id)
                send_learner_org_subscription_expired(org)
                try:
                    from apps.notifications.services import send_subscription_expired_notification
                    send_subscription_expired_notification(org)
                except Exception:
                    logger.warning("Failed to send subscription expired notification for org %s", org_id, exc_info=True)
    except Exception:
        logger.warning("Failed to notify learners of org subscription expiry", exc_info=True)

    return count


@shared_task
def reconcile_stale_pesapal_payments():
    """
    Background task to reconcile stuck pending Pesapal payments.
    Iterates over all pending Pesapal payments older than 15 minutes
    and checks their status with Pesapal.
    """
    from apps.payments.models import Payment
    from apps.payments.views_pesapal import _reconcile_stale_subscription_checkouts_for_user
    from django.contrib.auth import get_user_model

    User = get_user_model()
    cutoff = timezone.now() - __import__('datetime').timedelta(minutes=15)

    pending_user_ids = (
        Payment.objects.filter(
            status="pending",
            payment_method="pesapal",
            created_at__lt=cutoff,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )

    reconciled = 0
    for user_id in pending_user_ids:
        try:
            user = User.objects.get(pk=user_id)
            _reconcile_stale_subscription_checkouts_for_user(user)
            reconciled += 1
        except Exception:
            logger.warning("Reconciliation failed for user %s", user_id, exc_info=True)

    logger.info("Reconciled stale Pesapal payments for %d users", reconciled)
    return reconciled


@shared_task
def check_seat_capacity():
    """
    Check organizations approaching seat capacity and notify admins.
    Triggers at 80% and 100% thresholds.
    """
    from apps.accounts.models import Organization, Membership
    from apps.notifications.services import send_seat_capacity_warning

    orgs = Organization.objects.filter(is_active=True, max_seats__isnull=False)
    notified = 0
    for org in orgs:
        used = Membership.objects.filter(
            organization=org, is_active=True
        ).count()
        if org.max_seats and org.max_seats > 0:
            percent = (used / org.max_seats) * 100
            if percent >= 80:
                try:
                    send_seat_capacity_warning(org, percent)
                    notified += 1
                except Exception:
                    logger.warning(
                        "Seat capacity notification failed for org %s",
                        org.id, exc_info=True,
                    )
    logger.info("Seat capacity warnings sent for %d organizations", notified)
    return notified
