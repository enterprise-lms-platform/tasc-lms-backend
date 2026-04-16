from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_account_locked_email(user) -> None:
    """
    Send branded notification when account is locked after too many failed logins.
    Includes a link to the frontend password reset page.
    """
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
    reset_url = f"{frontend_base}/passwordreset"
    send_tasc_email(
        subject="Account temporarily locked",
        to=[user.email],
        template="emails/auth/account_locked.html",
        context={"user": user, "reset_url": reset_url},
    )


def send_tasc_email(
    *,
    subject: str,
    to: list[str],
    template: str,
    context: dict[str, Any],
    from_email: str | None = None,
    reply_to: str | None = None,
    raise_on_error: bool = False,
) -> None:
    """
    Sends an email using SendGrid Web API (HTTPS) to avoid SMTP port blocks (465/587).
    Falls back to Django EmailMultiAlternatives (uses EMAIL_BACKEND) only if SendGrid is not configured.

    Controlled by:
      - settings.DJANGO_EMAIL_ENABLED / env DJANGO_EMAIL_ENABLED (true/false)
      - settings.EMAIL_PROVIDER / env EMAIL_PROVIDER (console|django|sendgrid|auto)
      - settings.SENDGRID_API_KEY / env SENDGRID_API_KEY
      - settings.EMAIL_SUBJECT_PREFIX (optional)
      - settings.DEFAULT_FROM_EMAIL (optional)
      - settings.SUPPORT_EMAIL (optional)
    """
    enabled = getattr(settings, "DJANGO_EMAIL_ENABLED", True)
    if not enabled:
        return

    # Inject support_email and year for base template
    enriched_context = {
        "support_email": getattr(settings, "SUPPORT_EMAIL", None) or getattr(settings, "DEFAULT_FROM_EMAIL", "support@tasc-lms.com"),
        "year": datetime.now().year,
        **context,
    }

    try:
        html = render_to_string(template, enriched_context)
        text = strip_tags(html)

        subject_prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "") or ""
        full_subject = f"{subject_prefix}{subject}"

        from_addr = (
            from_email
            or getattr(settings, "DEFAULT_FROM_EMAIL", None)
            or "no-reply@example.com"
        )
        support_email = reply_to or getattr(settings, "SUPPORT_EMAIL", None)

        provider = str(getattr(settings, "EMAIL_PROVIDER", "auto")).lower()
        if provider not in {"console", "django", "sendgrid", "auto"}:
            logger.warning(
                "Unknown EMAIL_PROVIDER value; falling back to auto",
                extra={"email_provider": provider},
            )
            provider = "auto"

        if provider == "sendgrid":
            sendgrid_key = getattr(settings, "SENDGRID_API_KEY", None) or ""
            if not sendgrid_key:
                raise RuntimeError(
                    "EMAIL_PROVIDER is 'sendgrid' but SENDGRID_API_KEY is not configured."
                )
        elif provider in {"console", "django"}:
            sendgrid_key = ""
        else:
            sendgrid_key = (
                getattr(settings, "SENDGRID_API_KEY", None)
                or os.getenv("SENDGRID_API_KEY")
                or ""
            )

        # Use SendGrid when selected/available
        if sendgrid_key:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Email, To, Content

            mail = Mail(
                from_email=Email(from_addr),
                to_emails=[To(x) for x in to],
                subject=full_subject,
            )

            # Plain text + HTML
            mail.add_content(Content("text/plain", text))
            mail.add_content(Content("text/html", html))

            if support_email:
                mail.reply_to = Email(support_email)

            sg = SendGridAPIClient(sendgrid_key)
            sg.send(mail)
            return

        # Fallback (SMTP or whatever EMAIL_BACKEND is configured)
        from django.core.mail import EmailMultiAlternatives

        msg = EmailMultiAlternatives(
            subject=full_subject,
            body=text,
            from_email=from_addr,
            to=to,
        )
        if support_email:
            msg.reply_to = [support_email]
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
    except Exception:
        logger.exception(
            "Email send failed",
            extra={"to": to, "template": template},
        )
        if raise_on_error:
            raise
        return


