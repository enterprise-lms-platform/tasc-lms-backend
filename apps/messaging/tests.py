import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.messaging.models import Conversation, Message

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user1():
    return User.objects.create_user(username='user1', email='user1@test.com', password='password123')

@pytest.fixture
def user2():
    return User.objects.create_user(username='user2', email='user2@test.com', password='password123')


@pytest.mark.django_db
class TestMessagingAPI:
    def test_create_and_list_conversations(self, api_client, user1, user2):
        api_client.force_authenticate(user=user1)
        
        # Create
        response = api_client.post('/api/v1/messaging/conversations/', {'participants': [user2.id]}, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        conv_id = response.data['id']
        
        # List
        response = api_client.get('/api/v1/messaging/conversations/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['id'] == conv_id

    def test_send_and_list_messages(self, api_client, user1, user2):
        conv = Conversation.objects.create()
        conv.participants.add(user1, user2)
        
        api_client.force_authenticate(user=user1)
        
        # Send
        response = api_client.post(f'/api/v1/messaging/conversations/{conv.id}/messages/send/', {'content': 'Hello user2!'}, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['content'] == 'Hello user2!'
        
        # List
        response = api_client.get(f'/api/v1/messaging/conversations/{conv.id}/messages/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_mark_read(self, api_client, user1, user2):
        conv = Conversation.objects.create()
        conv.participants.add(user1, user2)
        Message.objects.create(conversation=conv, sender=user1, content='Hello!')
        
        # user2 marks as read
        api_client.force_authenticate(user=user2)
        response = api_client.post(f'/api/v1/messaging/conversations/{conv.id}/read/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['messages_marked_read'] == 1
        
        assert Message.objects.filter(is_read=True).count() == 1
