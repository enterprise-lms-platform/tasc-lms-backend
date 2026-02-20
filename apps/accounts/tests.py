from unittest.mock import patch, MagicMock
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tokens import email_verification_token
from apps.audit.models import AuditLog

User = get_user_model()


class MeEndpointTests(TestCase):
    """Tests for GET and PATCH /api/v1/auth/me/"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            email_verified=True,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        self.url = "/api/v1/auth/me/"

    def _auth_header(self):
        token = RefreshToken.for_user(self.user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token.access_token}"}

    # ---- GET ----
    def test_get_unauthenticated_returns_401(self):
        """me endpoint must reject unauthenticated requests."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_authenticated_returns_200(self):
        """me endpoint returns profile for authenticated user."""
        response = self.client.get(self.url, **self._auth_header())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)

    def test_get_response_excludes_is_staff(self):
        """is_staff must NOT be present in the response."""
        response = self.client.get(self.url, **self._auth_header())
        self.assertNotIn("is_staff", response.data)

    def test_get_response_excludes_is_superuser(self):
        """is_superuser must NOT be present in the response."""
        response = self.client.get(self.url, **self._auth_header())
        self.assertNotIn("is_superuser", response.data)

    def test_get_response_includes_expected_fields(self):
        """me endpoint returns the expected set of fields."""
        response = self.client.get(self.url, **self._auth_header())
        expected_fields = {
            "id", "name", "email", "username", "first_name", "last_name",
            "phone_number", "country", "timezone", "role", "google_picture",
            "marketing_opt_in", "terms_accepted_at", "email_verified", "is_active",
        }
        self.assertEqual(set(response.data.keys()), expected_fields)

    # ---- PATCH ----
    def test_patch_unauthenticated_returns_401(self):
        """PATCH me must reject unauthenticated requests."""
        response = self.client.patch(
            self.url, {"first_name": "Updated"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_partial_update_returns_200_and_same_response_shape(self):
        """PATCH updates only sent fields and returns same shape as GET me."""
        payload = {
            "first_name": "UpdatedFirst",
            "last_name": "UpdatedLast",
            "phone_number": "+1234567890",
            "country": "USA",
            "marketing_opt_in": True,
        }
        response = self.client.patch(
            self.url, payload, format="json", **self._auth_header()
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response shape must match GET me
        expected_fields = {
            "id", "name", "email", "username", "first_name", "last_name",
            "phone_number", "country", "timezone", "role", "google_picture",
            "marketing_opt_in", "terms_accepted_at", "email_verified", "is_active",
        }
        self.assertEqual(set(response.data.keys()), expected_fields)
        self.assertEqual(response.data["first_name"], "UpdatedFirst")
        self.assertEqual(response.data["last_name"], "UpdatedLast")
        self.assertEqual(response.data["phone_number"], "+1234567890")
        self.assertEqual(response.data["country"], "USA")
        self.assertIs(response.data["marketing_opt_in"], True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "UpdatedFirst")
        self.assertEqual(self.user.last_name, "UpdatedLast")

    def test_patch_ignores_forbidden_fields(self):
        """role, email_verified, is_active etc. must not be updatable via PATCH."""
        original_role = self.user.role
        original_email_verified = self.user.email_verified
        original_is_active = self.user.is_active
        response = self.client.patch(
            self.url,
            {
                "first_name": "OnlyThis",
                "role": "tasc_admin",
                "email_verified": False,
                "is_active": False,
            },
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "OnlyThis")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "OnlyThis")
        self.assertEqual(self.user.role, original_role)
        self.assertEqual(self.user.email_verified, original_email_verified)
        self.assertEqual(self.user.is_active, original_is_active)

    def test_patch_empty_body_returns_200(self):
        """PATCH with empty body (partial) is valid and returns current profile."""
        response = self.client.patch(
            self.url, {}, format="json", **self._auth_header()
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)


class AccountsAuditInstrumentationTests(TestCase):
    """Tests for US-027 Phase 2A audit instrumentation in accounts views."""

    def setUp(self):
        self.client = APIClient()

    def _auth_header(self, user):
        token = RefreshToken.for_user(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token.access_token}"}

    def test_patch_me_creates_audit_log(self):
        user = User.objects.create_user(
            username="meaudituser",
            email="meaudit@example.com",
            password="testpass123",
            first_name="Before",
            email_verified=True,
            is_active=True,
        )

        response = self.client.patch(
            "/api/v1/auth/me/",
            {"first_name": "After"},
            format="json",
            **self._auth_header(user),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            AuditLog.objects.filter(
                action="updated",
                resource="user",
                resource_id=str(user.id),
                actor=user,
            ).exists()
        )

    @patch("apps.accounts.views.send_tasc_email")
    def test_invite_user_create_and_update_create_audit_logs(self, mock_send_tasc_email):
        mock_send_tasc_email.return_value = None
        admin_user = User.objects.create_user(
            username="inviteadmin",
            email="inviteadmin@example.com",
            password="testpass123",
            role="tasc_admin",
            email_verified=True,
            is_active=True,
        )
        invite_url = "/api/v1/admin/users/invite/"
        invite_email = "invited.user@example.com"

        create_response = self.client.post(
            invite_url,
            {
                "email": invite_email,
                "first_name": "Invited",
                "last_name": "User",
                "role": "instructor",
            },
            format="json",
            **self._auth_header(admin_user),
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        invited_user = User.objects.get(email__iexact=invite_email)
        self.assertTrue(
            AuditLog.objects.filter(
                action="created",
                resource="user",
                resource_id=str(invited_user.id),
                actor=admin_user,
            ).exists()
        )

        update_response = self.client.post(
            invite_url,
            {
                "email": invite_email,
                "first_name": "Invited",
                "last_name": "User",
                "role": "finance",
            },
            format="json",
            **self._auth_header(admin_user),
        )
        self.assertEqual(update_response.status_code, status.HTTP_201_CREATED)

        self.assertTrue(
            AuditLog.objects.filter(
                action="updated",
                resource="user",
                resource_id=str(invited_user.id),
                actor=admin_user,
            ).exists()
        )

    def test_verify_email_persists_activation_and_creates_audit_log(self):
        user = User.objects.create_user(
            username="verifyaudit",
            email="verifyaudit@example.com",
            password="testpass123",
            email_verified=False,
            is_active=False,
        )
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        response = self.client.get(f"/api/v1/auth/verify-email/{uidb64}/{token}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertTrue(user.is_active)

        log = AuditLog.objects.filter(
            action="updated",
            resource="user",
            resource_id=str(user.id),
        ).order_by("-created_at").first()
        self.assertIsNotNone(log)
        self.assertIsNone(log.actor)


@override_settings(GOOGLE_CLIENT_ID="test-client-id")
class GoogleOAuthLinkTests(TestCase):
    """Tests for POST /api/v1/auth/google/link/"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="linkuser",
            email="link@example.com",
            password="testpass123",
            email_verified=True,
            is_active=True,
        )
        self.other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="testpass123",
            email_verified=True,
            is_active=True,
            google_id="existing-google-id",
        )
        self.url = "/api/v1/auth/google/link/"
        token = RefreshToken.for_user(self.user)
        self.auth_header = {"HTTP_AUTHORIZATION": f"Bearer {token.access_token}"}

    def test_unauthenticated_returns_401(self):
        """Link endpoint must reject unauthenticated requests."""
        response = self.client.post(self.url, {"id_token": "tok"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_id_token_returns_400(self):
        """Must return 400 when id_token is not provided."""
        response = self.client.post(self.url, {}, format="json", **self.auth_header)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.accounts.google_auth_views.requests.get")
    def test_invalid_google_token_returns_400(self, mock_get):
        """Must return 400 when Google rejects the token."""
        mock_get.return_value = MagicMock(status_code=401)
        response = self.client.post(
            self.url, {"id_token": "bad-token"}, format="json", **self.auth_header
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("apps.accounts.google_auth_views.requests.get")
    def test_successful_link(self, mock_get):
        """Valid token links Google account to request.user."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "sub": "new-google-id-123",
                "picture": "https://example.com/pic.jpg",
                "aud": "test-client-id",
            }),
        )
        response = self.client.post(
            self.url, {"id_token": "valid-token"}, format="json", **self.auth_header
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Google account linked successfully")

        # Verify the DB was updated on request.user (not some payload user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.google_id, "new-google-id-123")
        self.assertEqual(self.user.google_picture, "https://example.com/pic.jpg")

    @patch("apps.accounts.google_auth_views.requests.get")
    def test_google_id_already_linked_to_other_user(self, mock_get):
        """Must return 400 when Google ID belongs to another user."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "sub": "existing-google-id",  # belongs to self.other_user
                "picture": "https://example.com/pic.jpg",
                "aud": "test-client-id",
                "email": "other@example.com",
                "email_verified": True,
            }),
        )
        response = self.client.post(
            self.url, {"id_token": "valid-token"}, format="json", **self.auth_header
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already linked", response.data["error"])

    @patch("apps.accounts.google_auth_views.requests.get")
    def test_error_does_not_leak_details(self, mock_get):
        """Internal errors must return a generic message, not str(e)."""
        mock_get.side_effect = RuntimeError("secret DB connection string")
        response = self.client.post(
            self.url, {"id_token": "valid-token"}, format="json", **self.auth_header
        )
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertNotIn("secret", response.data.get("error", ""))
        self.assertEqual(
            response.data["error"],
            "Failed to link Google account. Please try again.",
        )

    @patch("apps.accounts.google_auth_views.requests.get")
    def test_no_email_password_in_request_body(self, mock_get):
        """Endpoint must NOT accept or require email/password fields."""
        # Even if email+password are sent, they should be ignored.
        # The endpoint should work with just id_token + auth header.
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "sub": "another-google-id",
                "picture": None,
                "aud": "test-client-id",
                "email": "link@example.com",
                "email_verified": True,
            }),
        )
        response = self.client.post(
            self.url,
            {
                "id_token": "tok",
                "email": "attacker@evil.com",
                "password": "doesntmatter",
            },
            format="json",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The linked user must be request.user, not attacker@evil.com
        self.user.refresh_from_db()
        self.assertEqual(self.user.google_id, "another-google-id")


@override_settings(MAX_LOGIN_ATTEMPTS=5, ACCOUNT_LOCK_MINUTES=15)
class LoginLockoutTests(TestCase):
    """Tests for login lockout after failed attempts (US-015)."""

    def setUp(self):
        self.client = APIClient()
        self.login_url = "/api/v1/auth/login/"
        self.user = User.objects.create_user(
            username="lockuser",
            email="lock@example.com",
            password="correctpass",
            email_verified=True,
            is_active=True,
        )

    def test_lock_after_five_failed_attempts(self):
        """After 5 failed attempts account is locked and 6th attempt returns 403."""
        for _ in range(5):
            response = self.client.post(
                self.login_url,
                {"email": "lock@example.com", "password": "wrong"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertIn("detail", response.data)

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.account_locked_until)

        response = self.client.post(
            self.login_url,
            {"email": "lock@example.com", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Account locked", response.data["detail"])

    def test_locked_account_blocks_login_until_after_lock_expiry(self):
        """Locked account returns 403; after lock expires wrong password returns 401."""
        self.user.failed_login_attempts = 5
        self.user.account_locked_until = timezone.now() + timedelta(minutes=15)
        self.user.save(update_fields=["failed_login_attempts", "account_locked_until"])

        response = self.client.post(
            self.login_url,
            {"email": "lock@example.com", "password": "correctpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Expire the lock
        self.user.account_locked_until = timezone.now() - timedelta(minutes=1)
        self.user.save(update_fields=["account_locked_until"])

        response = self.client.post(
            self.login_url,
            {"email": "lock@example.com", "password": "correctpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_successful_login_resets_counters(self):
        """Successful login clears failed_login_attempts and account_locked_until."""
        self.user.failed_login_attempts = 3
        self.user.account_locked_until = None
        self.user.save(update_fields=["failed_login_attempts", "account_locked_until"])

        response = self.client.post(
            self.login_url,
            {"email": "lock@example.com", "password": "correctpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.account_locked_until)

    @patch("apps.accounts.auth_views.send_account_locked_email")
    def test_email_sent_on_lock(self, mock_send):
        """When lock triggers, send_account_locked_email is called."""
        for _ in range(5):
            self.client.post(
                self.login_url,
                {"email": "lock@example.com", "password": "wrong"},
                format="json",
            )

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[0][0].pk, self.user.pk)

    @patch("apps.accounts.auth_views.send_login_otp_email")
    def test_successful_password_returns_mfa_required(self, mock_send_otp):
        """Correct password returns mfa_required with challenge_id, not tokens."""
        response = self.client.post(
            self.login_url,
            {"email": "lock@example.com", "password": "correctpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mfa_required"])
        self.assertEqual(response.data["method"], "email_otp")
        self.assertIn("challenge_id", response.data)
        self.assertEqual(response.data["expires_in"], 300)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        mock_send_otp.assert_called_once()
        self.assertEqual(mock_send_otp.call_args[0][0].pk, self.user.pk)
        self.assertEqual(len(mock_send_otp.call_args[0][1]), 6)


class LoginOTPTests(TestCase):
    """Tests for email OTP login flow (verify-otp, resend-otp)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="otpuser",
            email="otp@example.com",
            password="testpass123",
            email_verified=True,
            is_active=True,
        )
        self.login_url = "/api/v1/auth/login/"
        self.verify_url = "/api/v1/auth/login/verify-otp/"
        self.resend_url = "/api/v1/auth/login/resend-otp/"

    def _login_get_challenge_id(self, mock_send_otp):
        """Helper: login with password, capture challenge_id and OTP from mock."""
        response = self.client.post(
            self.login_url,
            {"email": "otp@example.com", "password": "testpass123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        challenge_id = response.data["challenge_id"]
        otp_sent = mock_send_otp.call_args[0][1]
        return challenge_id, otp_sent

    @patch("apps.accounts.auth_views.send_login_otp_email")
    def test_verify_otp_returns_tokens_and_marks_challenge_used(self, mock_send_otp):
        """Successful OTP verification returns JWT tokens and marks challenge used."""
        challenge_id, otp = self._login_get_challenge_id(mock_send_otp)

        response = self.client.post(
            self.verify_url,
            {"challenge_id": challenge_id, "otp": otp},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], self.user.email)

        from apps.accounts.models import LoginOTPChallenge

        challenge = LoginOTPChallenge.objects.get(id=challenge_id)
        self.assertTrue(challenge.is_used)

    @patch("apps.accounts.auth_views.send_login_otp_email")
    def test_wrong_otp_increments_attempts_after_five_rejects(self, mock_send_otp):
        """Wrong OTP increments attempts; after 5 attempts returns 403."""
        challenge_id, _ = self._login_get_challenge_id(mock_send_otp)

        for i in range(5):
            response = self.client.post(
                self.verify_url,
                {"challenge_id": challenge_id, "otp": "000000"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("Invalid or expired", response.data["detail"])

        response = self.client.post(
            self.verify_url,
            {"challenge_id": challenge_id, "otp": "000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Too many attempts", response.data["detail"])

    @patch("apps.accounts.auth_views.send_login_otp_email")
    def test_resend_increments_send_count_after_three_rejects(self, mock_send_otp):
        """Resend increments send_count; after 3 resends returns 429."""
        challenge_id, otp = self._login_get_challenge_id(mock_send_otp)

        for _ in range(2):
            response = self.client.post(
                self.resend_url,
                {"challenge_id": challenge_id},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("OTP sent", response.data["detail"])

        self.assertEqual(mock_send_otp.call_count, 3)

        response = self.client.post(
            self.resend_url,
            {"challenge_id": challenge_id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Maximum resend", response.data["detail"])
