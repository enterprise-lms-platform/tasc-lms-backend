"""
Badge serializers for the learning app.
"""
from rest_framework import serializers
from apps.learning.models import Badge, UserBadge


class BadgeSerializer(serializers.ModelSerializer):
    """Serializer for badge definitions."""

    class Meta:
        model = Badge
        fields = [
            'id', 'slug', 'name', 'description', 'icon_url',
            'category', 'criteria_type', 'criteria_value', 'order',
        ]


class UserBadgeSerializer(serializers.ModelSerializer):
    """Serializer for a user's earned badge."""
    badge = BadgeSerializer(read_only=True)

    class Meta:
        model = UserBadge
        fields = ['id', 'badge', 'earned_at']
