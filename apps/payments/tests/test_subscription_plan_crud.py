from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.payments.models import Subscription

User = get_user_model()


class SubscriptionPlanCrudTest(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='planadmin',
            email='planadmin@example.com',
            password='pass1234',
            role=User.Role.TASC_ADMIN,
            email_verified=True,
            is_active=True,
        )
        self.learner_user = User.objects.create_user(
            username='planlearner',
            email='planlearner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.active_plan = Subscription.objects.create(
            name='Active Plan',
            description='Visible plan',
            price=Decimal('49.00'),
            currency='UGX',
            billing_cycle='monthly',
            duration_days=180,
            trial_days=0,
            status=Subscription.Status.ACTIVE,
        )
        self.inactive_plan = Subscription.objects.create(
            name='Inactive Plan',
            description='Hidden plan',
            price=Decimal('79.00'),
            currency='UGX',
            billing_cycle='yearly',
            duration_days=365,
            trial_days=0,
            status=Subscription.Status.INACTIVE,
        )
        self.archived_plan = Subscription.objects.create(
            name='Archived Plan',
            description='Retired plan',
            price=Decimal('99.00'),
            currency='UGX',
            billing_cycle='quarterly',
            duration_days=90,
            trial_days=0,
            status=Subscription.Status.ARCHIVED,
        )

    def test_admin_can_create_plan(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.post(
            '/api/v1/payments/subscriptions/',
            {
                'name': 'New Admin Plan',
                'description': 'Created by admin',
                'price': '129.00',
                'currency': 'UGX',
                'billing_cycle': 'yearly',
                'duration_days': 365,
                'features': ['Unlimited access'],
                'max_courses': None,
                'max_users': None,
                'trial_days': 0,
                'status': 'active',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Admin Plan')
        self.assertEqual(response.data['duration_days'], 365)
        self.assertEqual(response.data['status'], 'active')

    def test_admin_can_update_plan(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.patch(
            f'/api/v1/payments/subscriptions/{self.active_plan.id}/',
            {
                'price': '59.00',
                'duration_days': 200,
                'features': ['Priority support'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.active_plan.refresh_from_db()
        self.assertEqual(self.active_plan.price, Decimal('59.00'))
        self.assertEqual(self.active_plan.duration_days, 200)
        self.assertEqual(self.active_plan.features, ['Priority support'])

    def test_admin_can_change_status(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.patch(
            f'/api/v1/payments/subscriptions/{self.active_plan.id}/',
            {'status': 'archived'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.active_plan.refresh_from_db()
        self.assertEqual(self.active_plan.status, Subscription.Status.ARCHIVED)

    def test_non_admin_cannot_write_plan(self):
        self.client.force_authenticate(self.learner_user)
        response = self.client.post(
            '/api/v1/payments/subscriptions/',
            {
                'name': 'Blocked Plan',
                'price': '49.00',
                'currency': 'UGX',
                'billing_cycle': 'monthly',
                'duration_days': 180,
                'features': [],
                'trial_days': 0,
                'status': 'active',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_non_admin_plan_list_returns_active_only(self):
        self.client.force_authenticate(self.learner_user)
        response = self.client.get('/api/v1/payments/subscriptions/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data if isinstance(response.data, list) else response.data['results']
        ids = {item['id'] for item in payload}
        self.assertEqual(ids, {self.active_plan.id})

    def test_public_plan_list_returns_active_only(self):
        response = self.client.get('/api/v1/public/subscription-plans/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data if isinstance(response.data, list) else response.data['results']
        ids = {item['id'] for item in payload}
        self.assertEqual(ids, {self.active_plan.id})

    @patch('apps.payments.views_pesapal.PesapalService.initialize_payment')
    def test_inactive_or_archived_plan_cannot_start_onetime_pesapal_checkout(self, mock_initialize_payment):
        self.client.force_authenticate(self.learner_user)

        for plan in (self.inactive_plan, self.archived_plan):
            with self.subTest(status=plan.status):
                response = self.client.post(
                    '/api/v1/payments/pesapal/initiate-subscription-onetime/',
                    {'subscription_id': plan.id, 'currency': 'UGX'},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('not found or inactive', str(response.data).lower())

        mock_initialize_payment.assert_not_called()
