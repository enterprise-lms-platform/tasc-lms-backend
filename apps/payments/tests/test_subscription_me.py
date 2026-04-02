"""Tests for GET /api/v1/payments/subscription/me/ endpoint."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.payments.models import Subscription, UserSubscription

User = get_user_model()

SUBSCRIPTION_ME_URL = '/api/v1/payments/subscription/me/'
USER_SUBSCRIPTIONS_URL = '/api/v1/payments/user-subscriptions/'


def _auth(user):
    from rest_framework_simplejwt.tokens import RefreshToken
    return {'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(user).access_token}'}


class SubscriptionMeViewTest(APITestCase):
    """GET /api/v1/payments/subscription/me/ returns current user's subscription status."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='subuser',
            email='subuser@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )

    def _create_plan(self, name='Test Plan', billing_cycle='monthly'):
        return Subscription.objects.create(
            name=name,
            description='desc',
            price=Decimal('9.99'),
            currency='USD',
            billing_cycle=billing_cycle,
            status=Subscription.Status.ACTIVE,
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(SUBSCRIPTION_ME_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_subscriptions_returns_false(self):
        response = self.client.get(SUBSCRIPTION_ME_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data['has_active_subscription'])
        self.assertEqual(data['status'], 'none')
        self.assertFalse(data['is_trial'])
        self.assertIsNone(data['start_date'])
        self.assertIsNone(data['end_date'])
        self.assertEqual(data['days_remaining'], 0)
        self.assertIsNone(data['plan'])

    def test_expired_subscription_returns_false(self):
        plan = self._create_plan()
        UserSubscription.objects.create(
            user=self.user,
            subscription=plan,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now() - timedelta(days=200),
            end_date=timezone.now() - timedelta(days=10),
            price=plan.price,
            currency=plan.currency,
        )
        response = self.client.get(SUBSCRIPTION_ME_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data['has_active_subscription'])
        self.assertEqual(data['status'], 'none')

    def test_active_subscription_with_end_date_returns_true_and_days_remaining(self):
        plan = self._create_plan()
        end_date = timezone.now() + timedelta(days=30)
        UserSubscription.objects.create(
            user=self.user,
            subscription=plan,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now() - timedelta(days=5),
            end_date=end_date,
            price=plan.price,
            currency=plan.currency,
        )
        response = self.client.get(SUBSCRIPTION_ME_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['has_active_subscription'])
        self.assertEqual(data['status'], 'active')
        self.assertFalse(data['is_trial'])
        self.assertIsNotNone(data['start_date'])
        self.assertIsNotNone(data['end_date'])
        self.assertGreaterEqual(data['days_remaining'], 29)
        self.assertLessEqual(data['days_remaining'], 31)
        self.assertEqual(data['plan']['id'], plan.id)
        self.assertEqual(data['plan']['name'], plan.name)
        self.assertEqual(data['plan']['billing_cycle'], 'monthly')

    def test_active_subscription_with_end_date_null_returns_true_and_days_remaining_null(self):
        plan = self._create_plan()
        UserSubscription.objects.create(
            user=self.user,
            subscription=plan,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now(),
            end_date=None,
            price=plan.price,
            currency=plan.currency,
        )
        response = self.client.get(SUBSCRIPTION_ME_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['has_active_subscription'])
        self.assertEqual(data['status'], 'active')
        self.assertIsNone(data['end_date'])
        self.assertIsNone(data['days_remaining'])
        self.assertEqual(data['plan']['id'], plan.id)

    def test_multiple_active_prefers_null_end_date(self):
        plan_a = self._create_plan(name='Plan A')
        plan_b = self._create_plan(name='Plan B')
        # One with end_date, one without
        UserSubscription.objects.create(
            user=self.user,
            subscription=plan_b,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=365),
            price=plan_b.price,
            currency=plan_b.currency,
        )
        UserSubscription.objects.create(
            user=self.user,
            subscription=plan_a,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now(),
            end_date=None,
            price=plan_a.price,
            currency=plan_a.currency,
        )
        response = self.client.get(SUBSCRIPTION_ME_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['has_active_subscription'])
        # Must prefer the one with end_date null
        self.assertEqual(data['plan']['name'], 'Plan A')
        self.assertIsNone(data['days_remaining'])

    def test_multiple_active_prefers_latest_end_date_when_none_null(self):
        plan_a = self._create_plan(name='Plan A')
        plan_b = self._create_plan(name='Plan B')
        # Both with end_date; B ends later
        UserSubscription.objects.create(
            user=self.user,
            subscription=plan_a,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            price=plan_a.price,
            currency=plan_a.currency,
        )
        UserSubscription.objects.create(
            user=self.user,
            subscription=plan_b,
            status=UserSubscription.Status.ACTIVE,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=180),
            price=plan_b.price,
            currency=plan_b.currency,
        )
        response = self.client.get(SUBSCRIPTION_ME_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['has_active_subscription'])
        # Must prefer the one with latest end_date
        self.assertEqual(data['plan']['name'], 'Plan B')
        self.assertGreaterEqual(data['days_remaining'], 170)

    def test_paid_subscription_duration_is_plan_derived(self):
        plan = self._create_plan(name='6-Month Plan', billing_cycle='monthly')
        # Sanity check: Phase 1 target is 180 days plan-derived
        self.assertEqual(plan.duration_days, 180)

        before = timezone.now()
        response = self.client.post(
            USER_SUBSCRIPTIONS_URL,
            {'subscription': plan.id, 'is_trial': False},
            format='json',
            **_auth(self.user),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()

        end_date = parse_datetime(data['end_date'])
        self.assertIsNotNone(end_date)
        expected_seconds = plan.duration_days * 24 * 60 * 60
        actual_seconds = (end_date - before).total_seconds()
        self.assertLess(abs(actual_seconds - expected_seconds), 120)  # 2 minute tolerance

        self.assertEqual(data['status'], UserSubscription.Status.ACTIVE)
        self.assertFalse(data['is_trial'])

    def test_one_active_subscription_is_enforced_for_paid_and_trial(self):
        plan_a = self._create_plan(name='Plan A')
        plan_b = self._create_plan(name='Plan B')

        # Create a trial subscription (should be considered "active" for the one-subscription rule).
        trial_before = timezone.now()
        trial_response = self.client.post(
            USER_SUBSCRIPTIONS_URL,
            {'subscription': plan_a.id, 'is_trial': True},
            format='json',
            **_auth(self.user),
        )
        self.assertEqual(trial_response.status_code, status.HTTP_201_CREATED)
        trial_data = trial_response.json()
        trial_end_date = parse_datetime(trial_data['end_date'])
        self.assertIsNotNone(trial_end_date)
        self.assertLess(abs((trial_end_date - trial_before).total_seconds() - 7 * 24 * 60 * 60), 120)
        self.assertTrue(trial_data['is_trial'])

        # Attempt to create a second paid subscription while trial is still active.
        paid_response = self.client.post(
            USER_SUBSCRIPTIONS_URL,
            {'subscription': plan_b.id, 'is_trial': False},
            format='json',
            **_auth(self.user),
        )
        self.assertEqual(paid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('active subscription', paid_response.json().get('error', '').lower())
