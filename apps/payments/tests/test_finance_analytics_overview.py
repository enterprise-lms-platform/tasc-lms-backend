from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.payments.models import Invoice, Payment, Subscription, UserSubscription

User = get_user_model()


class FinanceAnalyticsOverviewApiTests(APITestCase):
    endpoint = '/api/v1/payments/finance/analytics-overview/'

    def setUp(self):
        self.finance_user = User.objects.create_user(
            username='finance_analytics_user',
            email='finance-analytics@example.com',
            password='pass1234',
            role='finance',
            email_verified=True,
            is_active=True,
        )
        self.regular_user = User.objects.create_user(
            username='learner_analytics_user',
            email='learner-analytics@example.com',
            password='pass1234',
            role='learner',
            email_verified=True,
            is_active=True,
        )
        self.other_user = User.objects.create_user(
            username='other_analytics_user',
            email='other-analytics@example.com',
            password='pass1234',
            role='learner',
            email_verified=True,
            is_active=True,
        )
        self.subscription_plan = Subscription.objects.create(
            name='Analytics Plan',
            description='Plan for analytics tests',
            price=Decimal('120.00'),
            currency='UGX',
            billing_cycle='yearly',
            duration_days=180,
            status='active',
        )

    def _create_payment(self, **kwargs):
        created_at = kwargs.pop('created_at', None)
        completed_at = kwargs.pop('completed_at', None)
        defaults = {
            'user': self.regular_user,
            'amount': Decimal('100.00'),
            'currency': 'UGX',
            'payment_method': 'pesapal',
            'status': 'pending',
            'description': 'Analytics payment',
        }
        defaults.update(kwargs)
        payment = Payment.objects.create(**defaults)
        update_fields = {}
        if created_at is not None:
            update_fields['created_at'] = created_at
        if completed_at is not None:
            update_fields['completed_at'] = completed_at
        if update_fields:
            Payment.objects.filter(id=payment.id).update(**update_fields)
            payment.refresh_from_db()
        return payment

    def test_requires_authentication(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 401)

    def test_rejects_non_finance_roles(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 403)

    def test_uses_default_months_for_invalid_value(self):
        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint, {'months': 99})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['window']['months'], 6)

    def test_months_window_and_zero_fill_and_status_bucket_fill(self):
        now = timezone.now()
        this_month = now.replace(day=5, hour=10, minute=0, second=0, microsecond=0)
        month_2 = (this_month - timedelta(days=31)).replace(day=7)
        month_4 = (this_month - timedelta(days=31 * 3)).replace(day=9)

        # Completed rows in non-consecutive months to verify zero-filled months.
        self._create_payment(
            status='completed',
            amount=Decimal('120.00'),
            created_at=this_month,
            completed_at=this_month,
        )
        self._create_payment(
            status='completed',
            amount=Decimal('200.00'),
            created_at=month_2,
            completed_at=month_2,
        )
        self._create_payment(
            status='completed',
            amount=Decimal('300.00'),
            created_at=month_4,
            completed_at=month_4,
        )
        self._create_payment(status='failed', amount=Decimal('50.00'), created_at=this_month)
        self._create_payment(status='pending', amount=Decimal('60.00'), created_at=this_month)

        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint, {'months': 6})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['window']['months'], 6)
        self.assertEqual(len(data['revenue_trend']), 6)
        zero_months = [p for p in data['revenue_trend'] if p['collected_revenue'] == '0.00']
        self.assertTrue(len(zero_months) >= 1)

        outcomes = data['payment_outcomes']
        self.assertEqual(outcomes['cancelled'], 0)
        self.assertEqual(outcomes['refunded'], 0)
        self.assertEqual(outcomes['completed'], 3)
        self.assertEqual(outcomes['failed'], 1)
        self.assertEqual(outcomes['pending'], 1)
        self.assertEqual(outcomes['total'], 5)

    def test_completion_rate_and_failed_count_use_selected_window(self):
        now = timezone.now()
        in_window = now - timedelta(days=20)
        old = now - timedelta(days=31 * 7)

        # In 6-month window: 2 completed, 1 failed, 1 pending => 50.0%
        self._create_payment(status='completed', created_at=in_window, completed_at=in_window)
        self._create_payment(status='completed', created_at=in_window, completed_at=in_window)
        self._create_payment(status='failed', created_at=in_window)
        self._create_payment(status='pending', created_at=in_window)

        # Out of window should not influence completion rate or failed count window metric.
        self._create_payment(status='failed', created_at=old)
        self._create_payment(status='completed', created_at=old, completed_at=old)

        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint, {'months': 6})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['payment_kpis']['payment_completion_rate_pct'], 50.0)
        self.assertEqual(data['payment_kpis']['failed_payments_count'], 1)

    def test_invoice_and_subscription_aggregates(self):
        today = timezone.localdate()
        Invoice.objects.create(
            user=self.regular_user,
            invoice_type='subscription',
            customer_name='Learner Analytics',
            customer_email='learner-analytics@example.com',
            subtotal=Decimal('80.00'),
            total_amount=Decimal('80.00'),
            currency='UGX',
            status='pending',
            due_date=today - timedelta(days=2),
        )
        Invoice.objects.create(
            user=self.other_user,
            invoice_type='subscription',
            customer_name='Other Analytics',
            customer_email='other-analytics@example.com',
            subtotal=Decimal('70.00'),
            total_amount=Decimal('70.00'),
            currency='UGX',
            status='pending',
            due_date=today + timedelta(days=4),
        )
        Invoice.objects.create(
            user=self.other_user,
            invoice_type='subscription',
            customer_name='Paid Invoice',
            customer_email='paid@example.com',
            subtotal=Decimal('50.00'),
            total_amount=Decimal('50.00'),
            currency='UGX',
            status='paid',
            due_date=today - timedelta(days=5),
        )

        UserSubscription.objects.create(
            user=self.regular_user,
            subscription=self.subscription_plan,
            status='active',
            price=Decimal('120.00'),
            currency='UGX',
        )
        UserSubscription.objects.create(
            user=self.other_user,
            subscription=self.subscription_plan,
            status='cancelled',
            price=Decimal('120.00'),
            currency='UGX',
        )
        UserSubscription.objects.create(
            user=self.other_user,
            subscription=self.subscription_plan,
            status='expired',
            price=Decimal('120.00'),
            currency='UGX',
        )

        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['invoice_insights']['pending_invoices_count'], 2)
        self.assertEqual(data['invoice_insights']['pending_invoices_amount'], '150.00')
        self.assertEqual(data['invoice_insights']['overdue_invoices_count'], 1)
        self.assertEqual(data['subscription_insights']['active'], 1)
        self.assertEqual(data['subscription_insights']['cancelled'], 1)
        self.assertEqual(data['subscription_insights']['expired'], 1)
