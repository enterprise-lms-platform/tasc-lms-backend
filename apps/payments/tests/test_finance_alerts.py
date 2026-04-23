from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.payments.models import Invoice, Payment, Subscription, UserSubscription

User = get_user_model()


class FinanceAlertsApiTests(APITestCase):
    endpoint = '/api/v1/payments/finance/alerts/'

    def setUp(self):
        self.finance_user = User.objects.create_user(
            username='finance_user',
            email='finance@example.com',
            password='pass1234',
            role='finance',
            email_verified=True,
            is_active=True,
        )
        self.regular_user = User.objects.create_user(
            username='learner_user',
            email='learner@example.com',
            password='pass1234',
            role='learner',
            email_verified=True,
            is_active=True,
        )
        self.plan = Subscription.objects.create(
            name='Finance Plan',
            description='Plan',
            price=Decimal('120.00'),
            currency='UGX',
            billing_cycle='yearly',
            duration_days=365,
            status='active',
        )

    def _create_payment(self, **kwargs):
        defaults = {
            'user': self.regular_user,
            'amount': Decimal('100.00'),
            'currency': 'UGX',
            'payment_method': 'pesapal',
            'status': 'completed',
            'description': 'Payment',
        }
        defaults.update(kwargs)
        return Payment.objects.create(**defaults)

    def _create_invoice(self, **kwargs):
        defaults = {
            'user': self.regular_user,
            'invoice_type': 'subscription',
            'customer_name': 'Learner',
            'customer_email': 'learner@example.com',
            'subtotal': Decimal('50.00'),
            'total_amount': Decimal('50.00'),
            'currency': 'UGX',
            'status': 'pending',
            'due_date': timezone.localdate() + timedelta(days=1),
        }
        defaults.update(kwargs)
        return Invoice.objects.create(**defaults)

    def test_requires_authentication(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 401)

    def test_rejects_non_finance_roles(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 403)

    def test_returns_zero_summary_when_no_rules_match(self):
        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['summary'], {'total': 0, 'critical': 0, 'warning': 0, 'info': 0, 'success': 0})
        self.assertEqual(data['alerts'], [])

    def test_triggers_phase1_rules_and_orders_by_severity(self):
        now = timezone.now()
        today = timezone.localdate()

        for idx in range(4):
            self._create_invoice(
                total_amount=Decimal('300000.00'),
                due_date=today - timedelta(days=idx + 1),
                status='pending',
            )
        for _ in range(3):
            self._create_invoice(
                total_amount=Decimal('200000.00'),
                due_date=today + timedelta(days=2),
                status='pending',
            )

        for idx in range(6):
            self._create_payment(
                status='failed',
                created_at=now - timedelta(hours=1, minutes=idx),
            )
        for idx in range(14):
            self._create_payment(
                status='completed',
                completed_at=now - timedelta(hours=1),
                created_at=now - timedelta(hours=2, minutes=idx),
            )
        for idx in range(9):
            self._create_payment(
                status='pending',
                created_at=now - timedelta(hours=3, minutes=idx),
            )

        for idx in range(11):
            UserSubscription.objects.create(
                user=self.regular_user,
                subscription=self.plan,
                status='active',
                price=Decimal('120.00'),
                currency='UGX',
                end_date=now + timedelta(days=7, hours=idx),
            )
        UserSubscription.objects.create(
            user=self.regular_user,
            subscription=self.plan,
            status='cancelled',
            price=Decimal('120.00'),
            currency='UGX',
            cancelled_at=now - timedelta(hours=2),
        )

        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['summary']['total'], 6)
        self.assertEqual(data['summary']['critical'], 2)
        self.assertEqual(data['summary']['warning'], 2)
        self.assertEqual(data['summary']['info'], 2)
        self.assertEqual(data['summary']['success'], 0)

        codes = [a['code'] for a in data['alerts']]
        self.assertIn('INVOICE_OVERDUE_BACKLOG', codes)
        self.assertIn('PAYMENT_FAILURE_SPIKE', codes)
        self.assertIn('PAYMENT_PENDING_BUILDUP', codes)
        self.assertIn('SUBSCRIPTION_EXPIRY_WAVE', codes)
        self.assertIn('INVOICE_DUE_SOON', codes)
        self.assertIn('SUBSCRIPTION_CANCELLATIONS_TODAY', codes)

        severities = [a['severity'] for a in data['alerts']]
        self.assertEqual(severities[:2], ['critical', 'critical'])
        self.assertEqual(severities[2:4], ['warning', 'warning'])
        self.assertEqual(severities[4:], ['info', 'info'])
