from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import (
    Enrollment, SessionProgress, Certificate, Discussion, DiscussionReply
)
from apps.catalogue.models import Course, Session


class EnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for Enrollment model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    course_thumbnail = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    time_remaining_days = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'user', 'user_name', 'user_email',
            'course', 'course_title', 'course_thumbnail',
            'organization', 'organization_name',
            'status', 'enrolled_at', 'completed_at', 'expires_at',
            'progress_percentage', 'last_accessed_at', 'last_accessed_session',
            'paid_amount', 'currency',
            'certificate_issued', 'certificate_issued_at',
            'time_remaining_days'
        ]
        read_only_fields = ['id', 'enrolled_at', 'progress_percentage', 'last_accessed_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_course_title(self, obj):
        return obj.course.title
    
    def get_course_thumbnail(self, obj):
        return obj.course.thumbnail
    
    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None
    
    def get_time_remaining_days(self, obj):
        if obj.expires_at:
            remaining = obj.expires_at - timezone.now()
            return max(remaining.days, 0)
        return None


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating enrollments."""
    
    class Meta:
        model = Enrollment
        fields = [
            'course', 'organization', 'paid_amount', 'currency'
        ]
    
    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class SessionProgressSerializer(serializers.ModelSerializer):
    """Serializer for SessionProgress model."""
    session_title = serializers.SerializerMethodField()
    session_type = serializers.SerializerMethodField()
    duration_minutes = serializers.SerializerMethodField()
    time_spent_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = SessionProgress
        fields = [
            'id', 'enrollment', 'session', 'session_title', 'session_type',
            'is_started', 'started_at', 'is_completed', 'completed_at',
            'time_spent_seconds', 'time_spent_minutes', 'last_accessed_at',
            'notes', 'duration_minutes'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'last_accessed_at']
    
    def get_session_title(self, obj):
        return obj.session.title
    
    def get_session_type(self, obj):
        return obj.session.session_type
    
    def get_duration_minutes(self, obj):
        return obj.session.video_duration_seconds // 60 if obj.session.video_duration_seconds else 0
    
    def get_time_spent_minutes(self, obj):
        return obj.time_spent_seconds // 60


class SessionProgressCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating session progress."""
    
    class Meta:
        model = SessionProgress
        fields = [
            'session', 'is_started', 'is_completed',
            'time_spent_seconds', 'notes'
        ]


class CertificateSerializer(serializers.ModelSerializer):
    """Serializer for Certificate model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = Certificate
        fields = [
            'id', 'enrollment',
            'user_name', 'user_email', 'course_title',
            'certificate_number', 'issued_at', 'expiry_date',
            'is_valid', 'is_expired',
            'pdf_url', 'verification_url'
        ]
        read_only_fields = ['id', 'certificate_number', 'issued_at']
    
    def get_user_name(self, obj):
        return obj.enrollment.user.get_full_name() or obj.enrollment.user.email
    
    def get_user_email(self, obj):
        return obj.enrollment.user.email
    
    def get_course_title(self, obj):
        return obj.enrollment.course.title


class CertificateCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating certificates."""
    
    class Meta:
        model = Certificate
        fields = ['expiry_date']


class DiscussionSerializer(serializers.ModelSerializer):
    """Serializer for Discussion model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    session_title = serializers.SerializerMethodField()
    reply_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Discussion
        fields = [
            'id', 'user', 'user_name', 'user_email', 'user_avatar',
            'course', 'course_title', 'session', 'session_title',
            'title', 'content',
            'is_pinned', 'is_locked', 'is_deleted',
            'reply_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_user_avatar(self, obj):
        return obj.user.avatar
    
    def get_course_title(self, obj):
        return obj.course.title if obj.course else None
    
    def get_session_title(self, obj):
        return obj.session.title if obj.session else None


class DiscussionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating discussions."""
    
    class Meta:
        model = Discussion
        fields = [
            'course', 'session', 'title', 'content'
        ]


class DiscussionReplySerializer(serializers.ModelSerializer):
    """Serializer for DiscussionReply model."""
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = DiscussionReply
        fields = [
            'id', 'discussion', 'user', 'user_name', 'user_email', 'user_avatar',
            'parent', 'content', 'is_deleted',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_user_avatar(self, obj):
        return obj.user.avatar


class DiscussionReplyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating discussion replies."""
    
    class Meta:
        model = DiscussionReply
        fields = [
            'discussion', 'parent', 'content'
        ]


class SessionProgressUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating session progress."""
    
    class Meta:
        model = SessionProgress
        fields = [
            'is_completed', 'time_spent_seconds'
        ]