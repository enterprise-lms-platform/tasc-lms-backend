from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from .models import Notification
from .serializers import (
    NotificationSerializer,
    NotificationListSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary='List notifications',
        description='Returns list of notifications for the authenticated user',
        parameters=[
            OpenApiParameter(name='is_read', type=bool, description='Filter by read status'),
            OpenApiParameter(name='type', type=str, description='Filter by notification type'),
        ],
    ),
    retrieve=extend_schema(
        summary='Get notification',
        description='Returns notification details by ID',
    ),
    destroy=extend_schema(
        summary='Delete notification',
        description='Delete a notification',
    ),
)
class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user notifications.
    Supports:
    - Listing notifications
    - Marking as read
    - Marking all as read
    """
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return NotificationListSerializer
        return NotificationSerializer
    
    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)
        
        # Filter by read status
        is_read = self.request.query_params.get('is_read', None)
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')
        
        # Filter by type
        notification_type = self.request.query_params.get('type', None)
        if notification_type:
            queryset = queryset.filter(type=notification_type)
        
        # Filter by date range
        created_after = self.request.query_params.get('created_after')
        created_before = self.request.query_params.get('created_before')
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        
        return queryset
    
    @extend_schema(
        summary='Mark notification as read',
        description='Mark a single notification as read',
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a single notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Mark all as read',
        description='Mark all notifications as read',
        responses={200: {'description': 'Number of notifications marked as read'}},
    )
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        queryset = self.get_queryset()
        updated_count = queryset.filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return Response({
            'message': f'{updated_count} notifications marked as read',
            'count': updated_count
        })
    
    @extend_schema(
        summary='Unread count',
        description='Get count of unread notifications',
        responses={200: {'description': 'Unread notifications count'}},
    )
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        return Response({'unread_count': count})
    
    @extend_schema(
        summary='Bulk delete notifications',
        description='Delete multiple notifications by their IDs',
        responses={200: {'description': 'Number of notifications deleted'}},
    )
    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """POST /api/v1/notifications/bulk-delete/  body: { "ids": [1,2,3] }"""
        ids = request.data.get('ids', [])
        deleted = Notification.objects.filter(
            id__in=ids, user=request.user
        ).delete()[0]
        return Response({'deleted': deleted})
