"""Tests for learning app including subscription-gated endpoints."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalogue.models import Assignment, Category, Course, Session
from apps.learning.models import Enrollment, SessionProgress, Submission
from apps.payments.models import Subscription, UserSubscription

User = get_user_model()

ENROLLMENTS_URL = '/api/v1/learning/enrollments/'
SESSION_PROGRESS_URL = '/api/v1/learning/session-progress/'
SUBMISSIONS_URL = '/api/v1/learning/submissions/'
PRESIGN_URL = '/api/v1/uploads/presign/'


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

    def test_learner_without_subscription_gets_403(self):
        response = self.client.post(
            ENROLLMENTS_URL,
            {'course': self.course.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('detail', response.data)
        self.assertIn('active subscription', str(response.data['detail']).lower())

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

    def test_duplicate_enroll_idempotent_returns_200(self):
        """Repeated POST for same course returns 200 with existing enrollment (no IntegrityError)."""
        _grant_subscription(self.learner)
        first = self.client.post(
            ENROLLMENTS_URL,
            {'course': self.course.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        enrollment_id = first.data['id']

        second = self.client.post(
            ENROLLMENTS_URL,
            {'course': self.course.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data['id'], enrollment_id)
        self.assertEqual(second.data['course'], self.course.id)

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


# -----------------------------------------------------------------------------
# Submission V1 tests
# -----------------------------------------------------------------------------

def _make_assignment_course():
    """Helper: create course with assignment session."""
    instructor = User.objects.create_user(
        username='sub_instructor',
        email='sub_inst@example.com',
        password='pass1234',
        role=User.Role.INSTRUCTOR,
        email_verified=True,
        is_active=True,
    )
    category = Category.objects.create(name='Sub Cat', slug='sub-cat')
    course = Course.objects.create(
        title='Submission Course',
        description='desc',
        slug='sub-course',
        status='published',
        instructor=instructor,
        created_by=None,
    )
    session = Session.objects.create(
        course=course,
        title='Assignment Session',
        order=1,
        session_type=Session.SessionType.ASSIGNMENT,
    )
    assignment = Assignment.objects.create(session=session, max_points=100)
    return course, session, assignment, instructor


class SubmissionModelTest(TestCase):
    """Submission model: create, unique constraint, status choices."""

    def setUp(self):
        course, session, self.assignment, _ = _make_assignment_course()
        self.learner = User.objects.create_user(
            username='sub_learner',
            email='sub_learner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.enrollment = Enrollment.objects.create(
            user=self.learner,
            course=course,
            status=Enrollment.Status.ACTIVE,
        )

    def test_create_submission_draft(self):
        s = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.DRAFT,
        )
        self.assertEqual(s.status, Submission.Status.DRAFT)
        self.assertIsNone(s.submitted_at)
        self.assertIsNone(s.grade)

    def test_create_submission_submitted(self):
        s = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.SUBMITTED,
            submitted_text='My answer',
            submitted_at=timezone.now(),
        )
        self.assertEqual(s.status, Submission.Status.SUBMITTED)
        self.assertEqual(s.submitted_text, 'My answer')

    def test_unique_enrollment_assignment(self):
        Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.DRAFT,
        )
        with self.assertRaises(Exception):
            Submission.objects.create(
                enrollment=self.enrollment,
                assignment=self.assignment,
                status=Submission.Status.DRAFT,
            )


class SubmissionApiTest(APITestCase):
    """Submission API: create, list, detail, update, grade, duplicate prevention."""

    def setUp(self):
        self.client = APIClient()
        course, session, self.assignment, self.instructor = _make_assignment_course()
        self.learner = User.objects.create_user(
            username='api_learner',
            email='api_learner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.enrollment = Enrollment.objects.create(
            user=self.learner,
            course=course,
            status=Enrollment.Status.ACTIVE,
        )
        self.admin = User.objects.create_user(
            username='sub_admin',
            email='sub_admin@example.com',
            password='pass1234',
            role=User.Role.TASC_ADMIN,
            email_verified=True,
            is_active=True,
        )

    def test_learner_create_submission_201(self):
        response = self.client.post(
            SUBMISSIONS_URL,
            {'enrollment': self.enrollment.id, 'assignment': self.assignment.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(response.data['assignment'], self.assignment.id)
        self.assertEqual(response.data['enrollment'], self.enrollment.id)

    def test_duplicate_submission_returns_400(self):
        self.client.post(
            SUBMISSIONS_URL,
            {'enrollment': self.enrollment.id, 'assignment': self.assignment.id},
            format='json',
            **_auth(self.learner),
        )
        response = self.client.post(
            SUBMISSIONS_URL,
            {'enrollment': self.enrollment.id, 'assignment': self.assignment.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)
        self.assertIn('already exists', str(response.data['non_field_errors']).lower())

    def test_learner_cannot_create_for_others_enrollment(self):
        other = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        other_enrollment = Enrollment.objects.create(
            user=other,
            course=self.enrollment.course,
            status=Enrollment.Status.ACTIVE,
        )
        response = self.client.post(
            SUBMISSIONS_URL,
            {'enrollment': other_enrollment.id, 'assignment': self.assignment.id},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_requires_text_or_file(self):
        response = self.client.post(
            SUBMISSIONS_URL,
            {
                'enrollment': self.enrollment.id,
                'assignment': self.assignment.id,
                'status': 'submitted',
            },
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_submit_with_text_201(self):
        response = self.client.post(
            SUBMISSIONS_URL,
            {
                'enrollment': self.enrollment.id,
                'assignment': self.assignment.id,
                'status': 'submitted',
                'submitted_text': 'My essay answer',
            },
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'submitted')
        self.assertEqual(response.data['submitted_text'], 'My essay answer')
        self.assertIsNotNone(response.data.get('submitted_at'))

    def test_learner_list_own_only(self):
        Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.DRAFT,
        )
        other = User.objects.create_user(
            username='other2',
            email='other2@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        other_enroll = Enrollment.objects.create(
            user=other,
            course=self.enrollment.course,
            status=Enrollment.Status.ACTIVE,
        )
        Submission.objects.create(
            enrollment=other_enroll,
            assignment=self.assignment,
            status=Submission.Status.DRAFT,
        )
        response = self.client.get(SUBMISSIONS_URL, **_auth(self.learner))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['enrollment'], self.enrollment.id)

    def test_learner_patch_draft_200(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.DRAFT,
            submitted_text='draft',
        )
        response = self.client.patch(
            f'{SUBMISSIONS_URL}{sub.id}/',
            {'submitted_text': 'updated draft'},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['submitted_text'], 'updated draft')

    def test_learner_patch_submitted_400(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.SUBMITTED,
            submitted_text='submitted',
            submitted_at=timezone.now(),
        )
        response = self.client.patch(
            f'{SUBMISSIONS_URL}{sub.id}/',
            {'submitted_text': 'trying to edit'},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_learner_grade_403(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.SUBMITTED,
            submitted_text='submitted',
            submitted_at=timezone.now(),
        )
        response = self.client.post(
            f'{SUBMISSIONS_URL}{sub.id}/grade/',
            {'grade': 85, 'feedback': 'Good work'},
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_instructor_grade_200(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.SUBMITTED,
            submitted_text='submitted',
            submitted_at=timezone.now(),
        )
        response = self.client.post(
            f'{SUBMISSIONS_URL}{sub.id}/grade/',
            {'grade': 85, 'feedback': 'Good work'},
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'graded')
        self.assertEqual(response.data['grade'], 85)
        self.assertEqual(response.data['feedback'], 'Good work')

    def test_grade_out_of_range_400(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.SUBMITTED,
            submitted_text='submitted',
            submitted_at=timezone.now(),
        )
        response = self.client.post(
            f'{SUBMISSIONS_URL}{sub.id}/grade/',
            {'grade': 150, 'feedback': 'Nope'},
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_grade_draft_400(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.DRAFT,
        )
        response = self.client.post(
            f'{SUBMISSIONS_URL}{sub.id}/grade/',
            {'grade': 50},
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_learner_delete_draft_204(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.DRAFT,
        )
        response = self.client.delete(
            f'{SUBMISSIONS_URL}{sub.id}/',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Submission.objects.filter(id=sub.id).exists())

    def test_learner_delete_submitted_400(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.SUBMITTED,
            submitted_text='x',
            submitted_at=timezone.now(),
        )
        response = self.client.delete(
            f'{SUBMISSIONS_URL}{sub.id}/',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_instructor_list_submissions_for_course(self):
        sub = Submission.objects.create(
            enrollment=self.enrollment,
            assignment=self.assignment,
            status=Submission.Status.SUBMITTED,
            submitted_text='x',
            submitted_at=timezone.now(),
        )
        response = self.client.get(SUBMISSIONS_URL, **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)


class SubmissionPresignTest(APITestCase):
    """Presign submission-files: enrollment ownership and assignment-in-course validation."""

    def setUp(self):
        self.client = APIClient()
        course, session, self.assignment, _ = _make_assignment_course()
        self.learner = User.objects.create_user(
            username='presign_learner',
            email='presign_learner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.enrollment = Enrollment.objects.create(
            user=self.learner,
            course=course,
            status=Enrollment.Status.ACTIVE,
        )

    def test_submission_files_requires_enrollment_assignment(self):
        response = self.client.post(
            PRESIGN_URL,
            {
                'prefix': 'submission-files',
                'filename': 'doc.pdf',
                'content_type': 'application/pdf',
            },
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submission_files_own_enrollment_ok(self):
        """Learner with own enrollment gets presign (assuming Spaces configured)."""
        response = self.client.post(
            PRESIGN_URL,
            {
                'prefix': 'submission-files',
                'filename': 'doc.pdf',
                'content_type': 'application/pdf',
                'enrollment_id': self.enrollment.id,
                'assignment_id': self.assignment.id,
            },
            format='json',
            **_auth(self.learner),
        )
        # May be 200 (if configured) or 503 (Spaces not configured in test)
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE))

    def test_submission_files_other_enrollment_403(self):
        other = User.objects.create_user(
            username='presign_other',
            email='presign_other@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        other_enroll = Enrollment.objects.create(
            user=other,
            course=self.enrollment.course,
            status=Enrollment.Status.ACTIVE,
        )
        response = self.client.post(
            PRESIGN_URL,
            {
                'prefix': 'submission-files',
                'filename': 'doc.pdf',
                'content_type': 'application/pdf',
                'enrollment_id': other_enroll.id,
                'assignment_id': self.assignment.id,
            },
            format='json',
            **_auth(self.learner),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
