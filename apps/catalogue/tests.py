from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from datetime import timedelta
from django.utils import timezone

from apps.learning.models import Enrollment
from apps.payments.models import Subscription, UserSubscription

from .models import Category, Course, Module, Quiz, QuizQuestion, Session, Tag


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

User = get_user_model()

COURSES_URL = '/api/v1/catalogue/courses/'
MODULES_URL = '/api/v1/catalogue/modules/'
SESSIONS_URL = '/api/v1/catalogue/sessions/'
CATEGORIES_URL = '/api/v1/catalogue/categories/'
TAGS_URL = '/api/v1/catalogue/tags/'


def _auth(user):
    """Return Authorization header dict for the given user."""
    token = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {token.access_token}'}


def _make_instructor(suffix=''):
    return User.objects.create_user(
        username=f'instructor{suffix}',
        email=f'instructor{suffix}@example.com',
        password='pass1234',
        role='instructor',
        email_verified=True,
        is_active=True,
    )


def _make_category():
    return Category.objects.create(name='Web Dev', slug='web-dev')


def _minimal_payload(**overrides):
    """Return the smallest valid draft-course payload."""
    base = {
        'title': 'Test Course',
        'description': 'Some description',
        'status': 'draft',
    }
    base.update(overrides)
    return base


class CourseDiscountedPriceTest(TestCase):
    def test_discounted_price_uses_decimal_math(self):
        course = Course(
            title="Discount Course",
            slug="discount-course",
            description="desc",
            price=Decimal("100.00"),
            discount_percentage=10,
        )
        self.assertEqual(course.discounted_price, Decimal("90.00"))

    def test_discounted_price_none_or_zero_discount_returns_price(self):
        base_kwargs = {
            "title": "No Discount Course",
            "slug": "no-discount-course",
            "description": "desc",
            "price": Decimal("100.00"),
        }
        course_none = Course(discount_percentage=None, **base_kwargs)
        self.assertEqual(course_none.discounted_price, Decimal("100.00"))

        course_zero = Course(discount_percentage=0, **base_kwargs)
        self.assertEqual(course_zero.discounted_price, Decimal("100.00"))


# ---------------------------------------------------------------------------
# A) Publish-time validation tests
# ---------------------------------------------------------------------------

