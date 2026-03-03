"""
Account-related service helpers.
"""

import logging

from apps.notifications.services import send_tasc_email

logger = logging.getLogger(__name__)


def send_login_otp_email(user, otp: str) -> None:
    """
    Send OTP email for login using existing branded template.
    Uses send_tasc_email; mfa_code.html extends base template.
    """
    try:
        send_tasc_email(
            subject="Your TASC LMS login code",
            to=[user.email],
            template="emails/auth/mfa_code.html",
            context={"user": user, "otp": otp},
            raise_on_error=True,
        )
    except Exception:
        logger.exception(
            "Failed to send login OTP email",
            extra={"user_id": getattr(user, "id", None), "email": user.email},
        )
        raise
