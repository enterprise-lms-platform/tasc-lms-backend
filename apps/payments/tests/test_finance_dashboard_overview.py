from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.payments.models import Invoice, Payment, Subscription, UserSubscription

User = get_user_model()


class FinanceDashboardOverviewApiTests(APITestCase):
    endpoint = '/api/v1/payments/finance/dashboard-overview/'

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
        self.other_user = User.objects.create_user(
            username='other_user',
            email='other@example.com',
            password='pass1234',
            role='learner',
            email_verified=True,
            is_active=True,
        )
        self.subscription_plan = Subscription.objects.create(
            name='Biannual Plan',
            description='Plan',
            price=Decimal('120.00'),
            currency='UGX',
            billing_cycle='yearly',
            duration_days=180,
            status='active',
        )

    def _create_payment(self, **kwargs):
        created_at = kwargs.pop('created_at', None)
        defaults = {
            'user': self.regular_user,
            'amount': Decimal('100.00'),
            'currency': 'UGX',
            'payment_method': 'pesapal',
            'status': 'completed',
            'description': 'Subscription payment',
        }
        defaults.update(kwargs)
        payment = Payment.objects.create(**defaults)
        if created_at is not None:
            Payment.objects.filter(id=payment.id).update(created_at=created_at)
            payment.refresh_from_db()
        return payment

    def _create_invoice(self, **kwargs):
        defaults = {
            'user': self.regular_user,
            'invoice_type': 'subscription',
            'customer_name': 'Learner User',
            'customer_email': 'learner@example.com',
            'subtotal': Decimal('50.00'),
            'total_amount': Decimal('50.00'),
            'currency': 'UGX',
            'status': 'pending',
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

    def test_returns_expected_kpis_month_filter_trend_and_recent_order(self):
        now = timezone.now()
        current_month_completed_at = now.replace(day=2, hour=10, minute=0, second=0, microsecond=0)
        previous_month_completed_at = (now.replace(day=1, hour=9, minute=0, second=0, microsecond=0) - timedelta(days=1)).replace(day=10)

        newest = self._create_payment(
            amount=Decimal('300.00'),
            completed_at=current_month_completed_at,
            created_at=now,
            provider_order_id='ord-new',
            provider_payment_id='pay-new',
        )
        self._create_payment(
            amount=Decimal('100.00'),
            completed_at=current_month_completed_at,
            created_at=now - timedelta(hours=2),
            provider_order_id='ord-this-month',
            provider_payment_id='pay-this-month',
        )
        self._create_payment(
            amount=Decimal('200.00'),
            completed_at=previous_month_completed_at,
            created_at=now - timedelta(days=40),
            provider_order_id='ord-last-month',
            provider_payment_id='pay-last-month',
        )
        self._create_payment(
            amount=Decimal('999.00'),
            status='failed',
            completed_at=None,
            created_at=now - timedelta(minutes=5),
            provider_order_id='ord-failed',
            provider_payment_id='pay-failed',
        )
        for idx in range(7):
            self._create_payment(
                amount=Decimal('10.00'),
                status='pending',
                completed_at=None,
                created_at=now - timedelta(days=idx + 1),
                provider_order_id=f'ord-pending-{idx}',
                provider_payment_id=f'pay-pending-{idx}',
            )

        self._create_invoice(total_amount=Decimal('50.00'), status='pending')
        self._create_invoice(total_amount=Decimal('70.00'), status='pending')
        self._create_invoice(total_amount=Decimal('500.00'), status='paid')

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

        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['currency'], 'UGX')
        self.assertEqual(data['kpis']['total_collected_revenue'], '600.00')
        self.assertEqual(data['kpis']['collected_revenue_this_month'], '400.00')
        self.assertEqual(data['kpis']['pending_invoices_count'], 2)
        self.assertEqual(data['kpis']['pending_invoices_amount'], '120.00')
        self.assertEqual(data['kpis']['active_subscribers'], 2)

        self.assertEqual(len(data['revenue_trend']), 6)
        trend_by_month = {row['month']: row['collected_revenue'] for row in data['revenue_trend']}
        self.assertEqual(trend_by_month[current_month_completed_at.strftime('%Y-%m')], '400.00')
        self.assertEqual(trend_by_month[previous_month_completed_at.strftime('%Y-%m')], '200.00')

        self.assertEqual(len(data['recent_payment_events']), 8)
        self.assertEqual(data['recent_payment_events'][0]['payment_id'], str(newest.id))
        created_times = [item['created_at'] for item in data['recent_payment_events']]
        self.assertEqual(created_times, sorted(created_times, reverse=True))
