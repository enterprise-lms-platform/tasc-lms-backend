"""Tests for learning app including subscription-gated endpoints."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalogue.models import Category, Course, Session
from apps.learning.models import Enrollment, SessionProgress
from apps.payments.models import Subscription, UserSubscription

User = get_user_model()

ENROLLMENTS_URL = '/api/v1/learning/enrollments/'
SESSION_PROGRESS_URL = '/api/v1/learning/session-progress/'


def _auth(user):
    return {'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(user).access_token}'}


def _grant_subscription(user, days=180):
    """Grant active subscription to user for testing."""
    plan = Subscription.objects.filter(status=Subscription.Status.ACTIVE).first()
    if not plan:
        plan = Subscription.objects.create(
            name="6-Month Test",
            description="Test plan",
            price=Decimal("0.00"),
            currency="USD",
            billing_cycle="yearly",
            status=Subscription.Status.ACTIVE,
        )
    UserSubscription.objects.create(
        user=user,
        subscription=plan,
        status=UserSubscription.Status.ACTIVE,
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=days),
        price=plan.price,
        currency=plan.currency,
    )


class EnrollmentSubscriptionGateTest(APITestCase):
    """POST /api/v1/learning/enrollments/ requires active subscription for learners."""

    def setUp(self):
        self.client = APIClient()
        self.learner = User.objects.create_user(
            username='enroll_learner',
            email='enroll_learner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        category = Category.objects.create(name='Test Cat', slug='test-cat')
        self.course = Course.objects.create(
            title='Test Course',
            description='desc',
            slug='enroll-test-course',
            status='published',
            instructor=User.objects.create_user(
                username='inst',
                email='inst@example.com',
                password='pass1234',
                role=User.Role.INSTRUCTOR,
                email_verified=True,
                is_active=True,
            ),
            created_by=None,
        )

    def test_learner_without_subscription_gets_400(self):
        response = self.client.post(
            ENROLLMENTS_URL,
            {'course': self.course.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('subscription', response.data)
        self.assertIn('active subscription', str(response.data['subscription']).lower())

    def test_learner_with_subscription_gets_201(self):
        _grant_subscription(self.learner)
        response = self.client.post(
            ENROLLMENTS_URL,
            {'course': self.course.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['course'], self.course.id)

    def test_instructor_can_enroll_without_subscription(self):
        inst = User.objects.filter(role=User.Role.INSTRUCTOR).first()
        response = self.client.post(
            ENROLLMENTS_URL,
            {'course': self.course.id},
            format='json',
            **_auth(inst),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class SessionProgressSubscriptionGateTest(APITestCase):
    """Session progress endpoints require active subscription for learners."""

    def setUp(self):
        self.client = APIClient()
        self.learner = User.objects.create_user(
            username='progress_learner',
            email='progress_learner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        category = Category.objects.create(name='Prog Cat', slug='prog-cat')
        self.course = Course.objects.create(
            title='Progress Course',
            description='desc',
            slug='progress-course',
            status='published',
            instructor=User.objects.create_user(
                username='prog_inst',
                email='prog_inst@example.com',
                password='pass1234',
                role=User.Role.INSTRUCTOR,
                email_verified=True,
                is_active=True,
            ),
            created_by=None,
        )
        self.session = Session.objects.create(
            course=self.course,
            title='S1',
            order=1,
            session_type='video',
        )
        self.enrollment = Enrollment.objects.create(
            user=self.learner,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )
        self.session_progress = SessionProgress.objects.create(
            enrollment=self.enrollment,
            session=self.session,
        )

    def test_learner_without_subscription_gets_403_on_list(self):
        response = self.client.get(
            SESSION_PROGRESS_URL,
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_learner_with_subscription_gets_200_on_list(self):
        _grant_subscription(self.learner)
        response = self.client.get(
            SESSION_PROGRESS_URL,
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
