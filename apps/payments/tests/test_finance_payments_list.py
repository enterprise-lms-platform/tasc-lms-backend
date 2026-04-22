from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.payments.models import Payment

User = get_user_model()


class FinancePaymentListTests(APITestCase):
    endpoint = '/api/v1/payments/finance/payments/'

    def setUp(self):
        self.finance_user = User.objects.create_user(
            username='finance_list_user',
            email='finance-list@example.com',
            password='pass1234',
            role='finance',
            email_verified=True,
            is_active=True,
        )
        self.regular_user = User.objects.create_user(
            username='regular_list_user',
            email='regular-list@example.com',
            password='pass1234',
            role='learner',
            email_verified=True,
            is_active=True,
        )

    def test_requires_finance_facing_role(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 403)

    def test_lists_payments_with_filters(self):
        Payment.objects.create(
            user=self.regular_user,
            amount=Decimal('100.00'),
            currency='UGX',
            payment_method='pesapal',
            status='completed',
            provider_order_id='order-abc',
            provider_payment_id='confirm-abc',
            description='Alpha payment',
        )
        Payment.objects.create(
            user=self.regular_user,
            amount=Decimal('50.00'),
            currency='UGX',
            payment_method='pesapal',
            status='failed',
            provider_order_id='order-def',
            provider_payment_id='confirm-def',
            description='Beta payment',
        )

        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get(self.endpoint, {'status': 'completed', 'search': 'alpha'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['status'], 'completed')
        self.assertEqual(data['results'][0]['provider_order_id'], 'order-abc')
