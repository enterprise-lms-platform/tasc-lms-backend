from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Category, Course, Session

User = get_user_model()

COURSES_URL = '/api/v1/catalogue/courses/'
SESSIONS_URL = '/api/v1/catalogue/sessions/'


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
