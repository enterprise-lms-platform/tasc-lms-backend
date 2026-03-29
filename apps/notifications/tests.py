from unittest.mock import patch
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.notifications.services import send_tasc_email
from apps.notifications.models import Notification

User = get_user_model()


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

class NotificationViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notifuser",
            email="notif@example.com",
            password="testpass123",
            email_verified=True,
            is_active=True,
        )
        self.client.force_authenticate(user=self.user)
        
        now = timezone.now()
        
        # Create notifications spaced out in time
        n1 = Notification.objects.create(user=self.user, title="Oldest", message="5 days ago")
        n1.created_at = now - timedelta(days=5)
        n1.save()
        
        n2 = Notification.objects.create(user=self.user, title="Middle", message="2 days ago")
        n2.created_at = now - timedelta(days=2)
        n2.save()
        
        n3 = Notification.objects.create(user=self.user, title="Newest", message="now")
        n3.created_at = now
        n3.save()
        
        self.n1, self.n2, self.n3 = n1, n2, n3

    def test_notification_date_filters(self):
        now = timezone.now()
        
        # Test created_after (should get Middle and Newest)
        after_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        response = self.client.get(f"/api/v1/notifications/?created_after={after_date}")
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(len(results), 2)
        titles = [r['title'] for r in results]
        self.assertIn("Middle", titles)
        self.assertIn("Newest", titles)
        
        # Test created_before (should get Oldest and Middle)
        before_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        response = self.client.get(f"/api/v1/notifications/?created_before={before_date}")
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(len(results), 2)
        titles = [r['title'] for r in results]
        self.assertIn("Oldest", titles)
        self.assertIn("Middle", titles)

    def test_bulk_delete(self):
        # We start with 3 notifications
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 3)
        
        # Delete n1 and n3
        data = {"ids": [self.n1.id, self.n3.id]}
        response = self.client.post("/api/v1/notifications/bulk-delete/", data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['deleted'], 2)
        
        # Should only have n2 left
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
        remaining = Notification.objects.get(user=self.user)
        self.assertEqual(remaining.id, self.n2.id)
