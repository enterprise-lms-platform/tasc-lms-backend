import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class PolicyAwareMinimumLengthValidator:
    """
    Minimum length validator that reads from the security policy cache,
    falling back to the configured default.
    """

    def __init__(self, min_length=8):
        self.min_length = min_length

    def _effective_min(self):
        try:
            from django.core.cache import cache
            policy = cache.get('system:security_policy', {})
            return int(policy.get('min_password_length') or self.min_length)
        except Exception:
            return self.min_length

    def validate(self, password, user=None):
        min_len = self._effective_min()
        if len(password) < min_len:
            raise ValidationError(
                _("This password is too short. It must contain at least %(min_length)d characters."),
                code='password_too_short',
                params={'min_length': min_len},
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least %(min_length)d characters."
        ) % {'min_length': self._effective_min()}


class PasswordComplexityValidator:
    """
    Enforce uppercase, lowercase, digit, and special character requirements.
    """

    def validate(self, password, user=None):
        errors = []

        if not re.search(r"[A-Z]", password or ""):
            errors.append(_("Password must contain at least one uppercase letter."))
        if not re.search(r"[a-z]", password or ""):
            errors.append(_("Password must contain at least one lowercase letter."))
        if not re.search(r"\d", password or ""):
            errors.append(_("Password must contain at least one number."))
        if not re.search(r"[^A-Za-z0-9]", password or ""):
            errors.append(_("Password must contain at least one special character."))

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must contain at least one uppercase letter, one lowercase letter, one number, and one special character."
        )
