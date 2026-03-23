"""Tests for payment endpoints (migrated from tests.py)."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.catalogue.models import Course
from apps.payments.models import Subscription

User = get_user_model()


class PublicSubscriptionPlansTest(APITestCase):
    """GET /api/v1/public/subscription-plans/ allows anonymous access."""

    def setUp(self):
        Subscription.objects.create(
            name='Test Plan',
            description='Test description',
            price=99.99,
            currency='USD',
            billing_cycle='monthly',
            status=Subscription.Status.ACTIVE,
        )

    def test_anonymous_can_list_public_subscription_plans(self):
        response = self.client.get('/api/v1/public/subscription-plans/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertGreaterEqual(len(data['results']), 1)
        plan = data['results'][0]
        self.assertIn('id', plan)
        self.assertIn('name', plan)
        self.assertIn('price', plan)
        self.assertIn('billing_cycle', plan)

    def test_only_active_plans_returned(self):
        Subscription.objects.create(
            name='Inactive Plan',
            price=49.99,
            currency='USD',
            billing_cycle='yearly',
            status=Subscription.Status.INACTIVE,
        )
        response = self.client.get('/api/v1/public/subscription-plans/')
        self.assertEqual(response.status_code, 200)
        names = [p['name'] for p in response.json()['results']]
        self.assertIn('Test Plan', names)
        self.assertNotIn('Inactive Plan', names)


class PaymentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
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
