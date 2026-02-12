from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class MeEndpointTests(TestCase):
    """Tests for GET /api/v1/auth/me/"""

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

    def test_unauthenticated_returns_401(self):
        """me endpoint must reject unauthenticated requests."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        """me endpoint returns profile for authenticated user."""
        response = self.client.get(self.url, **self._auth_header())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)

    def test_response_excludes_is_staff(self):
        """is_staff must NOT be present in the response."""
        response = self.client.get(self.url, **self._auth_header())
        self.assertNotIn("is_staff", response.data)

    def test_response_excludes_is_superuser(self):
        """is_superuser must NOT be present in the response."""
        response = self.client.get(self.url, **self._auth_header())
        self.assertNotIn("is_superuser", response.data)

    def test_response_includes_expected_fields(self):
        """me endpoint returns the expected set of fields."""
        response = self.client.get(self.url, **self._auth_header())
        expected_fields = {
            "id", "name", "email", "username", "first_name", "last_name",
            "phone_number", "country", "timezone", "role", "google_picture",
            "marketing_opt_in", "terms_accepted_at", "email_verified", "is_active",
        }
        self.assertEqual(set(response.data.keys()), expected_fields)


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

    def test_no_email_password_in_request_body(self):
        """Endpoint must NOT accept or require email/password fields."""
        # Even if email+password are sent, they should be ignored.
        # The endpoint should work with just id_token + auth header.
        with patch("apps.accounts.google_auth_views.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "sub": "another-google-id",
                    "picture": None,
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
