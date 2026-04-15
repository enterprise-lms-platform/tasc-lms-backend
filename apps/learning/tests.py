"""Tests for learning app including subscription-gated endpoints."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, Organization
from apps.catalogue.models import Assignment, Category, Course, Session, Quiz
from apps.learning.models import Certificate, Enrollment, SessionProgress, Submission, QuizSubmission
from apps.payments.models import Subscription, UserSubscription

User = get_user_model()

ENROLLMENTS_URL = '/api/v1/learning/enrollments/'
SESSION_PROGRESS_URL = '/api/v1/learning/session-progress/'
SUBMISSIONS_URL = '/api/v1/learning/submissions/'
QUIZ_SUBMISSIONS_URL = '/api/v1/learning/quiz-submissions/'
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


class OrgAdminSubmissionScopingTests(APITestCase):
    """Org admin reads must be scoped to active membership organization."""

    def setUp(self):
        self.client = APIClient()
        course, session, self.assignment, self.instructor = _make_assignment_course()
        self.course = course

        quiz_session = Session.objects.create(
            course=self.course,
            title='Quiz Session',
            order=2,
            session_type=Session.SessionType.QUIZ,
        )
        self.quiz = Quiz.objects.create(session=quiz_session)

        self.org_a = Organization.objects.create(name="Org A")
        self.org_b = Organization.objects.create(name="Org B")

        self.org_admin = User.objects.create_user(
            username='org_admin_user',
            email='org_admin@example.com',
            password='pass1234',
            role=User.Role.ORG_ADMIN,
            email_verified=True,
            is_active=True,
        )
        Membership.objects.create(
            user=self.org_admin,
            organization=self.org_a,
            role=Membership.Role.ORG_ADMIN,
            is_active=True,
        )

        self.org_admin_no_membership = User.objects.create_user(
            username='org_admin_no_membership',
            email='org_admin_no_membership@example.com',
            password='pass1234',
            role=User.Role.ORG_ADMIN,
            email_verified=True,
            is_active=True,
        )

        self.tasc_admin = User.objects.create_user(
            username='tasc_admin_user',
            email='tasc_admin@example.com',
            password='pass1234',
            role=User.Role.TASC_ADMIN,
            email_verified=True,
            is_active=True,
        )

        self.learner_a = User.objects.create_user(
            username='learner_a',
            email='learner_a@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.learner_b = User.objects.create_user(
            username='learner_b',
            email='learner_b@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )

        self.enrollment_a = Enrollment.objects.create(
            user=self.learner_a,
            course=self.course,
            organization=self.org_a,
            status=Enrollment.Status.ACTIVE,
        )
        self.enrollment_b = Enrollment.objects.create(
            user=self.learner_b,
            course=self.course,
            organization=self.org_b,
            status=Enrollment.Status.ACTIVE,
        )

        self.submission_a = Submission.objects.create(
            enrollment=self.enrollment_a,
            assignment=self.assignment,
            status=Submission.Status.GRADED,
            submitted_text='org-a',
            submitted_at=timezone.now(),
            grade=88,
        )
        self.submission_b = Submission.objects.create(
            enrollment=self.enrollment_b,
            assignment=self.assignment,
            status=Submission.Status.GRADED,
            submitted_text='org-b',
            submitted_at=timezone.now(),
            grade=55,
        )

        self.quiz_submission_a = QuizSubmission.objects.create(
            enrollment=self.enrollment_a,
            quiz=self.quiz,
            attempt_number=1,
            score=80,
            max_score=100,
            passed=True,
            time_spent_seconds=120,
        )
        self.quiz_submission_b = QuizSubmission.objects.create(
            enrollment=self.enrollment_b,
            quiz=self.quiz,
            attempt_number=1,
            score=40,
            max_score=100,
            passed=False,
            time_spent_seconds=100,
        )

    def test_org_admin_sees_only_own_org_submissions(self):
        response = self.client.get(SUBMISSIONS_URL, **_auth(self.org_admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.submission_a.id)
        self.assertNotEqual(results[0]['id'], self.submission_b.id)

    def test_org_admin_no_active_membership_gets_empty_submissions(self):
        response = self.client.get(SUBMISSIONS_URL, **_auth(self.org_admin_no_membership))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get('results', [])), 0)

    def test_org_admin_sees_only_own_org_quiz_submissions(self):
        response = self.client.get(QUIZ_SUBMISSIONS_URL, **_auth(self.org_admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.quiz_submission_a.id)
        self.assertNotEqual(results[0]['id'], self.quiz_submission_b.id)

    def test_org_admin_statistics_scoped_to_own_org(self):
        response = self.client.get(
            f'{SUBMISSIONS_URL}statistics/',
            {'course': self.course.id},
            **_auth(self.org_admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_submissions'], 1)
        self.assertEqual(response.data['graded'], 1)
        self.assertEqual(response.data['pending'], 0)
        self.assertEqual(response.data['average_grade'], 88.0)

    def test_org_admin_stats_fail_closed_without_membership(self):
        response = self.client.get(f'{SUBMISSIONS_URL}stats/', **_auth(self.org_admin_no_membership))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_assignments'], 0)
        self.assertEqual(response.data['graded'], 0)
        self.assertEqual(response.data['pending'], 0)
        self.assertEqual(response.data['total_quizzes'], 0)
        self.assertEqual(response.data['quiz_pass_rate'], 0)

    def test_learner_still_sees_own_data_only(self):
        response = self.client.get(SUBMISSIONS_URL, **_auth(self.learner_a))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.submission_a.id)

    def test_tasc_admin_behavior_preserved(self):
        response = self.client.get(SUBMISSIONS_URL, **_auth(self.tasc_admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        self.assertEqual(len(results), 2)


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


# ════════════════════════════════════════════════════════════════════════════
# LMS Manager analytics — platform-wide (no org scoping)
# ════════════════════════════════════════════════════════════════════════════

ENROLLMENT_TRENDS_URL = '/api/v1/learning/analytics/enrollment-trends/'
LEARNING_STATS_URL = '/api/v1/learning/analytics/learning-stats/'
TOP_COURSE_PERFORMANCE_URL = '/api/v1/learning/analytics/top-course-performance/'


class LmsManagerAnalyticsPlatformWideTest(APITestCase):
    """
    LMS Manager is a platform-wide role.  Analytics endpoints must return
    unfiltered data — identical to tasc_admin — with no org scoping.
    """

    def setUp(self):
        self.client = APIClient()

        self.manager = User.objects.create_user(
            username='mgr_analytics',
            email='mgr_analytics@example.com',
            password='pass1234',
            role=User.Role.LMS_MANAGER,
            email_verified=True,
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username='admin_analytics',
            email='admin_analytics@example.com',
            password='pass1234',
            role=User.Role.TASC_ADMIN,
            email_verified=True,
            is_active=True,
        )
        self.instructor = User.objects.create_user(
            username='inst_analytics',
            email='inst_analytics@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.learner = User.objects.create_user(
            username='learner_analytics',
            email='learner_analytics@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )

        cat = Category.objects.create(name='Analytics Cat')
        self.course = Course.objects.create(
            title='Analytics Course',
            instructor=self.instructor,
            category=cat,
            status='published',
        )
        self.enrollment = Enrollment.objects.create(
            user=self.learner,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )

    # ── enrollment-trends ──────────────────────────────────────────────

    def test_enrollment_trends_lms_manager_200(self):
        response = self.client.get(ENROLLMENT_TRENDS_URL, **_auth(self.manager))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('enrollments', data)
        self.assertIn('completions', data)

    def test_enrollment_trends_lms_manager_matches_tasc_admin(self):
        """LMS Manager sees identical trend data as tasc_admin."""
        mgr_resp = self.client.get(ENROLLMENT_TRENDS_URL, **_auth(self.manager))
        admin_resp = self.client.get(ENROLLMENT_TRENDS_URL, **_auth(self.admin))
        self.assertEqual(mgr_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(mgr_resp.json()['enrollments'], admin_resp.json()['enrollments'])

    def test_enrollment_trends_short_window_no_keyerror(self):
        """months=1 must not KeyError when DB month falls outside labels_map."""
        cat = Category.objects.get(name='Analytics Cat')
        extra_course = Course.objects.create(
            title='Edge Case Course',
            slug='edge-case-course',
            instructor=self.instructor,
            category=cat,
            status='published',
        )
        Enrollment.objects.create(
            user=self.learner,
            course=extra_course,
            status=Enrollment.Status.ACTIVE,
        )
        for m in (1, 2, 3):
            response = self.client.get(
                f'{ENROLLMENT_TRENDS_URL}?months={m}', **_auth(self.manager),
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            self.assertEqual(len(data['labels']), m)
            self.assertEqual(len(data['enrollments']), m)
            self.assertEqual(len(data['completions']), m)

    def test_enrollment_trends_instructor_sees_own_courses_only(self):
        """Instructor filter is preserved (not affected by our change)."""
        other_inst = User.objects.create_user(
            username='other_inst', email='other_inst@example.com',
            password='pass1234', role=User.Role.INSTRUCTOR,
            email_verified=True, is_active=True,
        )
        response = self.client.get(ENROLLMENT_TRENDS_URL, **_auth(other_inst))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(sum(response.json()['enrollments']), 0)

    # ── learning-stats ─────────────────────────────────────────────────

    def test_learning_stats_lms_manager_200(self):
        response = self.client.get(LEARNING_STATS_URL, **_auth(self.manager))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('total_learners', data)
        self.assertIn('avg_completion_rate', data)
        self.assertIn('avg_quiz_score', data)

    def test_learning_stats_lms_manager_matches_tasc_admin(self):
        mgr_resp = self.client.get(LEARNING_STATS_URL, **_auth(self.manager))
        admin_resp = self.client.get(LEARNING_STATS_URL, **_auth(self.admin))
        self.assertEqual(mgr_resp.json()['total_learners'], admin_resp.json()['total_learners'])

    def test_learning_stats_instructor_sees_own_courses_only(self):
        other_inst = User.objects.create_user(
            username='other_inst2', email='other_inst2@example.com',
            password='pass1234', role=User.Role.INSTRUCTOR,
            email_verified=True, is_active=True,
        )
        response = self.client.get(LEARNING_STATS_URL, **_auth(other_inst))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['total_learners'], 0)

    def test_learning_stats_total_courses_in_progress_counts_active_enrollments(self):
        """total_courses_in_progress must use Enrollment.Status.ACTIVE, not a non-existent status."""
        response = self.client.get(LEARNING_STATS_URL, **_auth(self.manager))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['total_courses_in_progress'], 1)

    # ── top-course-performance ─────────────────────────────────────────

    def test_top_course_performance_lms_manager_200_and_shape(self):
        response = self.client.get(TOP_COURSE_PERFORMANCE_URL, **_auth(self.manager))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        row = next(r for r in data if r['course_id'] == self.course.id)
        self.assertEqual(row['course_title'], 'Analytics Course')
        self.assertEqual(row['enrollments'], 1)
        self.assertIn('completed', row)
        self.assertIn('completion_rate', row)
        self.assertIsInstance(row['completion_rate'], int)

    def test_top_course_performance_tasc_admin_matches_manager(self):
        mgr = self.client.get(TOP_COURSE_PERFORMANCE_URL, **_auth(self.manager))
        admin = self.client.get(TOP_COURSE_PERFORMANCE_URL, **_auth(self.admin))
        self.assertEqual(mgr.status_code, status.HTTP_200_OK)
        self.assertEqual(admin.status_code, status.HTTP_200_OK)
        key = lambda rows: sorted(rows, key=lambda r: r['course_id'])
        self.assertEqual(key(mgr.json()), key(admin.json()))

    def test_top_course_performance_instructor_own_courses_only(self):
        other_inst = User.objects.create_user(
            username='tcp_other_inst',
            email='tcp_other_inst@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        cat = Category.objects.get(name='Analytics Cat')
        other_course = Course.objects.create(
            title='Other Inst TCPP Course',
            slug='other-inst-tcpp-course',
            instructor=other_inst,
            category=cat,
            status='published',
        )
        Enrollment.objects.create(
            user=self.learner,
            course=other_course,
            status=Enrollment.Status.ACTIVE,
        )
        response = self.client.get(TOP_COURSE_PERFORMANCE_URL, **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {r['course_id'] for r in response.json()}
        self.assertIn(self.course.id, ids)
        self.assertNotIn(other_course.id, ids)

    def test_top_course_performance_learner_403(self):
        response = self.client.get(TOP_COURSE_PERFORMANCE_URL, **_auth(self.learner))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EnrollmentListScopeAndFiltersTest(APITestCase):
    """GET /api/v1/learning/enrollments/ role-scoped queryset, status filter, pagination."""

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name='List Scope Org', slug='list-scope-org')
        self.other_org = Organization.objects.create(name='Other Org', slug='other-org-scope')

        self.instructor = User.objects.create_user(
            username='elst_inst',
            email='elst_inst@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.learner_a = User.objects.create_user(
            username='elst_learner_a',
            email='learner_a@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.learner_b = User.objects.create_user(
            username='elst_learner_b',
            email='learner_b@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        cat = Category.objects.create(name='ELST Cat', slug='elst-cat')
        self.course = Course.objects.create(
            title='ELST Course',
            description='d',
            slug='elst-course',
            status='published',
            instructor=self.instructor,
            category=cat,
            created_by=None,
        )
        self.enroll_inst_own = Enrollment.objects.create(
            user=self.instructor,
            course=self.course,
            organization=self.org,
            status=Enrollment.Status.ACTIVE,
        )
        self.enroll_a = Enrollment.objects.create(
            user=self.learner_a,
            course=self.course,
            organization=self.org,
            status=Enrollment.Status.ACTIVE,
        )
        self.enroll_b_completed = Enrollment.objects.create(
            user=self.learner_b,
            course=self.course,
            organization=self.org,
            status=Enrollment.Status.COMPLETED,
        )

        other_inst = User.objects.create_user(
            username='elst_other_inst',
            email='elst_other_inst@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.other_course = Course.objects.create(
            title='Other Inst Course',
            description='d',
            slug='other-inst-elst',
            status='published',
            instructor=other_inst,
            category=cat,
            created_by=None,
        )
        self.enroll_other = Enrollment.objects.create(
            user=self.learner_a,
            course=self.other_course,
            organization=self.other_org,
            status=Enrollment.Status.ACTIVE,
        )

        self.org_admin = User.objects.create_user(
            username='elst_org_admin',
            email='org_admin_elst@example.com',
            password='pass1234',
            role=User.Role.ORG_ADMIN,
            email_verified=True,
            is_active=True,
        )
        Membership.objects.create(
            user=self.org_admin,
            organization=self.org,
            role=Membership.Role.ORG_ADMIN,
            is_active=True,
        )

        self.lms_manager = User.objects.create_user(
            username='elst_lms_mgr',
            email='lms_mgr_elst@example.com',
            password='pass1234',
            role=User.Role.LMS_MANAGER,
            email_verified=True,
            is_active=True,
        )
        self.tasc_admin = User.objects.create_user(
            username='elst_tasc',
            email='tasc_elst@example.com',
            password='pass1234',
            role=User.Role.TASC_ADMIN,
            email_verified=True,
            is_active=True,
        )

    def _ids(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        if isinstance(data, list):
            return {row['id'] for row in data}
        return {row['id'] for row in data.get('results', [])}

    def test_learner_list_only_self(self):
        response = self.client.get(ENROLLMENTS_URL, **_auth(self.learner_a))
        ids = self._ids(response)
        self.assertEqual(ids, {self.enroll_a.id})

    def test_instructor_default_list_only_self(self):
        response = self.client.get(ENROLLMENTS_URL, **_auth(self.instructor))
        ids = self._ids(response)
        self.assertEqual(ids, {self.enroll_inst_own.id})

    def test_instructor_role_instructor_param_lists_students_in_taught_courses(self):
        response = self.client.get(
            f'{ENROLLMENTS_URL}?role=instructor',
            **_auth(self.instructor),
        )
        ids = self._ids(response)
        self.assertEqual(ids, {self.enroll_inst_own.id, self.enroll_a.id, self.enroll_b_completed.id})
        self.assertNotIn(self.enroll_other.id, ids)

    def test_org_admin_list_organization_enrollments_only(self):
        response = self.client.get(ENROLLMENTS_URL, **_auth(self.org_admin))
        ids = self._ids(response)
        self.assertEqual(ids, {self.enroll_inst_own.id, self.enroll_a.id, self.enroll_b_completed.id})
        self.assertNotIn(self.enroll_other.id, ids)

    def test_lms_manager_platform_wide(self):
        response = self.client.get(ENROLLMENTS_URL, **_auth(self.lms_manager))
        ids = self._ids(response)
        self.assertEqual(
            ids,
            {
                self.enroll_inst_own.id,
                self.enroll_a.id,
                self.enroll_b_completed.id,
                self.enroll_other.id,
            },
        )

    def test_tasc_admin_platform_wide(self):
        response = self.client.get(ENROLLMENTS_URL, **_auth(self.tasc_admin))
        ids = self._ids(response)
        self.assertEqual(
            ids,
            {
                self.enroll_inst_own.id,
                self.enroll_a.id,
                self.enroll_b_completed.id,
                self.enroll_other.id,
            },
        )

    def test_status_filter(self):
        response = self.client.get(
            f'{ENROLLMENTS_URL}?status={Enrollment.Status.COMPLETED}',
            **_auth(self.lms_manager),
        )
        ids = self._ids(response)
        self.assertEqual(ids, {self.enroll_b_completed.id})

    def test_pagination_returns_count_and_respects_page_size(self):
        response = self.client.get(
            f'{ENROLLMENTS_URL}?page_size=2',
            **_auth(self.lms_manager),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertEqual(response.data['count'], 4)
        self.assertEqual(len(response.data['results']), 2)


CERTIFICATES_URL = '/api/v1/learning/certificates/'
CERTIFICATES_STATS_URL = '/api/v1/learning/certificates/stats/'


class CertificateViewSetScopeTest(APITestCase):
    """GET certificates list/retrieve/latest/stats: role scope, search, course filter, pagination."""

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name='Cert Scope Org', slug='cert-scope-org')
        self.other_org = Organization.objects.create(name='Cert Other Org', slug='cert-other-org')

        self.instructor = User.objects.create_user(
            username='cert_inst',
            email='cert_inst@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.learner_a = User.objects.create_user(
            username='cert_learner_a',
            email='learner_a_cert@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.learner_b = User.objects.create_user(
            username='cert_learner_b',
            email='learner_b_cert@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        cat = Category.objects.create(name='Cert Cat', slug='cert-cat')
        self.course = Course.objects.create(
            title='Cert Course Alpha',
            description='d',
            slug='cert-course-alpha',
            status='published',
            instructor=self.instructor,
            category=cat,
            created_by=None,
        )
        other_inst = User.objects.create_user(
            username='cert_other_inst',
            email='cert_other_inst@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.other_course = Course.objects.create(
            title='Cert Course Beta',
            description='d',
            slug='cert-course-beta',
            status='published',
            instructor=other_inst,
            category=cat,
            created_by=None,
        )
        self.enroll_inst_own = Enrollment.objects.create(
            user=self.instructor,
            course=self.course,
            organization=self.org,
            status=Enrollment.Status.ACTIVE,
        )
        self.enroll_a = Enrollment.objects.create(
            user=self.learner_a,
            course=self.course,
            organization=self.org,
            status=Enrollment.Status.ACTIVE,
        )
        self.enroll_b = Enrollment.objects.create(
            user=self.learner_b,
            course=self.course,
            organization=self.org,
            status=Enrollment.Status.ACTIVE,
        )
        self.enroll_other = Enrollment.objects.create(
            user=self.learner_a,
            course=self.other_course,
            organization=self.other_org,
            status=Enrollment.Status.ACTIVE,
        )

        # Manual certificates avoid enrollment COMPLETED signal (needs FRONTEND_URL in tests).
        self.cert_a = Certificate.objects.create(enrollment=self.enroll_a)
        self.cert_b = Certificate.objects.create(enrollment=self.enroll_b)
        self.cert_other = Certificate.objects.create(enrollment=self.enroll_other)

        self.org_admin = User.objects.create_user(
            username='cert_org_admin',
            email='org_admin_cert@example.com',
            password='pass1234',
            role=User.Role.ORG_ADMIN,
            email_verified=True,
            is_active=True,
        )
        Membership.objects.create(
            user=self.org_admin,
            organization=self.org,
            role=Membership.Role.ORG_ADMIN,
            is_active=True,
        )
        self.org_admin_no_membership = User.objects.create_user(
            username='cert_org_admin_nom',
            email='org_admin_nom_cert@example.com',
            password='pass1234',
            role=User.Role.ORG_ADMIN,
            email_verified=True,
            is_active=True,
        )

        self.lms_manager = User.objects.create_user(
            username='cert_lms_mgr',
            email='lms_mgr_cert@example.com',
            password='pass1234',
            role=User.Role.LMS_MANAGER,
            email_verified=True,
            is_active=True,
        )
        self.tasc_admin = User.objects.create_user(
            username='cert_tasc',
            email='tasc_cert@example.com',
            password='pass1234',
            role=User.Role.TASC_ADMIN,
            email_verified=True,
            is_active=True,
        )

    def _cert_ids(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        rows = data if isinstance(data, list) else data.get('results', [])
        return {row['id'] for row in rows}

    def test_learner_list_only_own_certificates(self):
        response = self.client.get(CERTIFICATES_URL, **_auth(self.learner_a))
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_a.id, self.cert_other.id})

    def test_learner_b_list_only_own(self):
        response = self.client.get(CERTIFICATES_URL, **_auth(self.learner_b))
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_b.id})

    def test_instructor_list_only_own_enrollment_certificates(self):
        response = self.client.get(CERTIFICATES_URL, **_auth(self.instructor))
        ids = self._cert_ids(response)
        self.assertEqual(ids, set())

    def test_org_admin_list_org_scoped_only(self):
        response = self.client.get(CERTIFICATES_URL, **_auth(self.org_admin))
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_a.id, self.cert_b.id})
        self.assertNotIn(self.cert_other.id, ids)

    def test_org_admin_no_membership_empty_list(self):
        response = self.client.get(CERTIFICATES_URL, **_auth(self.org_admin_no_membership))
        ids = self._cert_ids(response)
        self.assertEqual(ids, set())

    def test_lms_manager_platform_wide(self):
        response = self.client.get(CERTIFICATES_URL, **_auth(self.lms_manager))
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_a.id, self.cert_b.id, self.cert_other.id})

    def test_tasc_admin_platform_wide(self):
        response = self.client.get(CERTIFICATES_URL, **_auth(self.tasc_admin))
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_a.id, self.cert_b.id, self.cert_other.id})

    def test_org_admin_retrieve_out_of_scope_404(self):
        response = self.client.get(
            f'{CERTIFICATES_URL}{self.cert_other.id}/',
            **_auth(self.org_admin),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_org_admin_retrieve_in_scope_200(self):
        response = self.client.get(
            f'{CERTIFICATES_URL}{self.cert_a.id}/',
            **_auth(self.org_admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.cert_a.id)

    def test_latest_respects_scope_for_org_admin(self):
        response = self.client.get(f'{CERTIFICATES_URL}latest/', **_auth(self.org_admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(response.data['id'], {self.cert_a.id, self.cert_b.id})

    def test_latest_404_when_no_certificates_in_scope(self):
        response = self.client.get(f'{CERTIFICATES_URL}latest/', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_search_certificate_number(self):
        # Full number avoids matching other rows via shared prefix (e.g. TASC-YYYYMMDD-…).
        response = self.client.get(
            f'{CERTIFICATES_URL}?search={self.cert_b.certificate_number}',
            **_auth(self.lms_manager),
        )
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_b.id})

    def test_search_learner_email(self):
        response = self.client.get(
            f'{CERTIFICATES_URL}?search=learner_b_cert',
            **_auth(self.lms_manager),
        )
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_b.id})

    def test_course_filter(self):
        response = self.client.get(
            f'{CERTIFICATES_URL}?course={self.course.id}',
            **_auth(self.lms_manager),
        )
        ids = self._cert_ids(response)
        self.assertEqual(ids, {self.cert_a.id, self.cert_b.id})

    def test_pagination_count(self):
        response = self.client.get(
            f'{CERTIFICATES_URL}?page_size=2',
            **_auth(self.lms_manager),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 2)

    def test_stats_learner_forbidden(self):
        response = self.client.get(CERTIFICATES_STATS_URL, **_auth(self.learner_a))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stats_instructor_forbidden(self):
        response = self.client.get(CERTIFICATES_STATS_URL, **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stats_org_admin_scoped(self):
        response = self.client.get(CERTIFICATES_STATS_URL, **_auth(self.org_admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 2)

    def test_stats_lms_manager_platform_total(self):
        response = self.client.get(CERTIFICATES_STATS_URL, **_auth(self.lms_manager))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 3)

    def test_stats_org_admin_no_membership_zero(self):
        response = self.client.get(CERTIFICATES_STATS_URL, **_auth(self.org_admin_no_membership))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 0)
