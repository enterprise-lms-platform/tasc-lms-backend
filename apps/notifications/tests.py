from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.notifications.services import send_tasc_email


class SendTascEmailProviderRoutingTests(TestCase):
    @override_settings(
        EMAIL_PROVIDER="console",
        DJANGO_EMAIL_ENABLED=True,
        SENDGRID_API_KEY="",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    @patch.dict("os.environ", {"SENDGRID_API_KEY": "abc"}, clear=False)
    @patch("apps.notifications.services.render_to_string", return_value="<p>Hello</p>")
    @patch("django.core.mail.EmailMultiAlternatives.send", return_value=1)
    def test_console_provider_ignores_env_sendgrid_key_uses_django_backend(
        self, mock_email_send, _mock_render
    ):
        send_tasc_email(
            subject="Test",
            to=["dev@example.com"],
            template="emails/auth/mfa_code.html",
            context={},
        )
        mock_email_send.assert_called_once()

    @override_settings(
        EMAIL_PROVIDER="sendgrid",
        DJANGO_EMAIL_ENABLED=True,
        SENDGRID_API_KEY="",
    )
    @patch("apps.notifications.services.render_to_string", return_value="<p>Hello</p>")
    def test_sendgrid_provider_missing_key_raises_in_strict_mode_and_logs_otherwise(
        self, _mock_render
    ):
        with self.assertRaises(RuntimeError):
            send_tasc_email(
                subject="Strict test",
                to=["dev@example.com"],
                template="emails/auth/mfa_code.html",
                context={},
                raise_on_error=True,
            )

        with self.assertLogs("apps.notifications.services", level="ERROR"):
            send_tasc_email(
                subject="Non-strict test",
                to=["dev@example.com"],
                template="emails/auth/mfa_code.html",
                context={},
                raise_on_error=False,
            )
