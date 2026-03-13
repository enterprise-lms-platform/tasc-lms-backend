from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta
from .models import (
    Enrollment, SessionProgress, Certificate, Discussion, DiscussionReply,
    Submission,
)
from apps.catalogue.models import Course, Session
from apps.accounts.rbac import is_admin_like, is_instructor
from apps.payments.permissions import user_has_active_subscription


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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context['request'].user
        # Bypass for admin-like and instructors
        if is_admin_like(user) or is_instructor(user):
            return attrs
        if not user_has_active_subscription(user):
            raise PermissionDenied('An active subscription is required to enroll in courses.')
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        course = validated_data['course']
        defaults = {
            'organization': validated_data.get('organization'),
            'paid_amount': validated_data.get('paid_amount', 0),
            'currency': validated_data.get('currency', 'USD'),
        }
        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults=defaults,
        )
        self._created = created
        return enrollment


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


# -----------------------------------------------------------------------------
# Submission serializers
# -----------------------------------------------------------------------------

class SubmissionSerializer(serializers.ModelSerializer):
    """Read serializer for Submission (list/detail)."""
    assignment_title = serializers.SerializerMethodField()
    session_title = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    graded_by_name = serializers.SerializerMethodField()
    max_points = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            'id', 'enrollment', 'assignment',
            'assignment_title', 'session_title', 'max_points',
            'status', 'submitted_at',
            'submitted_text', 'submitted_file_url', 'submitted_file_name',
            'grade', 'feedback', 'internal_notes',
            'graded_at', 'graded_by', 'graded_by_name',
            'user_name', 'user_email',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_assignment_title(self, obj):
        return obj.assignment.session.title if obj.assignment and obj.assignment.session else None

    def get_session_title(self, obj):
        return obj.assignment.session.title if obj.assignment and obj.assignment.session else None

    def get_user_name(self, obj):
        return obj.enrollment.user.get_full_name() or obj.enrollment.user.email

    def get_user_email(self, obj):
        return obj.enrollment.user.email

    def get_graded_by_name(self, obj):
        return (obj.graded_by.get_full_name() or obj.graded_by.email) if obj.graded_by else None

    def get_max_points(self, obj):
        return obj.assignment.max_points if obj.assignment else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            role = getattr(request.user, 'role', None)
            if role not in (User.Role.INSTRUCTOR, User.Role.LMS_MANAGER, User.Role.TASC_ADMIN):
                data.pop('internal_notes', None)
        return data


class SubmissionCreateSerializer(serializers.ModelSerializer):
    """Create serializer for Submission."""

    class Meta:
        model = Submission
        fields = ['enrollment', 'assignment', 'status', 'submitted_text', 'submitted_file_url', 'submitted_file_name']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError('Authentication required.')

        enrollment = attrs.get('enrollment')
        assignment = attrs.get('assignment')

        if enrollment.user_id != request.user.id:
            raise serializers.ValidationError({'enrollment': 'You can only create submissions for your own enrollments.'})

        if assignment.session.course_id != enrollment.course_id:
            raise serializers.ValidationError({'assignment': 'Assignment does not belong to this enrollment\'s course.'})

        if Submission.objects.filter(enrollment=enrollment, assignment=assignment).exists():
            raise serializers.ValidationError(
                {'non_field_errors': ['A submission already exists for this enrollment and assignment.']}
            )

        status_val = attrs.get('status', Submission.Status.DRAFT)
        if status_val == Submission.Status.SUBMITTED:
            text = attrs.get('submitted_text', '').strip()
            file_url = attrs.get('submitted_file_url')
            if not text and not file_url:
                raise serializers.ValidationError(
                    {'non_field_errors': ['Submitted text or file URL is required when submitting.']}
                )

        return attrs

    def create(self, validated_data):
        status_val = validated_data.get('status', Submission.Status.DRAFT)
        submitted_at = timezone.now() if status_val == Submission.Status.SUBMITTED else None
        return Submission.objects.create(submitted_at=submitted_at, **validated_data)


class SubmissionUpdateSerializer(serializers.ModelSerializer):
    """Update serializer for Submission (learner PATCH draft only)."""

    class Meta:
        model = Submission
        fields = ['status', 'submitted_text', 'submitted_file_url', 'submitted_file_name']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        if instance.status != Submission.Status.DRAFT:
            raise serializers.ValidationError({'non_field_errors': ['Only draft submissions can be edited.']})

        status_val = attrs.get('status', instance.status)
        if status_val == Submission.Status.GRADED:
            raise serializers.ValidationError({'status': 'Learners cannot set status to graded.'})
        if status_val == Submission.Status.SUBMITTED:
            text = (attrs.get('submitted_text', None) if 'submitted_text' in attrs else instance.submitted_text) or ''
            file_url = attrs.get('submitted_file_url', instance.submitted_file_url) if 'submitted_file_url' in attrs else instance.submitted_file_url
            if not text.strip() and not file_url:
                raise serializers.ValidationError(
                    {'non_field_errors': ['Submitted text or file URL is required when submitting.']}
                )

        return attrs

    def update(self, instance, validated_data):
        status_val = validated_data.get('status', instance.status)
        if status_val == Submission.Status.SUBMITTED:
            validated_data['submitted_at'] = timezone.now()
        return super().update(instance, validated_data)


class GradeSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for grading a submission."""

    class Meta:
        model = Submission
        fields = ['grade', 'feedback', 'internal_notes']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        if instance.status != Submission.Status.SUBMITTED:
            raise serializers.ValidationError(
                {'non_field_errors': ['Only submitted submissions can be graded.']}
            )

        grade = attrs.get('grade')
        if grade is not None:
            max_points = instance.assignment.max_points
            if grade < 0 or grade > max_points:
                raise serializers.ValidationError(
                    {'grade': f'Grade must be between 0 and {max_points}.'}
                )

        return attrs

    def update(self, instance, validated_data):
        from django.utils import timezone
        validated_data['status'] = Submission.Status.GRADED
        validated_data['graded_at'] = timezone.now()
        validated_data['graded_by'] = self.context['request'].user
        return super().update(instance, validated_data)