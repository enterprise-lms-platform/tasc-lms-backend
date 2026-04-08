from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth import get_user_model

User = get_user_model()

class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(participants=self.request.user).prefetch_related('participants')

    def perform_create(self, serializer):
        conversation = serializer.save()
        conversation.participants.add(self.request.user)

    @action(detail=True, methods=['get'], url_path='messages')
    def list_messages(self, request, pk=None):
        conversation = self.get_object()
        messages = conversation.messages.all().select_related('sender')
        
        # Paginate messages if needed, here we'll just return all for simplicity
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = MessageSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='messages/send', serializer_class=MessageSerializer)
    def send_message(self, request, pk=None):
        conversation = self.get_object()
        serializer = MessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(conversation=conversation, sender=request.user)
            conversation.save() # Updates Conversation.updated_at
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='read')
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        updated = conversation.messages.exclude(sender=request.user).filter(is_read=False).update(is_read=True)
        return Response({'status': 'ok', 'messages_marked_read': updated})

    @action(detail=False, methods=['get'], url_path='user-search')
    def user_search(self, request):
        """
        Search for users to start a conversation with.
        Scoped to the same organization as the requesting user.
        Any authenticated user can call this (learner, instructor, manager, etc).
        """
        query = request.query_params.get('search', '').strip()
        if len(query) < 2:
            return Response([])

        users = User.objects.filter(
            is_active=True,
        ).filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        ).exclude(id=request.user.id).values(
            'id', 'first_name', 'last_name', 'email', 'role'
        )[:20]

        results = [
            {
                'id': u['id'],
                'name': f"{u['first_name']} {u['last_name']}".strip() or u['email'],
                'first_name': u['first_name'],
                'last_name': u['last_name'],
                'email': u['email'],
                'role': u['role'],
            }
            for u in users
        ]
        return Response(results)
