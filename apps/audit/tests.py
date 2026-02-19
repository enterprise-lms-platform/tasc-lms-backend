"""Tests for audit log API and login instrumentation."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, Organization
from apps.audit.models import AuditLog

User = get_user_model()


def _auth_header(user):
    token = RefreshToken.for_user(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token.access_token}"}


class AuditLogAPITests(TestCase):
    """Tests for audit log list endpoint permissions and scoping."""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/superadmin/audit-logs/"

    def test_tasc_admin_can_list_logs(self):
        """tasc_admin can list all audit logs."""
        admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="pass",
            role="tasc_admin",
            email_verified=True,
            is_active=True,
        )
        AuditLog.objects.create(
            actor=admin_user,
            actor_name="Admin",
            actor_email="admin@example.com",
            action=AuditLog.Action.LOGIN,
            resource=AuditLog.Resource.USER,
            details="Test log",
        )
        response = self.client.get(self.url, **_auth_header(admin_user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 1)

    def test_org_admin_only_sees_their_org_logs(self):
        """org_admin sees only logs for organizations they belong to."""
        org1 = Organization.objects.create(name="Org One", slug="org-one")
        org2 = Organization.objects.create(name="Org Two", slug="org-two")

        org_admin_user = User.objects.create_user(
            username="orgadmin",
            email="orgadmin@example.com",
            password="pass",
            role="org_admin",
            email_verified=True,
            is_active=True,
        )
        Membership.objects.create(user=org_admin_user, organization=org1, is_active=True)

        # Log in org1 (visible to org_admin)
        AuditLog.objects.create(
            actor=org_admin_user,
            actor_name="Org Admin",
            actor_email="orgadmin@example.com",
            action=AuditLog.Action.LOGIN,
            resource=AuditLog.Resource.USER,
            details="Login in org1",
            organization=org1,
        )
        # Log in org2 (not visible - org_admin not member)
        AuditLog.objects.create(
            actor=None,
            actor_name="Other",
            actor_email="other@example.com",
            action=AuditLog.Action.CREATED,
            resource=AuditLog.Resource.ORGANIZATION,
            details="Created org2",
            organization=org2,
        )

        response = self.client.get(self.url, **_auth_header(org_admin_user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["details"], "Login in org1")

    def test_finance_only_sees_payment_logs(self):
        """finance role sees only resource=payment logs."""
        finance_user = User.objects.create_user(
            username="finance",
            email="finance@example.com",
            password="pass",
            role="finance",
            email_verified=True,
            is_active=True,
        )

        AuditLog.objects.create(
            actor=finance_user,
            actor_name="Finance",
            actor_email="finance@example.com",
            action=AuditLog.Action.CREATED,
            resource=AuditLog.Resource.PAYMENT,
            details="Payment created",
        )
        AuditLog.objects.create(
            actor=finance_user,
            actor_name="Finance",
            actor_email="finance@example.com",
            action=AuditLog.Action.LOGIN,
            resource=AuditLog.Resource.USER,
            details="User login",
        )

        response = self.client.get(self.url, **_auth_header(finance_user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource"], "Payment")

    def test_learner_denied(self):
        """learner role cannot access audit logs."""
        learner = User.objects.create_user(
            username="learner",
            email="learner@example.com",
            password="pass",
            role="learner",
            email_verified=True,
            is_active=True,
        )
        response = self.client.get(self.url, **_auth_header(learner))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LoginAuditLogTests(TestCase):
    """Test that verify-otp success creates an AuditLog entry."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="otpaudit",
            email="otpaudit@example.com",
            password="testpass123",
            first_name="OTP",
            last_name="Audit",
            email_verified=True,
            is_active=True,
        )
        self.login_url = "/api/v1/auth/login/"
        self.verify_url = "/api/v1/auth/login/verify-otp/"

    def _get_challenge_and_otp(self, mock_send_otp):
        """Login with password, return challenge_id and OTP. Pass mock from test."""
        resp = self.client.post(
            self.login_url,
            {"email": "otpaudit@example.com", "password": "testpass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        challenge_id = resp.data["challenge_id"]
        otp = mock_send_otp.call_args[0][1]
        return challenge_id, otp

    @patch("apps.accounts.auth_views.send_login_otp_email")
    def test_verify_otp_success_creates_login_audit_log(self, mock_send_otp):
        """Successful OTP verification creates a login AuditLog with actor and details."""
        challenge_id, otp = self._get_challenge_and_otp(mock_send_otp)

        response = self.client.post(
            self.verify_url,
            {"challenge_id": challenge_id, "otp": otp},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        logs = AuditLog.objects.filter(actor=self.user, action=AuditLog.Action.LOGIN)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.resource, AuditLog.Resource.USER)
        self.assertIn("Logged in", log.details)
        self.assertEqual(log.actor_email, "otpaudit@example.com")

    @patch("apps.accounts.auth_views.send_login_otp_email")
    def test_verify_otp_success_captures_ip_from_request(self, mock_send_otp):
        """Login audit log captures IP from X-Forwarded-For or REMOTE_ADDR."""
        challenge_id, otp = self._get_challenge_and_otp(mock_send_otp)

        # Use a custom client request - we need to ensure META has REMOTE_ADDR
        # APIClient by default may set it. Override with X-Forwarded-For.
        response = self.client.post(
            self.verify_url,
            {"challenge_id": challenge_id, "otp": otp},
            format="json",
            HTTP_X_FORWARDED_FOR="192.168.1.100, 10.0.0.1",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log = AuditLog.objects.get(actor=self.user, action=AuditLog.Action.LOGIN)
        self.assertEqual(log.ip_address, "192.168.1.100")
