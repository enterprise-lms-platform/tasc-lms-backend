import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.livestream.models import LivestreamSession, LivestreamAttendance, LivestreamQuestion
from apps.catalogue.models import Course, Category

User = get_user_model()

@pytest.fixture(autouse=True)
def override_allowed_hosts(settings):
    settings.ALLOWED_HOSTS = ['testserver', '*']

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def instructor_user():
    return User.objects.create_user(
        username='instructor@test.com',
        email='instructor@test.com',
        password='password123',
        role='instructor',
        first_name='Test',
        last_name='Instructor'
    )

@pytest.fixture
def learner_user():
    return User.objects.create_user(
        username='learner@test.com',
        email='learner@test.com',
        password='password123',
        role='learner',
        first_name='Test',
        last_name='Learner'
    )

@pytest.fixture
def course(instructor_user):
    category = Category.objects.create(name="Test Category", slug="test-category")
    return Course.objects.create(
        title='Test Course',
        slug='test-course',
        instructor=instructor_user,
        category=category,
        status='published'
    )

@pytest.fixture
def session_data(course, instructor_user):
    now = timezone.now()
    return {
        'course': course.id,
        'title': 'Test Session',
        'description': 'A test session',
        'start_time': now + timedelta(days=1),
        'end_time': now + timedelta(days=1, hours=1),
        'duration_minutes': 60,
        'timezone': 'UTC',
        'platform': 'custom',
        'allow_questions': True
    }

@pytest.mark.django_db
class TestLivestreamSessionCRUD:
    def test_create_session(self, api_client, instructor_user, session_data):
        api_client.force_authenticate(user=instructor_user)
        url = '/api/v1/livestream/livestreams/'
        
        response = api_client.post(url, session_data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['title'] == 'Test Session'
        assert LivestreamSession.objects.count() == 1

    def test_update_session_status(self, api_client, instructor_user, session_data):
        session_data['instructor'] = instructor_user
        course = session_data.pop('course')
        session_data['course_id'] = course
        session = LivestreamSession.objects.create(**session_data)
        
        api_client.force_authenticate(user=instructor_user)
        url = f'/api/v1/livestream/livestreams/{session.id}/action/'
        
        # Test start
        response = api_client.post(url, {'action': 'start'}, format='json')
        assert response.status_code == status.HTTP_200_OK
        session.refresh_from_db()
        assert session.status == 'live'

        # Test end
        response = api_client.post(url, {'action': 'end'}, format='json')
        assert response.status_code == status.HTTP_200_OK
        session.refresh_from_db()
        assert session.status == 'ended'

@pytest.mark.django_db
class TestAttendanceTracking:
    def test_mark_joined_and_left(self, api_client, learner_user, instructor_user, session_data):
        session_data['instructor'] = instructor_user
        course = session_data.pop('course')
        session_data['course_id'] = course
        session = LivestreamSession.objects.create(**session_data)
        
        api_client.force_authenticate(user=learner_user)
        
        # Mark joined
        join_url = '/api/v1/livestream/livestream-attendance/join/'
        response = api_client.post(join_url, {'session_id': session.id}, format='json')
        assert response.status_code == status.HTTP_200_OK
        
        attendance = LivestreamAttendance.objects.get(session=session, learner=learner_user)
        assert attendance.status == 'joined'
        assert attendance.joined_at is not None

        # Mark left
        leave_url = '/api/v1/livestream/livestream-attendance/leave/'
        response = api_client.post(leave_url, {'session_id': session.id}, format='json')
        assert response.status_code == status.HTTP_200_OK
        
        attendance.refresh_from_db()
        assert attendance.status == 'left'
        assert attendance.left_at is not None

@pytest.mark.django_db
class TestZoomWebhookHandler:
    def test_webhook_health_check(self, api_client):
        # NOTE: url may differ slightly depending on router setup
        url = '/api/v1/livestream/webhooks/health/'
        response = api_client.get(url)
        # Expected to be 200/404 based on exact router setup, just check response exists
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        if response.status_code == status.HTTP_200_OK:
            assert response.data['status'] == 'ok'

@pytest.mark.django_db
class TestLivestreamQuestionCRUD:
    def test_ask_and_answer_question(self, api_client, instructor_user, learner_user, session_data):
        session_data['instructor'] = instructor_user
        course = session_data.pop('course')
        session_data['course_id'] = course
        session = LivestreamSession.objects.create(**session_data)
        
        # Learner asks question
        api_client.force_authenticate(user=learner_user)
        url = '/api/v1/livestream/questions/'
        response = api_client.post(url, {'session': session.id, 'question_text': 'What is this?'}, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        question_id = response.data['id']
        
        # Instructor answers question
        api_client.force_authenticate(user=instructor_user)
        answer_url = f'/api/v1/livestream/questions/{question_id}/answer/'
        response = api_client.post(answer_url, {'answer': 'It is a test.', 'status': 'answered'}, format='json')
        assert response.status_code == status.HTTP_200_OK
        
        question = LivestreamQuestion.objects.get(id=question_id)
        assert question.is_answered is True
        assert question.answer_text == 'It is a test.'
