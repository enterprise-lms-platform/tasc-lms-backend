from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta, datetime
import pytz
import re

from .models  import (
    LivestreamSession, LivestreamAttendance, 
    LivestreamRecording
)
from .calendar_service import TimezoneService


class LivestreamSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for LivestreamSession model.
    Includes computed properties and nested data.
    """
    
    course_title = serializers.CharField(source='course.title', read_only=True)
    instructor_name = serializers.SerializerMethodField()
    instructor_email = serializers.CharField(source='instructor.email', read_only=True)
    
    # Status properties
    is_live = serializers.BooleanField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    has_ended = serializers.BooleanField(read_only=True)
    
    # Stats
    attendee_count = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()
    
    # Timezone-aware times
    start_time_local = serializers.SerializerMethodField()
    end_time_local = serializers.SerializerMethodField()
    
    # Calendar links (added in view)
    calendar_links = serializers.SerializerMethodField()
    
    class Meta:
        model = LivestreamSession
        fields = [
            'id', 'course', 'course_title', 'instructor', 'instructor_name',
            'instructor_email', 'title', 'description', 'start_time', 'end_time',
            'start_time_local', 'end_time_local', 'duration_minutes', 'timezone',
            'is_recurring', 'recurrence_pattern', 'recurrence_end_date',
            'recurrence_days', 'parent_session', 'recurrence_order',
            'platform', 'zoom_meeting_id', 'join_url', 'start_url',
            'instructor_join_url', 'password', 'status', 'recording_url',
            'auto_recording', 'waiting_room', 'mute_on_entry', 'allow_chat',
            'allow_questions', 'max_attendees', 'total_attendees',
            'peak_attendees', 'is_live', 'is_upcoming', 'has_ended',
            'attendee_count', 'question_count', 'calendar_links',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'instructor', 'created_at', 'updated_at', 'zoom_meeting_id',
            'join_url', 'start_url', 'instructor_join_url', 'password',
            'recording_url', 'total_attendees', 'peak_attendees',
            'zoom_webhook_received'
        ]
    
    def get_instructor_name(self, obj):
        return obj.instructor.get_full_name() or obj.instructor.email
    
    def get_attendee_count(self, obj):
        return obj.attendances.filter(joined_at__isnull=False).count()
    
    def get_question_count(self, obj):
        return obj.questions.count()
    
    def get_start_time_local(self, obj):
        """Return start time in user's timezone if available"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user_tz = getattr(request.user, 'timezone', 'UTC')
            return TimezoneService.format_for_user(obj.start_time, user_tz)
        return obj.start_time.isoformat()
    
    def get_end_time_local(self, obj):
        """Return end time in user's timezone if available"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user_tz = getattr(request.user, 'timezone', 'UTC')
            return TimezoneService.format_for_user(obj.end_time, user_tz)
        return obj.end_time.isoformat()
    
    def get_calendar_links(self, obj):
        """Add calendar links - populated in view"""
        return {}  # Will be added in view
    
    def validate(self, data):
        """Validate session timing and recurrence"""
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        duration = data.get('duration_minutes')
        is_recurring = data.get('is_recurring', False)
        recurrence_pattern = data.get('recurrence_pattern', 'none')
        
        # Validate times
        if start_time and end_time:
            if end_time <= start_time:
                raise serializers.ValidationError(
                    "End time must be after start time"
                )
            
            # Calculate duration from times
            calculated_duration = (end_time - start_time).total_seconds() / 60
            
            # If duration provided, validate it matches
            if duration and abs(calculated_duration - duration) > 1:
                data['duration_minutes'] = int(calculated_duration)
        
        # Start time must be in the future for scheduled sessions
        if data.get('status', 'scheduled') == 'scheduled' and start_time:
            if start_time <= timezone.now():
                raise serializers.ValidationError(
                    "Start time must be in the future for scheduled sessions"
                )
        
        # Validate recurrence
        if is_recurring and recurrence_pattern != 'none':
            if not data.get('recurrence_end_date'):
                raise serializers.ValidationError(
                    "Recurrence end date is required for recurring sessions"
                )
            
            if recurrence_pattern in ['weekly', 'biweekly']:
                if not data.get('recurrence_days'):
                    raise serializers.ValidationError(
                        "Weekly days are required for weekly recurrence"
                    )
        
        return data


class LivestreamSessionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating livestream sessions.
    Includes Zoom integration and recurrence handling.
    """
    
    class Meta:
        model = LivestreamSession
        fields = [
            'course', 'title', 'description', 'start_time', 'end_time',
            'duration_minutes', 'timezone', 'is_recurring', 'recurrence_pattern',
            'recurrence_end_date', 'recurrence_days', 'platform',
            'auto_recording', 'waiting_room', 'mute_on_entry', 'allow_chat',
            'allow_questions', 'max_attendees'
        ]
    
    def validate_course(self, value):
        """Validate that the user is instructor of this course"""
        request = self.context.get('request')
        if request and request.user:
            if value.instructor != request.user:
                if not getattr(request.user, 'role', '') in ['admin', 'super_admin']:
                    raise serializers.ValidationError(
                        "You are not the instructor of this course"
                    )
        return value
    
    def validate_timezone(self, value):
        """Validate timezone string"""
        try:
            pytz.timezone(value)
            return value
        except pytz.exceptions.UnknownTimeZoneError:
            raise serializers.ValidationError(f"Unknown timezone: {value}")
    
    def create(self, validated_data):
        """Create session with instructor from request"""
        request = self.context.get('request')
        validated_data['instructor'] = request.user
        validated_data['created_by'] = request.user
        
        # Calculate duration if not provided
        if 'duration_minutes' not in validated_data:
            start = validated_data['start_time']
            end = validated_data['end_time']
            validated_data['duration_minutes'] = int((end - start).total_seconds() / 60)
        
        return super().create(validated_data)


class LivestreamSessionUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating livestream sessions.
    """
    
    class Meta:
        model = LivestreamSession
        fields = [
            'title', 'description', 'start_time', 'end_time',
            'duration_minutes', 'timezone', 'recurrence_end_date',
            'auto_recording', 'waiting_room', 'mute_on_entry',
            'allow_chat', 'allow_questions', 'max_attendees'
        ]
    
    def validate(self, data):
        """Validate that session can be updated"""
        instance = self.instance
        
        # Can't update live or ended sessions
        if instance.status in ['live', 'ended']:
            raise serializers.ValidationError(
                "Cannot update a session that is live or has ended"
            )
        
        return super().validate(data)


class LivestreamAttendanceSerializer(serializers.ModelSerializer):
    """
    Serializer for LivestreamAttendance model.
    """
    
    learner_name = serializers.SerializerMethodField()
    learner_email = serializers.CharField(source='learner.email', read_only=True)
    session_title = serializers.CharField(source='session.title', read_only=True)
    attendance_percentage = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = LivestreamAttendance
        fields = [
            'id', 'session', 'session_title', 'learner', 'learner_name',
            'learner_email', 'joined_at', 'left_at', 'duration_seconds',
            'attendance_percentage', 'status', 'questions_asked',
            'chat_messages', 'raised_hand', 'device_info', 'certificate_issued',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_learner_name(self, obj):
        return obj.learner.get_full_name() or obj.learner.email


class LivestreamRecordingSerializer(serializers.ModelSerializer):
    """
    Serializer for LivestreamRecording model.
    """
    
    session_title = serializers.CharField(source='session.title', read_only=True)
    
    class Meta:
        model = LivestreamRecording
        fields = [
            'id', 'session', 'session_title', 'recording_type', 'file_url',
            'download_url', 'file_size', 'file_extension', 'recording_start',
            'recording_end', 'duration_seconds', 'is_published', 'thumbnail_url',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class LivestreamActionSerializer(serializers.Serializer):
    """
    Serializer for livestream actions.
    """
    
    ACTION_CHOICES = [
        ('start', 'Start Session'),
        ('end', 'End Session'),
        ('cancel', 'Cancel Session'),
        ('remind', 'Send Reminder'),
        ('send_recording', 'Send Recording Link'),
    ]
    
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    reason = serializers.CharField(required=False, allow_blank=True)


class LivestreamQuestionAnswerSerializer(serializers.Serializer):
    """
    Serializer for answering questions.
    """
    
    answer = serializers.CharField(required=True)
    status = serializers.ChoiceField(
        choices=['answered', 'skipped'],
        default='answered'
    )


class UserTimezoneSerializer(serializers.Serializer):
    """
    Serializer for user timezone preference.
    """
    
    timezone = serializers.CharField(required=True)
    
    def validate_timezone(self, value):
        try:
            pytz.timezone(value)
            return value
        except pytz.exceptions.UnknownTimeZoneError:
            raise serializers.ValidationError(f"Unknown timezone: {value}")