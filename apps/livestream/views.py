from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiResponse,
    OpenApiExample, inline_serializer
)
import json
import logging
from datetime import timedelta

from django.db.models import Avg

from .models import (
    LivestreamSession, LivestreamAttendance, 
    LivestreamRecording, LivestreamQuestion
)
from .serializers import (
    LivestreamSessionSerializer, LivestreamSessionCreateSerializer,
    LivestreamSessionUpdateSerializer, LivestreamAttendanceSerializer,
    LivestreamActionSerializer,
    LivestreamQuestionAnswerSerializer, LivestreamRecordingSerializer,
    UserTimezoneSerializer, LivestreamQuestionSerializer,
    LivestreamQuestionCreateSerializer
)
from .services.platform_factory import LivestreamPlatformFactory
from .services.zoom_service import ZoomWebhookHandler
from .services.google_meet_service import GoogleMeetWebhookHandler
from .services.teams_service import TeamsWebhookHandler
from .services.calendar_service import CalendarService, TimezoneService
from .permissions import IsInstructorOrReadOnly
from apps.accounts.rbac import is_admin_like, is_instructor

logger = logging.getLogger(__name__)


@extend_schema(tags=['Livestream Sessions'])
class LivestreamSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing livestream sessions.
    
    Provides:
    - Create sessions with automatic Zoom meeting generation
    - List sessions with filtering
    - Join sessions with one-click links
    - Calendar integration
    - Recurring session support
    - Automatic attendance tracking
    """
    
    queryset = LivestreamSession.objects.all()
    permission_classes = [IsAuthenticated, IsInstructorOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return LivestreamSessionCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return LivestreamSessionUpdateSerializer
        return LivestreamSessionSerializer
    
    def get_queryset(self):
        """
        Filter sessions based on query parameters.
        Supports filtering by course, status, date range.
        Also handles timezone conversion for display.
        """
        queryset = LivestreamSession.objects.all()
        
        # Filter by course
        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        
        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by instructor
        instructor_id = self.request.query_params.get('instructor')
        if instructor_id:
            queryset = queryset.filter(instructor_id=instructor_id)
        
        # Filter by date range
        from_date = self.request.query_params.get('from')
        if from_date:
            queryset = queryset.filter(start_time__date__gte=from_date)
        
        to_date = self.request.query_params.get('to')
        if to_date:
            queryset = queryset.filter(end_time__date__lte=to_date)
        
        # Filter upcoming/ongoing/past
        when = self.request.query_params.get('when')
        now = timezone.now()
        if when == 'upcoming':
            queryset = queryset.filter(start_time__gt=now)
        elif when == 'ongoing':
            queryset = queryset.filter(
                start_time__lte=now,
                end_time__gte=now,
                status='live'
            )
        elif when == 'past':
            queryset = queryset.filter(end_time__lt=now)
        
        # For learners, only show relevant sessions
        user = self.request.user
        if not hasattr(user, 'role') or (not is_instructor(user) and not is_admin_like(user)):
            # Show sessions for courses they're enrolled in
            enrolled_courses = user.course_enrollments.filter(
                status='active'
            ).values_list('course_id', flat=True)
            queryset = queryset.filter(course_id__in=enrolled_courses)
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """List sessions with timezone conversion"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get user's timezone preference
        user_tz = request.query_params.get('timezone', 'UTC')
        if request.user.is_authenticated and hasattr(request.user, 'timezone'):
            user_tz = request.user.timezone
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
    
    @extend_schema(
        summary='Create livestream session',
        description='Create a new livestream session with automatic Zoom meeting generation',
        request=LivestreamSessionCreateSerializer,
        responses={201: LivestreamSessionSerializer}
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create a new livestream session with platform meeting integration"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Save session first
        session = serializer.save()
        
        # Create meeting on the selected platform
        self._create_platform_meeting(session)
        
        # If recurring, create child sessions
        if session.is_recurring and session.recurrence_pattern != 'none':
            self._create_recurring_sessions(session)
        
        return Response(
            LivestreamSessionSerializer(session, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )
    
    def _create_platform_meeting(self, session):
        """Create a meeting on the appropriate platform (Zoom, Google Meet, or Teams)."""
        if session.platform == 'custom':
            return  # Custom RTMP doesn't need a platform meeting
        
        try:
            platform_service = LivestreamPlatformFactory.get_platform(session.platform)
        except ValueError:
            logger.warning(f"Unsupported platform '{session.platform}' for session {session.id}")
            return
        
        meeting_data = {
            'topic': f"{session.course.title}: {session.title}",
            'agenda': session.description,
            'start_time': session.start_time,
            'duration': session.duration_minutes,
            'timezone': session.timezone,
            'host_video': True,
            'participant_video': False,
            'mute_upon_entry': session.mute_on_entry,
            'waiting_room': session.waiting_room,
            'auto_recording': 'cloud' if session.auto_recording else 'none',
        }
        
        try:
            # Handle recurring meetings (Zoom only for now)
            if session.platform == 'zoom' and session.is_recurring and session.recurrence_pattern != 'none':
                result = platform_service.create_recurring_meeting(
                    meeting_data,
                    session.recurrence_pattern,
                    session.recurrence_end_date
                )
            else:
                result = platform_service.create_meeting(meeting_data)
            
            # Store platform-specific meeting details
            if session.platform == 'zoom':
                if result.get('success'):
                    session.zoom_meeting_id = result['meeting_id']
                    session.zoom_meeting_uuid = result.get('meeting_uuid', '')
                    session.join_url = result['join_url']
                    session.start_url = result['start_url']
                    session.password = result.get('password', '')
                    session.save()
                else:
                    session.metadata['platform_error'] = result.get('error', 'Unknown error')
                    session.save()
                    
            elif session.platform == 'google_meet':
                if result.get('success'):
                    session.calendar_event_id = result.get('event_id', '')
                    session.join_url = result.get('meet_uri', '')
                    session.start_url = result.get('meet_uri', '')
                    session.save()
                else:
                    session.metadata['platform_error'] = str(result)
                    session.save()
                    
            elif session.platform == 'teams':
                session.teams_meeting_id = result.get('meeting_id', '')
                session.teams_join_url = result.get('join_url', '')
                session.join_url = result.get('join_url', '')
                session.save()

        except Exception as e:
            logger.error(f"Failed to create {session.platform} meeting for session {session.id}: {e}")
            session.metadata['platform_error'] = str(e)
            session.save()
    
    def _create_recurring_sessions(self, parent_session):
        """Create child sessions for recurring pattern."""
        pattern = parent_session.recurrence_pattern
        end_date = parent_session.recurrence_end_date
        
        if not end_date:
            return
        
        interval_map = {
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'biweekly': timedelta(weeks=2),
            'monthly': timedelta(days=30),  # approximate
        }
        interval = interval_map.get(pattern)
        if not interval:
            return
        
        duration = parent_session.end_time - parent_session.start_time
        current_start = parent_session.start_time + interval
        order = 1
        
        while current_start <= end_date:
            LivestreamSession.objects.create(
                course=parent_session.course,
                instructor=parent_session.instructor,
                title=parent_session.title,
                description=parent_session.description,
                start_time=current_start,
                end_time=current_start + duration,
                duration_minutes=parent_session.duration_minutes,
                timezone=parent_session.timezone,
                is_recurring=False,
                recurrence_pattern='none',
                parent_session=parent_session,
                recurrence_order=order,
                platform=parent_session.platform,
                auto_recording=parent_session.auto_recording,
                waiting_room=parent_session.waiting_room,
                mute_on_entry=parent_session.mute_on_entry,
                allow_chat=parent_session.allow_chat,
                allow_questions=parent_session.allow_questions,
                max_attendees=parent_session.max_attendees,
                created_by=parent_session.created_by,
            )
            current_start += interval
            order += 1
    
    @extend_schema(
        summary='Get session details',
        description='Get detailed information about a livestream session with timezone conversion'
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        data = serializer.data
        
        # Add calendar links
        data['calendar_links'] = CalendarService.get_all_calendar_links(
            instance, request, request.user if request.user.is_authenticated else None
        )
        
        # Add attendance status for current user
        if request.user.is_authenticated:
            try:
                attendance = LivestreamAttendance.objects.get(
                    session=instance,
                    learner=request.user
                )
                data['user_attendance'] = LivestreamAttendanceSerializer(attendance).data
            except LivestreamAttendance.DoesNotExist:
                data['user_attendance'] = None
        
        return Response(data)
    
    @extend_schema(
        summary='Update session',
        description='Update livestream session details (also updates Zoom meeting)'
    )
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Check if session can be updated
        if instance.status in ['live', 'ended']:
            return Response(
                {'error': 'Cannot update a session that is live or has ended'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Update on the appropriate platform
        self._update_platform_meeting(instance, serializer.validated_data)
        
        self.perform_update(serializer)
        
        return Response(
            LivestreamSessionSerializer(instance, context={'request': request}).data
        )
    
    def _update_platform_meeting(self, instance, validated_data):
        """Update the meeting on the appropriate platform."""
        update_data = {
            'topic': validated_data.get('title', instance.title),
            'agenda': validated_data.get('description', instance.description),
            'start_time': validated_data.get('start_time', instance.start_time),
            'duration': validated_data.get('duration_minutes', instance.duration_minutes),
        }
        
        try:
            if instance.platform == 'zoom' and instance.zoom_meeting_id:
                platform_service = LivestreamPlatformFactory.get_platform('zoom')
                platform_service.update_meeting(instance.zoom_meeting_id, update_data)
            elif instance.platform == 'google_meet' and instance.calendar_event_id:
                platform_service = LivestreamPlatformFactory.get_platform('google_meet')
                platform_service.update_meeting(instance.calendar_event_id, update_data)
            elif instance.platform == 'teams' and instance.teams_meeting_id:
                platform_service = LivestreamPlatformFactory.get_platform('teams')
                platform_service.update_meeting(instance.teams_meeting_id, update_data)
        except Exception as e:
            logger.error(f"Failed to update {instance.platform} meeting: {e}")
            instance.metadata['platform_update_error'] = str(e)
    
    @extend_schema(
        summary='Delete session',
        description='Delete a livestream session (also deletes platform meeting)'
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Delete from the appropriate platform
        try:
            if instance.platform == 'zoom' and instance.zoom_meeting_id:
                platform_service = LivestreamPlatformFactory.get_platform('zoom')
                platform_service.delete_meeting(instance.zoom_meeting_id)
            elif instance.platform == 'google_meet' and instance.calendar_event_id:
                platform_service = LivestreamPlatformFactory.get_platform('google_meet')
                platform_service.delete_meeting(instance.calendar_event_id)
            elif instance.platform == 'teams' and instance.teams_meeting_id:
                platform_service = LivestreamPlatformFactory.get_platform('teams')
                platform_service.delete_meeting(instance.teams_meeting_id)
        except Exception as e:
            logger.error(f"Failed to delete {instance.platform} meeting: {e}")
        
        return super().destroy(request, *args, **kwargs)
    
    @extend_schema(
        summary='Take action on session',
        description='Start, end, cancel, or send reminders for a session',
        request=LivestreamActionSerializer,
        responses={200: LivestreamSessionSerializer}
    )
    @action(detail=True, methods=['post'], url_path='action')
    def take_action(self, request, pk=None):
        """Take action on a session (start/end/cancel/remind)"""
        session = self.get_object()
        serializer = LivestreamActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action_type = serializer.validated_data['action']
        reason = serializer.validated_data.get('reason', '')
        
        if action_type == 'start':
            if session.status != 'scheduled':
                return Response(
                    {'error': 'Only scheduled sessions can be started'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            session.start_session()
            
        elif action_type == 'end':
            if session.status != 'live':
                return Response(
                    {'error': 'Only live sessions can be ended'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            session.end_session()
            # Auto-mark anyone who never checked in as no_show
            session.attendances.filter(
                status__in=['registered', 'joined']
            ).update(status='no_show')
            
        elif action_type == 'cancel':
            if session.status in ['ended', 'cancelled']:
                return Response(
                    {'error': 'Session already ended or cancelled'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            session.cancel_session(reason)
            
        elif action_type == 'remind':
            # Send reminder to enrolled learners
            self._send_reminder(session)
            session.reminder_sent_15m = True
            session.save()
            
        elif action_type == 'send_recording':
            # Send recording link to learners
            self._send_recording_link(session)
        
        return Response(
            LivestreamSessionSerializer(session, context={'request': request}).data
        )
    
    def _send_reminder(self, session):
        """Send reminder email to enrolled learners."""
        from django.core.mail import send_mass_mail
        from django.conf import settings as django_settings
        
        attendances = session.attendances.filter(status='registered')
        if not attendances.exists():
            return
        
        messages = []
        for att in attendances:
            messages.append((
                f"Reminder: {session.title} is starting soon",
                f"Hi {att.learner.get_full_name() or att.learner.email},\n\n"
                f"Your session '{session.title}' for {session.course.title} "
                f"starts at {session.start_time.strftime('%H:%M %Z')}.\n\n"
                f"Join here: {session.join_url}\n",
                django_settings.DEFAULT_FROM_EMAIL,
                [att.learner.email],
            ))
        
        try:
            send_mass_mail(messages, fail_silently=True)
            logger.info(f"Sent {len(messages)} reminders for session {session.id}")
        except Exception as e:
            logger.error(f"Failed to send reminders: {e}")
    
    def _send_recording_link(self, session):
        """Send recording link to enrolled learners."""
        from django.core.mail import send_mass_mail
        from django.conf import settings as django_settings
        
        if not session.recording_url:
            return
        
        attendances = session.attendances.all()
        messages = []
        for att in attendances:
            messages.append((
                f"Recording available: {session.title}",
                f"Hi {att.learner.get_full_name() or att.learner.email},\n\n"
                f"The recording for '{session.title}' is now available.\n\n"
                f"Watch here: {session.recording_url}\n",
                django_settings.DEFAULT_FROM_EMAIL,
                [att.learner.email],
            ))
        
        try:
            send_mass_mail(messages, fail_silently=True)
            logger.info(f"Sent {len(messages)} recording links for session {session.id}")
        except Exception as e:
            logger.error(f"Failed to send recording links: {e}")
    
    @extend_schema(
        summary='Join session',
        description='Get one-click join link for the session (redirects to Zoom)'
    )
    @action(detail=True, methods=['get'])
    def join(self, request, pk=None):
        """Get join link for the session"""
        session = self.get_object()
        
        # Record attendance attempt
        if request.user.is_authenticated:
            attendance, created = LivestreamAttendance.objects.get_or_create(
                session=session,
                learner=request.user
            )
        
        # Return join URL
        if request.user == session.instructor:
            # Instructor gets start URL
            return Response({
                'url': session.start_url or session.join_url,
                'type': 'instructor'
            })
        else:
            # Learners get join URL
            return Response({
                'url': session.join_url,
                'type': 'learner',
                'password': session.password if session.password else None
            })
    
    @extend_schema(
        summary='Get calendar links',
        description='Get calendar integration links for Google, Outlook, Apple, etc.'
    )
    @action(detail=True, methods=['get'])
    def calendar(self, request, pk=None):
        """Get calendar integration links"""
        session = self.get_object()
        
        links = CalendarService.get_all_calendar_links(
            session, request, request.user if request.user.is_authenticated else None
        )
        
        return Response(links)
    
    @extend_schema(
        summary='Download ICS file',
        description='Download .ics file for calendar import'
    )
    @action(detail=True, methods=['get'], url_path='calendar/ics')
    def download_ics(self, request, pk=None):
        """Download .ics file for calendar import"""
        session = self.get_object()
        
        # Get user's timezone preference
        user_tz = 'UTC'
        if request.user.is_authenticated and hasattr(request.user, 'timezone'):
            user_tz = request.user.timezone
        
        ics_content = CalendarService.generate_ics_file(session, request.user, user_tz)
        
        response = HttpResponse(ics_content, content_type='text/calendar')
        response['Content-Disposition'] = f'attachment; filename="livestream-{session.id}.ics"'
        response['Content-Length'] = len(ics_content)
        return response
    
    @extend_schema(
        summary='Get attendance',
        description='Get attendance list for the session (instructor only)'
    )
    @action(detail=True, methods=['get'])
    def attendance(self, request, pk=None):
        """Get attendance for this session"""
        session = self.get_object()
        
        # Only instructor or admin can view attendance
        if request.user != session.instructor and not is_admin_like(request.user):
            return Response(
                {'error': 'Only the instructor can view attendance'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        attendance = session.attendances.all()
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            attendance = attendance.filter(status=status_filter)
        
        page = self.paginate_queryset(attendance)
        if page is not None:
            serializer = LivestreamAttendanceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = LivestreamAttendanceSerializer(attendance, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Get attendance report',
        description='Get attendance report with statistics'
    )
    @action(detail=True, methods=['get'])
    def attendance_report(self, request, pk=None):
        """Get attendance report with statistics"""
        session = self.get_object()
        
        # Only instructor or admin can view reports
        if request.user != session.instructor and not is_admin_like(request.user):
            return Response(
                {'error': 'Only the instructor can view attendance reports'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        attendance = session.attendances.all()
        
        # Calculate statistics
        total_enrolled = attendance.count()
        attended = attendance.filter(joined_at__isnull=False).count()
        completed = attendance.filter(status='completed').count()
        
        # Average attendance duration
        avg_duration = attendance.filter(
            duration_seconds__gt=0
        ).aggregate(avg=Avg('duration_seconds'))['avg'] or 0
        
        return Response({
            'session_id': str(session.id),
            'session_title': session.title,
            'total_enrolled': total_enrolled,
            'attended': attended,
            'attendance_rate': round((attended / total_enrolled * 100) if total_enrolled > 0 else 0, 2),
            'completed': completed,
            'completion_rate': round((completed / attended * 100) if attended > 0 else 0, 2),
            'average_duration_minutes': round(avg_duration / 60, 2),
            'peak_attendees': session.peak_attendees,
        })
        
    
    @extend_schema(
        summary='Get recordings',
        description='Get recordings of the session'
    )
    @action(detail=True, methods=['get'])
    def recordings(self, request, pk=None):
        """Get recordings for this session"""
        session = self.get_object()
        recordings = session.recordings.filter(is_published=True)
        
        serializer = LivestreamRecordingSerializer(recordings, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Get recording download',
        description='Get download link for session recording (with authentication)'
    )
    @action(detail=True, methods=['get'], url_path='recordings/(?P<recording_id>[^/.]+)/download')
    def recording_download(self, request, pk=None, recording_id=None):
        """Get download link for specific recording"""
        session = self.get_object()
        recording = get_object_or_404(LivestreamRecording, id=recording_id, session=session)
        
        # Check if user has access
        if not self._user_has_recording_access(request.user, session):
            return Response(
                {'error': 'You do not have access to this recording'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response({
            'download_url': recording.download_url,
            'file_size': recording.file_size,
            'file_extension': recording.file_extension,
            'expires_in': '24 hours'  # Add signed URL expiry
        })
    
    def _user_has_recording_access(self, user, session):
        """Check if user has access to session recording"""
        if user == session.instructor:
            return True
        if is_admin_like(user):
            return True
        # Check if enrolled in course
        return user.course_enrollments.filter(
            course=session.course,
            status='active'
        ).exists()
   


@extend_schema(tags=['Livestream Attendance'])
class LivestreamAttendanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing livestream attendance.
    Automatically tracks when users join/leave.
    """
    
    queryset = LivestreamAttendance.objects.all()
    serializer_class = LivestreamAttendanceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Filter by session
        session_id = self.request.query_params.get('session')
        queryset = LivestreamAttendance.objects.all()
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        # Instructors see all, learners see only their own
        if not is_instructor(user) and not is_admin_like(user):
            queryset = queryset.filter(learner=user)
        
        return queryset
    
    @extend_schema(
        summary='Mark attendance',
        description='Mark that user has joined the livestream'
    )
    @action(detail=False, methods=['post'])
    def join(self, request):
        """Mark user as joined"""
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session = get_object_or_404(LivestreamSession, id=session_id)
        
        attendance, created = LivestreamAttendance.objects.get_or_create(
            session=session,
            learner=request.user
        )
        
        attendance.mark_joined({
            'device': request.META.get('HTTP_USER_AGENT', ''),
            'ip_address': request.META.get('REMOTE_ADDR', '')
        })
        
        return Response(LivestreamAttendanceSerializer(attendance).data)
    
    @extend_schema(
        summary='Mark leave',
        description='Mark that user has left the livestream'
    )
    @action(detail=False, methods=['post'])
    def leave(self, request):
        """Mark user as left"""
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session = get_object_or_404(LivestreamSession, id=session_id)
        
        attendance = get_object_or_404(
            LivestreamAttendance,
            session=session,
            learner=request.user
        )
        
        attendance.mark_left()
        
        return Response(LivestreamAttendanceSerializer(attendance).data)
    
    @extend_schema(
        summary='My attendance',
        description='Get current user\'s attendance records'
    )
    @action(detail=False, methods=['get'])
    def my_attendance(self, request):
        """Get current user's attendance records"""
        attendances = LivestreamAttendance.objects.filter(learner=request.user)

        page = self.paginate_queryset(attendances)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(attendances, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary='Learner self-check-in',
        description='Mark attendance as attended. Only active 10 min before to 30 min after session start.'
    )
    @action(detail=False, methods=['post'])
    def check_in(self, request):
        """Learner self-check-in — time-gated window"""
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = get_object_or_404(LivestreamSession, id=session_id)
        now = timezone.now()
        window_start = session.start_time - timedelta(minutes=10)
        window_end = session.start_time + timedelta(minutes=30)

        if not (window_start <= now <= window_end):
            return Response(
                {
                    'error': 'Check-in window is not open',
                    'window_start': window_start.isoformat(),
                    'window_end': window_end.isoformat(),
                    'now': now.isoformat(),
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        attendance, _ = LivestreamAttendance.objects.get_or_create(
            session=session,
            learner=request.user
        )
        attendance.status = 'attended'
        attendance.joined_at = attendance.joined_at or now
        attendance.save(update_fields=['status', 'joined_at', 'updated_at'])

        return Response(LivestreamAttendanceSerializer(attendance).data)

    @extend_schema(
        summary='Update attendance status',
        description='Instructor manually sets a learner\'s status (attended / absent / no_show).'
    )
    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        """Instructor updates a learner's attendance status"""
        attendance = self.get_object()
        new_status = request.data.get('status')

        allowed = {'attended', 'absent', 'no_show', 'completed'}
        if new_status not in allowed:
            return Response(
                {'error': f'status must be one of: {", ".join(allowed)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Only the session instructor or an admin may do this
        if (request.user != attendance.session.instructor
                and not is_admin_like(request.user)):
            return Response(
                {'error': 'Only the instructor can update attendance status'},
                status=status.HTTP_403_FORBIDDEN
            )

        attendance.status = new_status
        attendance.save(update_fields=['status', 'updated_at'])
        return Response(LivestreamAttendanceSerializer(attendance).data)


@extend_schema(tags=['Livestream - Webhooks'])
class LivestreamWebhookView(viewsets.GenericViewSet):
    """
    Handle Zoom webhooks for livestream sessions.
    Updates session status, attendance, and recordings automatically.
    """
    
    permission_classes = [AllowAny]
    serializer_class = None  # Webhooks don't use traditional serializers; see action decorators
    
    @extend_schema(
        summary='Zoom webhook',
        description='Receive webhooks from Zoom for automatic updates',
        request=inline_serializer(
            name='ZoomWebhookPayload',
            fields={}
        ),
        responses={200: OpenApiResponse(description='Webhook received')}
    )
    @action(detail=False, methods=['post'], url_path='zoom')
    @csrf_exempt
    def zoom_webhook(self, request):
        """Handle Zoom webhook"""
        handler = ZoomWebhookHandler()
        result = handler.handle_webhook(request)
        
        if result['success']:
            return JsonResponse({'status': 'success'})
        else:
            return JsonResponse(
                {'error': result.get('error', 'Unknown error')},
                status=400
            )

    @extend_schema(
        summary='Google Calendar webhook',
        description='Receive push notifications from Google Calendar for automatic updates',
        request=inline_serializer(
            name='GoogleCalendarWebhookPayload',
            fields={}
        ),
        responses={200: OpenApiResponse(description='Webhook received')},
        parameters=[
            OpenApiParameter(name='X-Goog-Channel-ID', location=OpenApiParameter.HEADER, required=True),
            OpenApiParameter(name='X-Goog-Resource-ID', location=OpenApiParameter.HEADER, required=True),
            OpenApiParameter(name='X-Goog-Resource-State', location=OpenApiParameter.HEADER, required=True),
        ]
    )
    @action(detail=False, methods=['post'], url_path='google-calendar')
    @csrf_exempt
    def google_calendar_webhook(self, request):
        """Handle Google Calendar push notification webhook"""
        handler = GoogleMeetWebhookHandler()
        result = handler.handle_webhook(request)
        
        status_code = 200
        if result.get('status') == 'error':
            status_code = 400
            
        return JsonResponse(result, status=status_code)

    @extend_schema(
        summary='Microsoft Teams webhook',
        description='Receive change notifications from Microsoft Graph for Teams meetings',
        request=inline_serializer(
            name='TeamsWebhookPayload',
            fields={}
        ),
        responses={200: OpenApiResponse(description='Webhook received or validation token returned')}
    )
    @action(detail=False, methods=['post'], url_path='teams')
    @csrf_exempt
    def teams_webhook(self, request):
        """Handle Microsoft Teams / Graph webhook"""
        handler = TeamsWebhookHandler()
        result = handler.handle_webhook(request)
        
        # If it's a validation request, Graph expects 200 OK with the token as plain text
        if 'validation_token' in result:
            from django.http import HttpResponse
            return HttpResponse(result['validation_token'], content_type='text/plain')
            
        status_code = 200
        if result.get('status') in ['error', 'invalid_payload']:
            status_code = 400
            
        return JsonResponse(result, status=status_code)
    
    @extend_schema(
        summary='Validate webhook',
        description='Validate Zoom webhook signature',
        parameters=[
            OpenApiParameter(name='x-zm-signature', location=OpenApiParameter.HEADER),
            OpenApiParameter(name='x-zm-request-timestamp', location=OpenApiParameter.HEADER),
        ]
    )
    @action(detail=False, methods=['get'], url_path='health')
    def webhook_health(self, request):
        """Webhook health endpoint"""
        return Response({
            'status': 'ok',
            'message': 'Webhook endpoint is active',
            'timestamp': timezone.now().isoformat()
        })


@extend_schema(tags=['Livestream - Timezone'])
class TimezoneViewSet(viewsets.GenericViewSet):
    """
    Handle timezone preferences and conversions for users.
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = UserTimezoneSerializer
    
    @extend_schema(
        summary='Get timezone options',
        description='Get list of available timezones'
    )
    @action(detail=False, methods=['get'])
    def options(self, request):
        """Get available timezone options"""
        return Response(TimezoneService.get_timezone_converter())
    
    @extend_schema(
        summary='Set user timezone',
        description='Set user\'s preferred timezone',
        request=UserTimezoneSerializer,
        responses={200: OpenApiResponse(description='Timezone updated')}
    )
    @action(detail=False, methods=['post'])
    def set_preference(self, request):
        """Set user's timezone preference"""
        serializer = UserTimezoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        request.user.timezone = serializer.validated_data['timezone']
        request.user.save(update_fields=['timezone'])
        
        return Response({
            'success': True,
            'timezone': request.user.timezone
        })
    
    @extend_schema(
        summary='Convert time',
        description='Convert time to user\'s timezone'
    )
    @action(detail=False, methods=['post'])
    def convert(self, request):
        """Convert time to user's timezone"""
        time_str = request.data.get('time')
        from_tz = request.data.get('from_timezone', 'UTC')
        to_tz = request.data.get('to_timezone', request.user.timezone if hasattr(request.user, 'timezone') else 'UTC')
        
        if not time_str:
            return Response(
                {'error': 'time is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Parse time
            from datetime import datetime
            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            
            # Convert
            import pytz
            from_tz_obj = pytz.timezone(from_tz)
            to_tz_obj = pytz.timezone(to_tz)
            
            if dt.tzinfo is None:
                dt = from_tz_obj.localize(dt)
            
            converted = dt.astimezone(to_tz_obj)
            
            return Response({
                'original': time_str,
                'converted': converted.isoformat(),
                'from_timezone': from_tz,
                'to_timezone': to_tz,
                'formatted': converted.strftime('%Y-%m-%d %H:%M %Z')
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    tags=['Livestream - Questions'],
    description='Manage questions in livestream sessions',
)
class LivestreamQuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing livestream questions.
    - GET: List questions for a session
    - POST: Ask a question (learners)
    - POST /{id}/answer/: Answer a question (instructor)
    - DELETE: Delete a question
    """
    queryset = LivestreamQuestion.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return LivestreamQuestionCreateSerializer
        return LivestreamQuestionSerializer

    def get_queryset(self):
        queryset = LivestreamQuestion.objects.select_related('session', 'asked_by', 'answered_by')
        
        session_id = self.request.query_params.get('session')
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        return queryset

    def create(self, request, *args, **kwargs):
        session_id = request.data.get('session')
        if not session_id:
            return Response(
                {'session': 'This field is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = LivestreamSession.objects.get(id=session_id)
        except LivestreamSession.DoesNotExist:
            return Response(
                {'session': 'Session not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not session.allow_questions:
            return Response(
                {'error': 'Questions are not allowed for this session.'},
                status=status.HTTP_403_FORBIDDEN
            )

        question = LivestreamQuestion.objects.create(
            session=session,
            asked_by=request.user,
            question_text=request.data.get('question_text', '')
        )

        return Response(
            LivestreamQuestionSerializer(question).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary='Answer a question',
        description='Answer a livestream question (instructor only)',
        request=LivestreamQuestionAnswerSerializer,
    )
    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        """Answer a question (instructor only)"""
        question = self.get_object()
        
        instructor = question.session.instructor
        if request.user != instructor and not is_admin_like(request.user):
            return Response(
                {'error': 'Only the instructor can answer questions.'},
                status=status.HTTP_403_FORBIDDEN
            )

        answer_text = request.data.get('answer', '')
        answer_status = request.data.get('status', 'answered')

        question.answer_text = answer_text
        question.answered_by = request.user
        question.answered_at = timezone.now()
        question.is_answered = answer_status == 'answered'
        question.save()

        return Response(LivestreamQuestionSerializer(question).data)