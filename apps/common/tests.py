from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalogue.models import Category, Course, Session

User = get_user_model()

PRESIGN_URL = "/api/v1/uploads/presign/"

PRESIGN_SETTINGS = {
    "DO_SPACES_REGION": "lon1",
    "DO_SPACES_BUCKET": "tasc-public",
    "DO_SPACES_PUBLIC_BUCKET": "tasc-public",
    "DO_SPACES_PRIVATE_BUCKET": "tasc-private",
    "DO_SPACES_ENDPOINT": "https://lon1.digitaloceanspaces.com",
    "DO_SPACES_ACCESS_KEY_ID": "key",
    "DO_SPACES_SECRET_ACCESS_KEY": "secret",
    "DO_SPACES_CDN_BASE_URL": "https://tasc-public.lon1.cdn.digitaloceanspaces.com",
    "DO_SPACES_PRESIGN_EXPIRY_SECONDS": 300,
}


def _auth_headers(user):
    token = RefreshToken.for_user(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token.access_token}"}


@override_settings(**PRESIGN_SETTINGS)
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
        self.assertIn("object_key", response.data)
        self.assertIn("bucket", response.data)
        self.assertIn("expires_in", response.data)
        self.assertEqual(response.data["method"], "PUT")
        self.assertEqual(response.data["headers"]["Content-Type"], "image/png")
        self.assertIn("x-amz-acl", response.data["headers"])
        self.assertTrue(response.data["public_url"].startswith("https://tasc-public.lon1.cdn.digitaloceanspaces.com/course-thumbnails/"))

        mock_client.generate_presigned_url.assert_called_once()
        call_kwargs = mock_client.generate_presigned_url.call_args.kwargs
        self.assertEqual(call_kwargs["HttpMethod"], "PUT")
        self.assertEqual(call_kwargs["Params"]["Bucket"], "tasc-public")
        self.assertEqual(call_kwargs["Params"]["ContentType"], "image/png")
        self.assertIn("ACL", call_kwargs["Params"])

    @patch("apps.common.views.create_boto3_client")
    def test_presign_accepts_avatars_prefix(self, mock_factory):
        mock_client = mock_factory.return_value
        mock_client.generate_presigned_url.return_value = "https://signed.example/upload"

        response = self.client.post(
            PRESIGN_URL,
            {
                "prefix": "avatars",
                "filename": "test.png",
                "content_type": "image/png",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("upload_url", response.data)
        self.assertIn("public_url", response.data)
        self.assertTrue(response.data["public_url"].startswith("https://tasc-public.lon1.cdn.digitaloceanspaces.com/avatars/"))
        self.assertEqual(response.data["headers"]["Content-Type"], "image/png")
        self.assertIn("x-amz-acl", response.data["headers"])

    def test_presign_rejects_invalid_content_type(self):
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

    def test_presign_rejects_invalid_prefix(self):
        bad_prefix = self.client.post(
            PRESIGN_URL,
            {
                "prefix": "malicious-path",
                "filename": "test.png",
                "content_type": "image/png",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(bad_prefix.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("prefix", bad_prefix.data)

    def test_session_assets_rejects_image_content_type(self):
        """session-assets only allows video, PDF, zip - not images."""
        cat = Category.objects.create(name="Test Cat", slug="test-cat-img")
        course = Course.objects.create(
            title="Test Course",
            slug="test-course-img",
            description="Desc",
            category=cat,
            instructor=self.user,
        )
        sess = Session.objects.create(course=course, title="Session 1", order=1)
        payload = {
            "prefix": "session-assets",
            "filename": "image.png",
            "content_type": "image/png",
            "course_id": course.id,
            "session_id": sess.id,
        }
        response = self.client.post(PRESIGN_URL, payload, format="json", **self.auth)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content_type", response.data)

    def test_session_assets_requires_course_id_and_session_id(self):
        """session-assets prefix requires course_id and session_id in POST body."""
        payload = {
            "prefix": "session-assets",
            "filename": "intro.mp4",
            "content_type": "video/mp4",
        }
        response = self.client.post(PRESIGN_URL, payload, format="json", **self.auth)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("course_id", response.data)
        self.assertIn("session_id", response.data)

        payload["course_id"] = 1
        response = self.client.post(PRESIGN_URL, payload, format="json", **self.auth)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("session_id", response.data)

    @patch("apps.common.views.create_boto3_client")
    def test_session_assets_returns_private_bucket_no_acl(self, mock_factory):
        """session-assets uses private bucket and does not include x-amz-acl header."""
        mock_client = mock_factory.return_value
        mock_client.generate_presigned_url.return_value = "https://signed.example/upload"

        cat = Category.objects.create(name="Test Cat", slug="test-cat")
        course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Desc",
            category=cat,
            instructor=self.user,
        )
        sess = Session.objects.create(course=course, title="Session 1", order=1)

        payload = {
            "prefix": "session-assets",
            "filename": "intro.mp4",
            "content_type": "video/mp4",
            "course_id": course.id,
            "session_id": sess.id,
        }
        response = self.client.post(PRESIGN_URL, payload, format="json", **self.auth)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["bucket"], "tasc-private")
        self.assertNotIn("public_url", response.data)
        self.assertNotIn("x-amz-acl", response.data["headers"])
        self.assertIn("object_key", response.data)
        self.assertTrue(response.data["object_key"].startswith("session-assets/course_"))
        self.assertTrue("session_" in response.data["object_key"])

        call_kwargs = mock_client.generate_presigned_url.call_args.kwargs
        self.assertEqual(call_kwargs["Params"]["Bucket"], "tasc-private")
        self.assertNotIn("ACL", call_kwargs["Params"])

    def test_session_assets_presigned_url_uses_virtual_hosted_style(self):
        """Presigned upload_url must use virtual-hosted style (bucket as subdomain) for DO Spaces."""
        cat = Category.objects.create(name="Test Cat", slug="test-cat-vh")
        course = Course.objects.create(
            title="Test Course",
            slug="test-course-vh",
            description="Desc",
            category=cat,
            instructor=self.user,
        )
        sess = Session.objects.create(course=course, title="Session 1", order=1)

        payload = {
            "prefix": "session-assets",
            "filename": "intro.mp4",
            "content_type": "video/mp4",
            "course_id": course.id,
            "session_id": sess.id,
        }
        response = self.client.post(PRESIGN_URL, payload, format="json", **self.auth)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        upload_url = response.data["upload_url"]
        # Virtual-hosted: https://<bucket>.lon1.digitaloceanspaces.com/<key>?...
        # Path-style would be: https://lon1.digitaloceanspaces.com/<bucket>/<key>?...
        self.assertIn(
            "tasc-private.lon1.digitaloceanspaces.com",
            upload_url,
            "upload_url must use virtual-hosted style (bucket as subdomain)",
        )

    def test_session_assets_unauthorized_learner_blocked(self):
        """Non-course-writer (learner) receives 403 for session-assets."""
        learner = User.objects.create_user(
            username="learner",
            email="learner@example.com",
            password="pass1234",
            role="learner",
            email_verified=True,
            is_active=True,
        )
        cat = Category.objects.create(name="Test Cat", slug="test-cat-2")
        course = Course.objects.create(
            title="Test Course",
            slug="test-course-2",
            description="Desc",
            category=cat,
        )
        sess = Session.objects.create(course=course, title="Session 1", order=1)

        payload = {
            "prefix": "session-assets",
            "filename": "intro.mp4",
            "content_type": "video/mp4",
            "course_id": course.id,
            "session_id": sess.id,
        }
        response = self.client.post(
            PRESIGN_URL, payload, format="json", **{"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(learner).access_token}"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.common.views.create_boto3_client")
    def test_session_assets_instructor_cannot_presign_other_instructors_course(self, mock_factory):
        """Instructor gets 403 when presigning for a course they do not own."""
        mock_client = mock_factory.return_value
        mock_client.generate_presigned_url.return_value = "https://signed.example/upload"

        other_instructor = User.objects.create_user(
            username="other-instructor",
            email="other@example.com",
            password="pass1234",
            role="instructor",
            email_verified=True,
            is_active=True,
        )
        cat = Category.objects.create(name="Test Cat", slug="test-cat-3")
        course = Course.objects.create(
            title="Other Course",
            slug="other-course",
            description="Desc",
            category=cat,
            instructor=other_instructor,
        )
        sess = Session.objects.create(course=course, title="Session 1", order=1)

        payload = {
            "prefix": "session-assets",
            "filename": "intro.mp4",
            "content_type": "video/mp4",
            "course_id": course.id,
            "session_id": sess.id,
        }
        # self.user is instructor but does NOT own this course
        response = self.client.post(PRESIGN_URL, payload, format="json", **self.auth)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


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
