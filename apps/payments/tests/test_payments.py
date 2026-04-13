"""Tests for payment endpoints (migrated from tests.py)."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.catalogue.models import Course
from apps.payments.models import Subscription, Invoice, Transaction

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

    def test_invoice_download_pdf(self):
        invoice = Invoice.objects.create(
            user=self.user,
            invoice_type='subscription',
            customer_name="payuser",
            customer_email="test@example.com",
            subtotal=99.99,
            total_amount=99.99,
            currency='USD',
            status='pending',
        )
        response = self.client.get(f"/api/v1/payments/invoices/{invoice.id}/download-pdf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('invoice_number', response.json())

    def test_invoice_email_receipt(self):
        invoice = Invoice.objects.create(
            user=self.user,
            invoice_type='subscription',
            customer_name="payuser",
            customer_email="test@example.com",
            subtotal=99.99,
            total_amount=99.99,
            currency='USD',
            status='paid',
        )
        response = self.client.post(f"/api/v1/payments/invoices/{invoice.id}/email-receipt/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'Receipt email queued')

    def test_transaction_export_csv(self):
        Transaction.objects.create(
            user=self.user,
            course=self.course,
            amount=99.99,
            currency='USD',
            status='completed',
            payment_method='card',
        )
        response = self.client.get("/api/v1/payments/transactions/export-csv/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Content-Disposition', response)
        self.assertTrue(response.content.decode('utf-8').startswith('ID,Transaction ID,Amount,Currency,Status,Payment Method,Created At,Completed At'))
        self.assertIn('99.99', response.content.decode('utf-8'))


# ════════════════════════════════════════════════════════════════════════════
# LMS Manager revenue analytics — platform-wide (no org scoping)
# ════════════════════════════════════════════════════════════════════════════

from rest_framework_simplejwt.tokens import RefreshToken


def _pay_auth(user):
    return {'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(user).access_token}'}


class LmsManagerRevenueAnalyticsPlatformWideTest(APITestCase):
    """LMS Manager sees all revenue data — same as tasc_admin."""

    REVENUE_URL = '/api/v1/payments/analytics/revenue/'

    def setUp(self):
        self.manager = User.objects.create_user(
            username='mgr_rev', email='mgr_rev@example.com',
            password='pass1234', role='lms_manager',
            email_verified=True, is_active=True,
        )
        self.admin = User.objects.create_user(
            username='admin_rev', email='admin_rev@example.com',
            password='pass1234', role='tasc_admin',
            email_verified=True, is_active=True,
        )

    def test_revenue_lms_manager_200(self):
        response = self.client.get(self.REVENUE_URL, **_pay_auth(self.manager))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('revenue', data)
        self.assertIn('total_revenue', data)

    def test_revenue_lms_manager_matches_tasc_admin(self):
        mgr_resp = self.client.get(self.REVENUE_URL, **_pay_auth(self.manager))
        admin_resp = self.client.get(self.REVENUE_URL, **_pay_auth(self.admin))
        self.assertEqual(mgr_resp.json()['revenue'], admin_resp.json()['revenue'])
