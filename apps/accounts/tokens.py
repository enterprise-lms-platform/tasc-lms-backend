from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """
    Dedicated token generator for email verification.
    Overrides _make_hash_value to include a 'ev' salt so tokens are
    semantically distinct from password-reset tokens and cannot be
    cross-used.
    """

    def _make_hash_value(self, user, timestamp):
        # Include email_verified state so the token is invalidated
        # once the email has been verified.
        email_verified = getattr(user, 'email_verified', False)
        return f"ev-{super()._make_hash_value(user, timestamp)}-{email_verified}"


email_verification_token = EmailVerificationTokenGenerator()