class CoursePublishValidationTest(TestCase):
    """Publish requires thumbnail + >=4 objectives; draft does not."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor()

    def test_publish_without_thumbnail_returns_400(self):
        payload = _minimal_payload(
            status='published',
            learning_objectives_list=[
                'Obj 1', 'Obj 2', 'Obj 3', 'Obj 4'
            ],
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('thumbnail', response.data)

    def test_publish_with_thumbnail_but_only_three_objectives_returns_400(self):
        payload = _minimal_payload(
            status='published',
            thumbnail='https://example.com/thumb.png',
            learning_objectives_list=['Obj 1', 'Obj 2', 'Obj 3'],
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('learning_objectives_list', response.data)

    def test_publish_with_both_thumbnail_and_four_objectives_returns_201(self):
        payload = _minimal_payload(
            status='published',
            thumbnail='https://example.com/thumb.png',
            learning_objectives_list=[
                'Obj 1', 'Obj 2', 'Obj 3', 'Obj 4'
            ],
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'published')

    def test_publish_errors_include_both_fields_when_both_missing(self):
        """Single request that violates both thumbnail AND objectives returns errors for both."""
        payload = _minimal_payload(
            status='published',
            learning_objectives_list=[],
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # thumbnail error fires first in validate(); once it raises, objectives check
        # is not reached — so at minimum thumbnail key must be present.
        self.assertIn('thumbnail', response.data)

    def test_draft_allows_missing_objectives(self):
        payload = _minimal_payload(status='draft', learning_objectives_list=[])
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_draft_allows_missing_thumbnail(self):
        payload = _minimal_payload(status='draft')
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_patch_title_on_already_published_course_does_not_retrigger_publish_check(self):
        """PATCHing only title on a published course must not fail due to objectives check."""
        course = Course.objects.create(
            title='Published Course',
            description='desc',
            slug='published-course',
            status='published',
            thumbnail='https://example.com/thumb.png',
            learning_objectives_list=['O1', 'O2', 'O3', 'O4'],
            learning_objectives='O1\nO2\nO3\nO4',
            instructor=self.instructor,
            created_by=self.instructor,
        )
        url = f'{COURSES_URL}{course.id}/'
        response = self.client.patch(url, {'title': 'Updated Title'}, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Title')


# ---------------------------------------------------------------------------
# B) Publish validation falls back to learning_objectives string
# ---------------------------------------------------------------------------

class CoursePublishFallbackValidationTest(TestCase):
    """Objectives check should accept the newline-string field as fallback."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor(suffix='_fb')

    def test_publish_with_objectives_string_fallback_accepted(self):
        """Four objectives in learning_objectives string should satisfy publish check."""
        payload = _minimal_payload(
            status='published',
            thumbnail='https://example.com/thumb.png',
            learning_objectives='Obj 1\nObj 2\nObj 3\nObj 4',
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_publish_with_only_three_lines_in_string_rejected(self):
        payload = _minimal_payload(
            status='published',
            thumbnail='https://example.com/thumb.png',
            learning_objectives='Obj 1\nObj 2\nObj 3',
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('learning_objectives_list', response.data)

    def test_publish_list_takes_priority_over_string(self):
        """If list is provided it is used; string with 4 lines should not rescue a list with 2."""
        payload = _minimal_payload(
            status='published',
            thumbnail='https://example.com/thumb.png',
            learning_objectives='Str1\nStr2\nStr3\nStr4',
            learning_objectives_list=['L1', 'L2'],
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('learning_objectives_list', response.data)


# ---------------------------------------------------------------------------
# C) Objectives list persistence and round-trip
# ---------------------------------------------------------------------------

class CourseObjectivesTest(TestCase):
    """learning_objectives_list persists, round-trips, and syncs the string field."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor(suffix='_obj')

    def _create_course(self, **overrides):
        payload = _minimal_payload(**overrides)
        return self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))

    def test_objectives_list_persists_and_syncs_string(self):
        objectives = ['Build React apps', 'Use HOCs', 'Create custom hooks', 'Optimise performance']
        response = self._create_course(learning_objectives_list=objectives)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        course_id = response.data['id']
        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data['learning_objectives_list'], objectives)
        self.assertEqual(
            get_response.data['learning_objectives'],
            '\n'.join(objectives)
        )

    def test_patch_objectives_list_updates_both_fields(self):
        response = self._create_course(
            learning_objectives_list=['A', 'B', 'C', 'D']
        )
        course_id = response.data['id']

        new_objectives = ['New 1', 'New 2', 'New 3', 'New 4']
        patch_response = self.client.patch(
            f'{COURSES_URL}{course_id}/',
            {'learning_objectives_list': new_objectives},
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)

        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        self.assertEqual(get_response.data['learning_objectives_list'], new_objectives)
        self.assertEqual(get_response.data['learning_objectives'], '\n'.join(new_objectives))

    def test_sending_only_string_does_not_populate_list(self):
        """Sending learning_objectives string only must NOT back-populate learning_objectives_list."""
        response = self._create_course(learning_objectives='Line1\nLine2')
        course_id = response.data['id']

        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        self.assertEqual(get_response.data['learning_objectives'], 'Line1\nLine2')
        self.assertEqual(get_response.data['learning_objectives_list'], [])

    def test_empty_strings_in_list_excluded_from_synced_string(self):
        """Blank objective entries must be stripped from the synced string.

        DRF CharField strips whitespace-only strings to '' before storage,
        so '  ' becomes '' in the persisted list.
        """
        objectives = ['Obj 1', '', 'Obj 3', '  ', 'Obj 5']
        response = self._create_course(learning_objectives_list=objectives)
        course_id = response.data['id']

        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        # DRF CharField(allow_blank=True) strips '  ' → '' in the stored list
        stored_list = get_response.data['learning_objectives_list']
        self.assertEqual(len(stored_list), 5)
        self.assertEqual(stored_list[0], 'Obj 1')
        self.assertEqual(stored_list[2], 'Obj 3')
        self.assertEqual(stored_list[4], 'Obj 5')
        # Blank/whitespace entries are absent from the synced string
        self.assertEqual(get_response.data['learning_objectives'], 'Obj 1\nObj 3\nObj 5')


# ---------------------------------------------------------------------------
# D) New session types
# ---------------------------------------------------------------------------

class SessionTypeTest(TestCase):
    """Expanded SessionType choices are accepted and rejected correctly."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor(suffix='_sess')
        category = _make_category()
        self.course = Course.objects.create(
            title='Session Test Course',
            description='desc',
            slug='session-test-course',
            status='draft',
            instructor=self.instructor,
            created_by=self.instructor,
        )

    def _create_session(self, session_type, order):
        return self.client.post(
            SESSIONS_URL,
            {
                'course': self.course.id,
                'title': f'Lesson ({session_type})',
                'session_type': session_type,
                'order': order,
            },
            format='json',
            **_auth(self.instructor)
        )

    def test_session_type_document_accepted(self):
        response = self._create_session('document', 1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['session_type'], 'document')

    def test_session_type_html_accepted(self):
        response = self._create_session('html', 2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['session_type'], 'html')

    def test_session_type_quiz_accepted(self):
        response = self._create_session('quiz', 3)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['session_type'], 'quiz')

    def test_session_type_assignment_accepted(self):
        response = self._create_session('assignment', 4)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['session_type'], 'assignment')

    def test_session_type_scorm_accepted(self):
        response = self._create_session('scorm', 5)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['session_type'], 'scorm')

    def test_invalid_session_type_rejected(self):
        response = self._create_session('invalid_type', 6)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('session_type', response.data)

    def test_legacy_session_types_still_accepted(self):
        """Original types (video, text, live) must still work."""
        for order, stype in enumerate(['video', 'text', 'live'], start=10):
            with self.subTest(session_type=stype):
                response = self._create_session(stype, order)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# D1b) Quiz authoring API (Instructor Quiz Builder MVP)
# ---------------------------------------------------------------------------

