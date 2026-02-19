"""Serializers for audit log API."""

from rest_framework import serializers


class AuditLogListSerializer(serializers.Serializer):
    """Response shape matching frontend needs."""

    id = serializers.IntegerField()
    timestamp = serializers.DateTimeField(source="created_at")
    user = serializers.CharField(source="actor_name")
    email = serializers.CharField(source="actor_email")
    action = serializers.CharField()
    resource = serializers.CharField()
    details = serializers.CharField()
    ip = serializers.IPAddressField(source="ip_address", allow_null=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Format timestamp as ISO string
        data["timestamp"] = instance.created_at.isoformat()
        # Title case for action and resource
        data["action"] = instance.action.title()
        data["resource"] = instance.resource.title()
        return data
