from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

PRESIGN_URL = "/api/v1/uploads/presign/"


def _auth_headers(user):
    token = RefreshToken.for_user(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token.access_token}"}


@override_settings(
    DO_SPACES_REGION="lon1",
    DO_SPACES_BUCKET="tasc-public",
    DO_SPACES_ENDPOINT="https://lon1.digitaloceanspaces.com",
    DO_SPACES_ACCESS_KEY_ID="key",
    DO_SPACES_SECRET_ACCESS_KEY="secret",
    DO_SPACES_CDN_BASE_URL="https://tasc-public.lon1.cdn.digitaloceanspaces.com",
    DO_SPACES_PRESIGN_EXPIRY_SECONDS=300,
)
class UploadPresignApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="upload-tester",
            email="upload-tester@example.com",
            password="pass1234",
            role="instructor",
            email_verified=True,
            is_active=True,
        )
        self.auth = _auth_headers(self.user)

    @patch("apps.common.views.create_boto3_client")
    def test_presign_returns_upload_and_public_urls(self, mock_factory):
        mock_client = mock_factory.return_value
        mock_client.generate_presigned_url.return_value = "https://signed.example/upload"

        payload = {
            "prefix": "course-thumbnails",
            "filename": "my unsafe file name.png",
            "content_type": "image/png",
        }
        response = self.client.post(PRESIGN_URL, payload, format="json", **self.auth)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("upload_url", response.data)
        self.assertIn("public_url", response.data)
        self.assertEqual(response.data["method"], "PUT")
        self.assertEqual(response.data["headers"]["Content-Type"], "image/png")
        self.assertTrue(response.data["public_url"].startswith("https://tasc-public.lon1.cdn.digitaloceanspaces.com/course-thumbnails/"))

        mock_client.generate_presigned_url.assert_called_once()
        call_kwargs = mock_client.generate_presigned_url.call_args.kwargs
        self.assertEqual(call_kwargs["HttpMethod"], "PUT")
        self.assertEqual(call_kwargs["Params"]["Bucket"], "tasc-public")
        self.assertEqual(call_kwargs["Params"]["ContentType"], "image/png")

    def test_presign_rejects_invalid_prefix_and_content_type(self):
        bad_prefix = self.client.post(
            PRESIGN_URL,
            {
                "prefix": "avatars",
                "filename": "test.png",
                "content_type": "image/png",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(bad_prefix.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("prefix", bad_prefix.data)

        bad_content_type = self.client.post(
            PRESIGN_URL,
            {
                "prefix": "course-banners",
                "filename": "test.gif",
                "content_type": "image/gif",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(bad_content_type.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content_type", bad_content_type.data)


class SwaggerRedirectRoutingTests(APITestCase):
    def test_invalid_non_api_non_admin_path_redirects_to_documentation(self):
        response = self.client.get("/this-does-not-exist", follow=False)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.headers.get("Location"), "/documentation/")

    def test_invalid_api_path_returns_404_without_documentation_redirect(self):
        response = self.client.get("/api/v1/this-does-not-exist", follow=False)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_path_is_not_redirected_to_documentation(self):
        response = self.client.get("/admin/this-does-not-exist", follow=False)
        if response.status_code in {301, 302, 307, 308}:
            self.assertNotEqual(response.headers.get("Location"), "/documentation/")
        else:
            self.assertIn(response.status_code, {status.HTTP_404_NOT_FOUND, status.HTTP_200_OK})
