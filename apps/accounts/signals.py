from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone


@receiver(user_logged_in)
def create_user_session(sender, request, user, **kwargs):
    """
    Create a UserSession record when user logs in.
    """
    try:
        from .models import UserSession

        # Get session key from Django session
        session_key = request.session.session_key

        if not session_key:
            request.session.create()
            session_key = request.session.session_key

        # Get IP address from request
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR")

        # Get user agent
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # Determine device info
        device_info = {
            "browser": "unknown",
            "os": "unknown",
            "is_mobile": False,
        }

        # Basic user agent parsing
        if user_agent:
            if "Mobile" in user_agent:
                device_info["is_mobile"] = True
            if "Chrome" in user_agent:
                device_info["browser"] = "Chrome"
            elif "Firefox" in user_agent:
                device_info["browser"] = "Firefox"
            elif "Safari" in user_agent:
                device_info["browser"] = "Safari"

        # Create session record
        UserSession.objects.create(
            user=user,
            session_key=session_key,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=device_info,
            is_active=True,
        )
    except Exception as e:
        import logging

        logging.warning(f"Failed to create user session for {user.email}: {e}")

    try:
        from apps.learning.badge_engine import check_and_award_badges
        check_and_award_badges(user, criteria_types=['login_streak'])
    except Exception as e:
        import logging
        logging.warning(f"Failed to check login streak badge for {user.email}: {e}")