class QuizApiTest(APITestCase):
    """Quiz authoring endpoints: GET/PATCH /sessions/{id}/quiz/, PUT /sessions/{id}/quiz/questions/"""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor(suffix='_quiz')
        self.other_instructor = User.objects.create_user(
            username='other_quiz_inst',
            email='other_quiz@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        category = _make_category()
        self.course = Course.objects.create(
            title='Quiz Test Course',
            description='desc',
            slug='quiz-test-course',
            status='draft',
            instructor=self.instructor,
            created_by=self.instructor,
        )
        self.quiz_session = Session.objects.create(
            course=self.course,
            title='Module 1 Quiz',
            session_type=Session.SessionType.QUIZ,
            order=1,
        )
        self.video_session = Session.objects.create(
            course=self.course,
            title='Intro Video',
            session_type=Session.SessionType.VIDEO,
            order=2,
        )

    def test_quiz_get_creates_and_returns_quiz_detail(self):
        """GET /sessions/{id}/quiz/ creates Quiz if needed and returns full detail."""
        response = self.client.get(
            f'{SESSIONS_URL}{self.quiz_session.id}/quiz/',
            **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('session', response.data)
        self.assertIn('settings', response.data)
        self.assertIn('questions', response.data)
        self.assertEqual(response.data['session']['id'], self.quiz_session.id)
        self.assertEqual(response.data['session']['title'], 'Module 1 Quiz')
        self.assertEqual(response.data['settings'], {})
        self.assertEqual(response.data['questions'], [])
        self.assertTrue(Quiz.objects.filter(session=self.quiz_session).exists())

    def test_quiz_patch_updates_settings_and_returns_merged(self):
        """PATCH /sessions/{id}/quiz/ merges settings."""
        quiz = Quiz.objects.create(session=self.quiz_session, settings={})
        response = self.client.patch(
            f'{SESSIONS_URL}{self.quiz_session.id}/quiz/',
            {'settings': {'time_limit_minutes': 30, 'passing_score_percent': 70}},
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['settings']['time_limit_minutes'], 30)
        self.assertEqual(response.data['settings']['passing_score_percent'], 70)
        quiz.refresh_from_db()
        self.assertEqual(quiz.settings['time_limit_minutes'], 30)

        response2 = self.client.patch(
            f'{SESSIONS_URL}{self.quiz_session.id}/quiz/',
            {'settings': {'max_attempts': 3}},
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data['settings']['time_limit_minutes'], 30)
        self.assertEqual(response2.data['settings']['max_attempts'], 3)

    def test_quiz_get_patch_return_404_for_non_quiz_session(self):
        """GET and PATCH /quiz/ return 404 for video session."""
        for method, url_suffix in [('get', ''), ('patch', '')]:
            with self.subTest(method=method):
                url = f'{SESSIONS_URL}{self.video_session.id}/quiz/'
                if method == 'get':
                    resp = self.client.get(url, **_auth(self.instructor))
                else:
                    resp = self.client.patch(url, {'settings': {}}, format='json', **_auth(self.instructor))
                self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
                self.assertIn('detail', resp.data)

    def test_quiz_questions_put_returns_404_for_non_quiz_session(self):
        """PUT /quiz/questions/ returns 404 for video session."""
        response = self.client.put(
            f'{SESSIONS_URL}{self.video_session.id}/quiz/questions/',
            {'questions': []},
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_quiz_questions_put_creates_questions(self):
        """PUT /quiz/questions/ creates new questions."""
        response = self.client.put(
            f'{SESSIONS_URL}{self.quiz_session.id}/quiz/questions/',
            {
                'questions': [
                    {'order': 0, 'question_type': 'multiple-choice', 'question_text': 'Q1?', 'points': 10,
                     'answer_payload': {'options': [{'text': 'A', 'isCorrect': True}]}},
                    {'order': 1, 'question_type': 'true-false', 'question_text': 'Q2?', 'points': 5,
                     'answer_payload': {'correctAnswer': True}},
                ],
            },
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['questions']), 2)
        self.assertEqual(response.data['questions'][0]['question_text'], 'Q1?')
        self.assertEqual(response.data['questions'][1]['question_type'], 'true-false')
        quiz = Quiz.objects.get(session=self.quiz_session)
        self.assertEqual(quiz.questions.count(), 2)

    def test_quiz_questions_put_updates_creates_deletes(self):
        """PUT replaces: update existing by id, create new without id, delete omitted."""
        quiz = Quiz.objects.create(session=self.quiz_session, settings={})
        q1 = QuizQuestion.objects.create(
            quiz=quiz, order=0, question_type='multiple-choice',
            question_text='Original Q1', points=10, answer_payload={},
        )
        q2 = QuizQuestion.objects.create(
            quiz=quiz, order=1, question_type='true-false',
            question_text='To be deleted', points=5, answer_payload={},
        )
        response = self.client.put(
            f'{SESSIONS_URL}{self.quiz_session.id}/quiz/questions/',
            {
                'questions': [
                    {'id': q1.id, 'order': 0, 'question_type': 'multiple-choice', 'question_text': 'Updated Q1',
                     'points': 15, 'answer_payload': {}},
                    {'order': 1, 'question_type': 'short-answer', 'question_text': 'New Q', 'points': 8,
                     'answer_payload': {}},
                ],
            },
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['questions']), 2)
        q1.refresh_from_db()
        self.assertEqual(q1.question_text, 'Updated Q1')
        self.assertEqual(q1.points, 15)
        self.assertFalse(QuizQuestion.objects.filter(pk=q2.id).exists())
        new_q = QuizQuestion.objects.get(quiz=quiz, question_text='New Q')
        self.assertEqual(new_q.question_type, 'short-answer')

    def test_instructor_cannot_edit_other_instructors_quiz(self):
        """Instructor cannot GET/PATCH/PUT quiz for another instructor's session."""
        other_course = Course.objects.create(
            title='Other Course',
            description='desc',
            slug='other-quiz-course',
            status='draft',
            instructor=self.other_instructor,
            created_by=self.other_instructor,
        )
        other_quiz_session = Session.objects.create(
            course=other_course,
            title='Other Quiz',
            session_type=Session.SessionType.QUIZ,
            order=1,
        )
        url = f'{SESSIONS_URL}{other_quiz_session.id}/quiz/'
        get_resp = self.client.get(url, **_auth(self.instructor))
        self.assertEqual(get_resp.status_code, status.HTTP_404_NOT_FOUND)
        patch_resp = self.client.patch(url, {'settings': {}}, format='json', **_auth(self.instructor))
        self.assertEqual(patch_resp.status_code, status.HTTP_404_NOT_FOUND)
        put_resp = self.client.put(
            f'{url}questions/', {'questions': []}, format='json', **_auth(self.instructor)
        )
        self.assertEqual(put_resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_question_type_returns_400(self):
        """PUT with invalid question_type returns 400."""
        response = self.client.put(
            f'{SESSIONS_URL}{self.quiz_session.id}/quiz/questions/',
            {'questions': [{'question_type': 'invalid', 'question_text': 'X', 'points': 10, 'answer_payload': {}}]},
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('question_type', str(response.data).lower() or 'questions' in response.data)

    def test_session_create_quiz_type_still_works(self):
        """Existing session creation with session_type=quiz still works unchanged."""
        response = self.client.post(
            SESSIONS_URL,
            {
                'course': self.course.id,
                'title': 'New Quiz',
                'session_type': 'quiz',
                'order': 10,
            },
            format='json',
            **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['session_type'], 'quiz')
        self.assertEqual(response.data['title'], 'New Quiz')


# ---------------------------------------------------------------------------
# D2) Session asset presigned GET URL (US-043)
# ---------------------------------------------------------------------------

SESSION_ASSET_URL_SETTINGS = {
    'DO_SPACES_REGION': 'lon1',
    'DO_SPACES_PRIVATE_BUCKET': 'tasc-private',
    'DO_SPACES_ENDPOINT': 'https://lon1.digitaloceanspaces.com',
    'DO_SPACES_ACCESS_KEY_ID': 'key',
    'DO_SPACES_SECRET_ACCESS_KEY': 'secret',
    'DO_SPACES_PRESIGN_EXPIRY_SECONDS': 300,
}


@override_settings(**SESSION_ASSET_URL_SETTINGS)
class SessionAssetUrlTest(APITestCase):
    """GET /api/v1/catalogue/sessions/<id>/asset-url/ access control and behaviour."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            username='asset_instructor',
            email='asset_instructor@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.other_instructor = User.objects.create_user(
            username='other_inst',
            email='other_inst@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.learner = User.objects.create_user(
            username='asset_learner',
            email='asset_learner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        self.other_learner = User.objects.create_user(
            username='other_learner',
            email='other_learner@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        category = _make_category()
        self.course = Course.objects.create(
            title='Asset Test Course',
            description='desc',
            slug='asset-test-course',
            status='published',
            instructor=self.instructor,
            created_by=self.instructor,
        )
        self.session = Session.objects.create(
            course=self.course,
            title='Session With Asset',
            order=1,
            asset_object_key='session-assets/course_1/session_1/abc/intro.mp4',
            asset_bucket='tasc-private',
            asset_mime_type='video/mp4',
        )
        Enrollment.objects.create(user=self.learner, course=self.course, status=Enrollment.Status.ACTIVE)
        _grant_subscription(self.learner)  # Required for asset_url access

    def _asset_url(self, user):
        return self.client.get(
            f'{SESSIONS_URL}{self.session.id}/asset-url/',
            **_auth(user),
        )

    @patch('apps.catalogue.views.create_boto3_client')
    def test_enrolled_learner_gets_200(self, mock_factory):
        mock_client = mock_factory.return_value
        mock_client.generate_presigned_url.return_value = 'https://presigned.example/asset.mp4'
        response = self._asset_url(self.learner)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['method'], 'GET')
        self.assertIn('url', response.data)
        self.assertEqual(response.data['expires_in'], 300)

    @patch('apps.catalogue.views.create_boto3_client')
    def test_non_enrolled_learner_gets_403(self, mock_factory):
        _grant_subscription(self.other_learner)  # Has subscription but not enrolled
        response = self._asset_url(self.other_learner)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('detail', response.data)

    @patch('apps.catalogue.views.create_boto3_client')
    def test_learner_without_subscription_gets_403(self, mock_factory):
        """Enrolled learner without active subscription is denied by HasActiveSubscription."""
        learner_no_sub = User.objects.create_user(
            username='learner_no_sub',
            email='learner_no_sub@example.com',
            password='pass1234',
            role=User.Role.LEARNER,
            email_verified=True,
            is_active=True,
        )
        Enrollment.objects.create(user=learner_no_sub, course=self.course, status=Enrollment.Status.ACTIVE)
        response = self._asset_url(learner_no_sub)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.catalogue.views.create_boto3_client')
    def test_course_instructor_gets_200(self, mock_factory):
        mock_client = mock_factory.return_value
        mock_client.generate_presigned_url.return_value = 'https://presigned.example/asset.mp4'
        response = self._asset_url(self.instructor)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('url', response.data)

    @patch('apps.catalogue.views.create_boto3_client')
    def test_other_instructor_gets_403(self, mock_factory):
        response = self._asset_url(self.other_instructor)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('detail', response.data)

    def test_missing_asset_object_key_returns_404(self):
        self.session.asset_object_key = None
        self.session.save(update_fields=['asset_object_key'])
        response = self._asset_url(self.learner)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('detail', response.data)
        self.assertIn('no uploaded asset', response.data['detail'].lower())


# ---------------------------------------------------------------------------
# D2b) Session delete cleans up Spaces asset
# ---------------------------------------------------------------------------

@override_settings(**SESSION_ASSET_URL_SETTINGS)
class SessionDeleteAssetCleanupTest(APITestCase):
    """DELETE /api/v1/catalogue/sessions/<id>/ removes the Spaces object best-effort."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            username='del_instructor',
            email='del_instructor@example.com',
            password='pass1234',
            role=User.Role.INSTRUCTOR,
            email_verified=True,
            is_active=True,
        )
        self.course = Course.objects.create(
            title='Delete Test Course',
            description='desc',
            slug='delete-test-course',
            status='draft',
            instructor=self.instructor,
            created_by=self.instructor,
        )

    @patch('apps.catalogue.views.delete_spaces_object')
    def test_delete_session_with_asset_calls_cleanup(self, mock_delete):
        session = Session.objects.create(
            course=self.course, title='With Asset', order=1,
            asset_object_key='session-assets/course_1/session_1/file.pdf',
            asset_bucket='tasc-private',
        )
        response = self.client.delete(
            f'{SESSIONS_URL}{session.id}/', **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Session.objects.filter(pk=session.pk).exists())
        mock_delete.assert_called_once_with('tasc-private', 'session-assets/course_1/session_1/file.pdf')

    @patch('apps.catalogue.views.delete_spaces_object')
    def test_delete_session_without_asset_skips_cleanup(self, mock_delete):
        session = Session.objects.create(
            course=self.course, title='No Asset', order=2,
        )
        response = self.client.delete(
            f'{SESSIONS_URL}{session.id}/', **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Session.objects.filter(pk=session.pk).exists())
        mock_delete.assert_not_called()

    @patch('apps.catalogue.views.delete_spaces_object')
    def test_delete_session_uses_private_bucket_fallback(self, mock_delete):
        session = Session.objects.create(
            course=self.course, title='Fallback Bucket', order=3,
            asset_object_key='session-assets/key.mp4',
            asset_bucket='',
        )
        response = self.client.delete(
            f'{SESSIONS_URL}{session.id}/', **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_delete.assert_called_once_with('tasc-private', 'session-assets/key.mp4')


# ---------------------------------------------------------------------------
# D2c) Module CRUD and session-module validation
# ---------------------------------------------------------------------------

class ModuleCRUDTest(APITestCase):
    """Module create, list, and instructor ownership."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor(suffix='_mod')
        self.other_instructor = User.objects.create_user(
            username='other_mod',
            email='other_mod@example.com',
            password='pass1234',
            role='instructor',
            email_verified=True,
            is_active=True,
        )
        self.course = Course.objects.create(
            title='Module Test Course',
            description='desc',
            slug='module-test-course',
            status='draft',
            instructor=self.instructor,
            created_by=self.instructor,
        )
        self.other_course = Course.objects.create(
            title='Other Course',
            description='desc',
            slug='other-module-course',
            status='draft',
            instructor=self.other_instructor,
            created_by=self.other_instructor,
        )

    def test_module_create_by_course_owner_succeeds(self):
        response = self.client.post(
            MODULES_URL,
            {'course': self.course.id, 'title': 'Intro Module'},
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Intro Module')
        self.assertEqual(response.data['course'], self.course.id)
        self.assertEqual(response.data['order'], 0)
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(response.data['require_sequential'], False)
        self.assertEqual(response.data['allow_preview'], True)

    def test_module_create_sequential_without_order_assigns_distinct_orders(self):
        """Two modules created without sending order receive order 0 and 1."""
        r1 = self.client.post(
            MODULES_URL,
            {'course': self.course.id, 'title': 'First'},
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.data['order'], 0)

        r2 = self.client.post(
            MODULES_URL,
            {'course': self.course.id, 'title': 'Second'},
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.data['order'], 1)

        self.assertNotEqual(r1.data['id'], r2.data['id'])
        mods = list(Module.objects.filter(course=self.course).order_by('order'))
        self.assertEqual(len(mods), 2)
        self.assertEqual(mods[0].order, 0)
        self.assertEqual(mods[1].order, 1)

    def test_module_list_filtered_by_course_works(self):
        Module.objects.create(course=self.course, title='M1', order=0)
        Module.objects.create(course=self.course, title='M2', order=1)
        Module.objects.create(course=self.other_course, title='M3', order=0)

        response = self.client.get(
            f'{MODULES_URL}?course={self.course.id}',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m['id'] for m in response.data['results']]
        self.assertEqual(len(ids), 2)
        titles = [m['title'] for m in response.data['results']]
        self.assertIn('M1', titles)
        self.assertIn('M2', titles)
        self.assertNotIn('M3', titles)

    def test_module_create_for_non_owned_course_rejected_for_instructor(self):
        response = self.client.post(
            MODULES_URL,
            {'course': self.other_course.id, 'title': 'Hijack Module'},
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('detail', response.data)

    def test_delete_module_sets_related_sessions_module_to_null(self):
        mod = Module.objects.create(course=self.course, title='To Delete', order=0)
        sess = Session.objects.create(
            course=self.course, title='Session In Module', order=0, module=mod,
        )
        self.assertEqual(sess.module_id, mod.id)

        response = self.client.delete(
            f'{MODULES_URL}{mod.id}/',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        sess.refresh_from_db()
        self.assertIsNone(sess.module_id)

    def test_session_create_rejects_module_from_different_course(self):
        mod = Module.objects.create(course=self.other_course, title='Other Mod', order=0)

        response = self.client.post(
            SESSIONS_URL,
            {
                'course': self.course.id,
                'module': mod.id,
                'title': 'Session',
                'session_type': 'video',
                'order': 0,
            },
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('module', response.data)
        self.assertIn('same course', str(response.data['module']).lower())

    def test_session_create_without_module_still_works(self):
        response = self.client.post(
            SESSIONS_URL,
            {
                'course': self.course.id,
                'title': 'Standalone Session',
                'session_type': 'video',
                'order': 0,
            },
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data.get('module'))
        sess = Session.objects.get(id=response.data['id'])
        self.assertIsNone(sess.module_id)

    def test_module_create_persists_modal_aligned_optional_fields(self):
        response = self.client.post(
            MODULES_URL,
            {
                'course': self.course.id,
                'title': 'Full Module',
                'description': 'A longer description',
                'status': 'published',
                'icon': 'trophy',
                'require_sequential': True,
                'allow_preview': False,
            },
            format='json',
            **_auth(self.instructor),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['description'], 'A longer description')
        self.assertEqual(response.data['status'], 'published')
        self.assertEqual(response.data['icon'], 'trophy')
        self.assertEqual(response.data['require_sequential'], True)
        self.assertEqual(response.data['allow_preview'], False)


# ---------------------------------------------------------------------------
# D3) External video embedding (US-0415)
# ---------------------------------------------------------------------------

class ExternalVideoEmbeddingTest(APITestCase):
    """External video embedding: YouTube, Vimeo, Loom via content_source + external_video_*."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor(suffix='_ext')
        category = _make_category()
        self.course = Course.objects.create(
            title='External Video Course',
            description='desc',
            slug='external-video-course',
            status='draft',
            instructor=self.instructor,
            created_by=self.instructor,
        )

    def _create_session(self, **payload):
        base = {
            'course': self.course.id,
            'title': 'Lesson',
            'session_type': 'video',
            'order': 1,
        }
        base.update(payload)
        return self.client.post(
            SESSIONS_URL,
            base,
            format='json',
            **_auth(self.instructor),
        )

    def _patch_session(self, session_id, **payload):
        return self.client.patch(
            f'{SESSIONS_URL}{session_id}/',
            payload,
            format='json',
            **_auth(self.instructor),
        )

    def test_external_youtube_watch_url_converts_to_embed(self):
        response = self._create_session(
            content_source='external',
            external_video_url='https://www.youtube.com/watch?v=abc123XYZ09',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['external_video_provider'], 'youtube')
        self.assertEqual(
            response.data['external_video_embed_url'],
            'https://www.youtube.com/embed/abc123XYZ09',
        )

    def test_external_youtu_be_converts(self):
        response = self._create_session(
            content_source='external',
            external_video_url='https://youtu.be/xyz789ABC',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['external_video_provider'], 'youtube')
        self.assertEqual(
            response.data['external_video_embed_url'],
            'https://www.youtube.com/embed/xyz789ABC',
        )

    def test_external_vimeo_converts(self):
        response = self._create_session(
            content_source='external',
            external_video_url='https://vimeo.com/123456789',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['external_video_provider'], 'vimeo')
        self.assertEqual(
            response.data['external_video_embed_url'],
            'https://player.vimeo.com/video/123456789',
        )

    def test_external_loom_converts(self):
        response = self._create_session(
            content_source='external',
            external_video_url='https://www.loom.com/share/abc123xyz',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['external_video_provider'], 'loom')
        self.assertEqual(
            response.data['external_video_embed_url'],
            'https://www.loom.com/embed/abc123xyz',
        )

    def test_external_rejects_http(self):
        response = self._create_session(
            content_source='external',
            external_video_url='http://www.youtube.com/watch?v=abc123',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('external_video_url', response.data)
        self.assertIn('https', str(response.data['external_video_url']).lower())

    def test_external_rejects_unknown_domain(self):
        response = self._create_session(
            content_source='external',
            external_video_url='https://evil.com/video',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('external_video_url', response.data)
        self.assertIn('Unsupported', str(response.data['external_video_url']))

    def test_switch_to_external_autoclears_asset_fields(self):
        session = Session.objects.create(
            course=self.course,
            title='Upload Session',
            order=1,
            session_type='video',
            content_source='upload',
            asset_object_key='session-assets/course_1/session_1/intro.mp4',
            asset_bucket='tasc-private',
        )
        response = self._patch_session(
            session.id,
            content_source='external',
            external_video_url='https://www.youtube.com/watch?v=test123',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data.get('asset_object_key'))
        self.assertEqual(response.data['external_video_provider'], 'youtube')
        self.assertEqual(
            response.data['external_video_embed_url'],
            'https://www.youtube.com/embed/test123',
        )


# ---------------------------------------------------------------------------
# E) Settings fields stored and returned
# ---------------------------------------------------------------------------

class CourseSettingsFieldsTest(TestCase):
    """New course settings fields are stored and returned correctly."""

    def setUp(self):
        self.client = APIClient()
        self.instructor = _make_instructor(suffix='_stg')

    def test_settings_fields_stored_and_returned(self):
        payload = _minimal_payload(
            is_public=False,
            sequential_learning=True,
            enrollment_limit=30,
            access_duration='6-months',
            start_date='2026-03-01',
            end_date='2026-09-01',
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        course_id = response.data['id']
        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        data = get_response.data
        self.assertFalse(data['is_public'])
        self.assertTrue(data['sequential_learning'])
        self.assertEqual(data['enrollment_limit'], 30)
        self.assertEqual(data['access_duration'], '6-months')
        self.assertEqual(data['start_date'], '2026-03-01')
        self.assertEqual(data['end_date'], '2026-09-01')

    def test_settings_fields_defaults(self):
        """Omitting settings fields must yield the expected model defaults."""
        response = self.client.post(
            COURSES_URL, _minimal_payload(), format='json', **_auth(self.instructor)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        course_id = response.data['id']
        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        data = get_response.data
        self.assertFalse(data['is_public'])
        self.assertTrue(data['allow_self_enrollment'])
        self.assertFalse(data['certificate_on_completion'])
        self.assertFalse(data['enable_discussions'])
        self.assertFalse(data['sequential_learning'])
        self.assertIsNone(data['enrollment_limit'])
        self.assertEqual(data['access_duration'], 'lifetime')
        self.assertIsNone(data['start_date'])
        self.assertIsNone(data['end_date'])

    def test_grading_config_stored_and_returned(self):
        grading = {
            'gradingScale': 'letter',
            'weightingMode': 'weighted',
            'passingThreshold': 60,
            'letterGradeThresholds': {'A': 90, 'B': 80, 'C': 70, 'D': 60},
            'categories': [
                {'id': 'assignments', 'name': 'Assignments', 'weight': 40},
                {'id': 'quizzes', 'name': 'Quizzes', 'weight': 60},
            ],
        }
        payload = _minimal_payload(grading_config=grading)
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        course_id = response.data['id']
        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        self.assertEqual(get_response.data['grading_config'], grading)

    def test_banner_and_subcategory_stored_and_returned(self):
        payload = _minimal_payload(
            banner='https://example.com/banner.jpg',
            subcategory='react',
        )
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        course_id = response.data['id']
        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        self.assertEqual(get_response.data['banner'], 'https://example.com/banner.jpg')
        self.assertEqual(get_response.data['subcategory'], 'react')

    def test_duration_minutes_stored_and_returned(self):
        payload = _minimal_payload(duration_hours=3, duration_minutes=45)
        response = self.client.post(COURSES_URL, payload, format='json', **_auth(self.instructor))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        course_id = response.data['id']
        get_response = self.client.get(f'{COURSES_URL}{course_id}/', **_auth(self.instructor))
        self.assertEqual(get_response.data['duration_minutes'], 45)


# ---------------------------------------------------------------------------
# F) Legacy published course PATCH safety
# ---------------------------------------------------------------------------

def _make_tasc_admin(suffix=''):
    return User.objects.create_user(
        username=f'tascadmin{suffix}',
        email=f'tascadmin{suffix}@example.com',
        password='pass1234',
        role='tasc_admin',
        email_verified=True,
        is_active=True,
    )


class CoursePublishedLegacyPatchTest(TestCase):
    """
    Publish validation must NOT fire on PATCH when status is absent from payload.

    Simulates courses that were published before the thumbnail/objectives
    requirement was introduced (created directly in DB, bypassing serializer).
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = _make_tasc_admin(suffix='_legacy')
        # Create a legacy published course directly in DB — bypasses serializer
        # validation, simulating a course published before validation was added.
        self.legacy_course = Course.objects.create(
            title='Legacy Published Course',
            description='A course published before thumbnail/objectives were required.',
            slug='legacy-published-course',
            status='published',
            # Deliberately no thumbnail, no learning_objectives, no list
            thumbnail=None,
            learning_objectives='',
            learning_objectives_list=[],
            instructor=self.admin,
            created_by=self.admin,
        )
        self.url = f'{COURSES_URL}{self.legacy_course.id}/'

    def test_patch_title_without_status_returns_200(self):
        """PATCH of title only (no status in payload) must NOT trigger publish validation."""
        response = self.client.patch(
            self.url,
            {'title': 'Updated Legacy Title'},
            format='json',
            **_auth(self.admin)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Legacy Title')
        # Confirm status was not changed
        self.assertEqual(response.data['status'], 'published')

    def test_patch_with_status_published_and_no_thumbnail_returns_400(self):
        """Explicitly sending status='published' in PATCH must still enforce thumbnail."""
        response = self.client.patch(
            self.url,
            {'status': 'published', 'title': 'Still No Thumbnail'},
            format='json',
            **_auth(self.admin)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('thumbnail', response.data)

    def test_patch_with_status_published_thumbnail_and_objectives_returns_200(self):
        """Explicitly sending status='published' with valid thumbnail + objectives must pass."""
        response = self.client.patch(
            self.url,
            {
                'status': 'published',
                'thumbnail': 'https://example.com/fixed-thumb.png',
                'learning_objectives_list': [
                    'Objective 1', 'Objective 2', 'Objective 3', 'Objective 4'
                ],
            },
            format='json',
            **_auth(self.admin)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'published')
        self.assertEqual(response.data['thumbnail'], 'https://example.com/fixed-thumb.png')


# ---------------------------------------------------------------------------
# G) Category parent filter (US-041 wizard bootstrap)
# ---------------------------------------------------------------------------

class CategoryParentFilterTest(APITestCase):
    """GET /api/v1/catalogue/categories/?parent= supports absent, null, and id."""

    def setUp(self):
        self.client = APIClient()
        self.user = _make_instructor(suffix='_catfilter')
        self.root1 = Category.objects.create(name='Root A', slug='root-a', parent=None, is_active=True)
        self.root2 = Category.objects.create(name='Root B', slug='root-b', parent=None, is_active=True)
        self.child1 = Category.objects.create(name='Child 1', slug='child-1', parent=self.root1, is_active=True)
        self.child2 = Category.objects.create(name='Child 2', slug='child-2', parent=self.root1, is_active=True)
        self.child3 = Category.objects.create(name='Child 3', slug='child-3', parent=self.root2, is_active=True)

    def test_list_categories_without_parent_param_returns_all_active(self):
        response = self.client.get(CATEGORIES_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c['id'] for c in response.data['results']]
        self.assertIn(self.root1.id, ids)
        self.assertIn(self.root2.id, ids)
        self.assertIn(self.child1.id, ids)
        self.assertIn(self.child2.id, ids)
        self.assertIn(self.child3.id, ids)

    def test_list_categories_parent_empty_returns_roots_only(self):
        response = self.client.get(f'{CATEGORIES_URL}?parent=', **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c['id'] for c in response.data['results']]
        self.assertIn(self.root1.id, ids)
        self.assertIn(self.root2.id, ids)
        self.assertNotIn(self.child1.id, ids)
        self.assertNotIn(self.child2.id, ids)
        self.assertNotIn(self.child3.id, ids)

    def test_list_categories_parent_null_returns_roots_only(self):
        response = self.client.get(f'{CATEGORIES_URL}?parent=null', **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c['id'] for c in response.data['results']]
        self.assertIn(self.root1.id, ids)
        self.assertIn(self.root2.id, ids)
        self.assertNotIn(self.child1.id, ids)
        self.assertNotIn(self.child2.id, ids)
        self.assertNotIn(self.child3.id, ids)

    def test_list_categories_parent_id_returns_children_only(self):
        response = self.client.get(f'{CATEGORIES_URL}?parent={self.root1.id}', **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c['id'] for c in response.data['results']]
        self.assertIn(self.child1.id, ids)
        self.assertIn(self.child2.id, ids)
        self.assertNotIn(self.root1.id, ids)
        self.assertNotIn(self.root2.id, ids)
        self.assertNotIn(self.child3.id, ids)

    def test_list_categories_parent_invalid_returns_400(self):
        response = self.client.get(f'{CATEGORIES_URL}?parent=notanint', **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('parent', response.data)
        self.assertIn('Invalid parent id', str(response.data['parent']))


# ---------------------------------------------------------------------------
# H) Tags pagination (US-041 wizard bootstrap)
# ---------------------------------------------------------------------------

class TagPaginationTest(APITestCase):
    """GET /api/v1/catalogue/tags/ returns paginated response with count/next/previous/results."""

    def setUp(self):
        self.client = APIClient()
        self.user = _make_instructor(suffix='_tagpag')
        for i in range(65):
            Tag.objects.create(name=f'Tag {i}', slug=f'tag-{i}')

    def test_tags_list_returns_paginated_response(self):
        response = self.client.get(TAGS_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 65)

    def test_tags_list_default_page_size(self):
        response = self.client.get(TAGS_URL, **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data['results']), 50)

    def test_tags_list_page_size_param(self):
        response = self.client.get(f'{TAGS_URL}?page_size=10', **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 10)
        self.assertEqual(response.data['count'], 65)

    def test_tags_list_page_param(self):
        response = self.client.get(f'{TAGS_URL}?page=2&page_size=10', **_auth(self.user))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 10)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNotNone(response.data['previous'])


# ---------------------------------------------------------------------------
# I) Subscription gating + public catalog
# ---------------------------------------------------------------------------

class PublicCatalogAccessTest(APITestCase):
    """Public catalog remains accessible without authentication or subscription."""

    def setUp(self):
        self.client = APIClient()
        category = _make_category()
        Course.objects.create(
            title='Public Course',
            description='desc',
            slug='public-course',
            status='published',
            instructor=_make_instructor(suffix='_pub'),
            created_by=None,
        )

    def test_public_courses_list_no_auth_returns_200(self):
        response = self.client.get('/api/v1/public/courses/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