def send_subscription_expiry_warning(organization, days_remaining):
    """Send 30/7 day warning to Org Admin before subscription expires."""
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
    renewal_url = f"{frontend_base}/org-admin/billing"
    
    # Get org admins
    from apps.accounts.models import Membership
    admins = Membership.objects.filter(
        organization=organization,
        role=Membership.Role.ORG_ADMIN,
        is_active=True
    ).select_related('user')
    
    for admin in admins:
        send_tasc_email(
            subject=f"Your TASC LMS subscription expires in {days_remaining} days",
            to=[admin.user.email],
            template="emails/payments/subscription_expiry_warning.html",
            context={
                "organization": organization,
                "admin": admin.user,
                "days_remaining": days_remaining,
                "renewal_url": renewal_url,
            },
        )
        
        # Also create in-app notification
        from apps.notifications.models import Notification
        Notification.objects.create(
            user=admin.user,
            type=Notification.Type.SYSTEM,
            title=f"Subscription expires in {days_remaining} days",
            description=f"Your organization's TASC LMS subscription will expire in {days_remaining} days. Renew now to avoid interruption.",
            link=renewal_url,
        )


def send_subscription_expired_notification(organization):
    """Notify Org Admin when subscription has expired."""
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
    renewal_url = f"{frontend_base}/org-admin/billing"
    
    from apps.accounts.models import Membership
    admins = Membership.objects.filter(
        organization=organization,
        role=Membership.Role.ORG_ADMIN,
        is_active=True
    ).select_related('user')
    
    for admin in admins:
        send_tasc_email(
            subject="Your TASC LMS subscription has expired",
            to=[admin.user.email],
            template="emails/payments/subscription_expired.html",
            context={
                "organization": organization,
                "admin": admin.user,
                "renewal_url": renewal_url,
            },
        )
        
        from apps.notifications.models import Notification
        Notification.objects.create(
            user=admin.user,
            type=Notification.Type.SYSTEM,
            title="Subscription expired",
            description=f"Your organization's TASC LMS subscription has expired. Renew now to restore learner access.",
            link=renewal_url,
        )


def check_and_notify_expiring_subscriptions():
    """Daily task to check for expiring subscriptions and send notifications."""
    from django.utils import timezone
    from datetime import timedelta
    from apps.payments.models import UserSubscription
    
    now = timezone.now()
    
    # Check subscriptions expiring in 30 days
    thirty_days = now + timedelta(days=30)
    subs_30_days = UserSubscription.objects.filter(
        status=UserSubscription.Status.ACTIVE,
        end_date__lte=thirty_days,
        end_date__gt=now,
        organization__isnull=False,
    ).select_related('organization')
    
    for sub in subs_30_days:
        # Check if we already sent 30-day warning (use Notification model to track)
        from apps.notifications.models import Notification
        already_notified = Notification.objects.filter(
            type=Notification.Type.SYSTEM,
            title__icontains="30 days",
            user__memberships__organization=sub.organization,
        ).exists()
        
        if not already_notified and sub.end_date:
            days_remaining = (sub.end_date - now).days
            if days_remaining == 30:
                send_subscription_expiry_warning(sub.organization, 30)
    
    # Check subscriptions expiring in 7 days
    seven_days = now + timedelta(days=7)
    subs_7_days = UserSubscription.objects.filter(
        status=UserSubscription.Status.ACTIVE,
        end_date__lte=seven_days,
        end_date__gt=now,
        organization__isnull=False,
    ).select_related('organization')
    
    for sub in subs_7_days:
        from apps.notifications.models import Notification
        already_notified = Notification.objects.filter(
            type=Notification.Type.SYSTEM,
            title__icontains="7 days",
            user__memberships__organization=sub.organization,
        ).exists()
        
        if not already_notified and sub.end_date:
            days_remaining = (sub.end_date - now).days
            if days_remaining == 7:
                send_subscription_expiry_warning(sub.organization, 7)
