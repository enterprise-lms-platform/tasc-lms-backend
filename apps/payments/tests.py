from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.catalogue.models import Course


class PaymentTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="payuser",
            email="test@example.com",
            password="testpass123",
            email_verified=True,
            is_active=True,
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test course description",
            price=99.99,
        )
        self.client.force_authenticate(user=self.user)

    def test_list_invoices_authenticated(self):
        """Authenticated user can list their invoices."""
        response = self.client.get("/api/v1/payments/invoices/")
        self.assertEqual(response.status_code, 200)