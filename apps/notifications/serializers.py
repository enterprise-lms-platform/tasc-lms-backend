from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'title', 'description',
            'is_read', 'link', 'created_at', 'read_at'
        ]
        read_only_fields = ['id', 'created_at']


class NotificationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'title', 'description',
            'is_read', 'link', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
