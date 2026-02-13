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
) -> None:
    """
    Sends an email using SendGrid Web API (HTTPS) to avoid SMTP port blocks (465/587).
    Falls back to Django EmailMultiAlternatives (uses EMAIL_BACKEND) only if SendGrid is not configured.

    Controlled by:
      - settings.DJANGO_EMAIL_ENABLED / env DJANGO_EMAIL_ENABLED (true/false)
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

    sendgrid_key = (
        getattr(settings, "SENDGRID_API_KEY", None)
        or os.getenv("SENDGRID_API_KEY")
        or ""
    )

    # Prefer SendGrid API if available
    if sendgrid_key:
        try:
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
        except Exception:
            # Don't break auth flows, but log so we can debug staging easily.
            logger.exception(
                "SendGrid email send failed",
                extra={"to": to, "template": template},
            )
            return

    # Fallback (SMTP or whatever EMAIL_BACKEND is configured)
    try:
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
            "Django email send failed",
            extra={"to": to, "template": template},
        )
        return
