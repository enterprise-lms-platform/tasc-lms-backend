"""
Account-related service helpers.
"""

from apps.notifications.services import send_tasc_email


def send_login_otp_email(user, otp: str) -> None:
    """
    Send OTP email for login using existing branded template.
    Uses send_tasc_email; mfa_code.html extends base template.
    """
    send_tasc_email(
        subject="Your TASC LMS login code",
        to=[user.email],
        template="emails/auth/mfa_code.html",
        context={"user": user, "otp": otp},
    )
