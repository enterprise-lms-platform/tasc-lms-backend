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

from apps.audit import models

from .models import (
    LivestreamSession, LivestreamAttendance, 
    LivestreamRecording
)
from .serializers import (
    LivestreamSessionSerializer, LivestreamSessionCreateSerializer,
    LivestreamSessionUpdateSerializer, LivestreamAttendanceSerializer,
    LivestreamActionSerializer,
    LivestreamQuestionAnswerSerializer, LivestreamRecordingSerializer,
    UserTimezoneSerializer
)
from .services.zoom_service import ZoomService, ZoomWebhookHandler
from .services.calendar_service import CalendarService, TimezoneService
from  .permissions import IsInstructorOrReadOnly


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
        if not hasattr(user, 'role') or user.role not in ['instructor', 'admin', 'super_admin']:
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
        """Create a new livestream session with Zoom integration"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Save session first
        session = serializer.save()
        
        # Create Zoom meeting automatically
        if session.platform == 'zoom':
            try:
                zoom_service = ZoomService()
                
                # Prepare meeting data
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
                
                # Handle recurring meetings
                if session.is_recurring and session.recurrence_pattern != 'none':
                    result = zoom_service.create_recurring_meeting(
                        meeting_data,
                        session.recurrence_pattern,
                        session.recurrence_end_date
                    )
                else:
                    result = zoom_service.create_meeting(meeting_data)
                
                if result['success']:
                    # Update session with Zoom details
                    session.zoom_meeting_id = result['meeting_id']
                    session.zoom_meeting_uuid = result.get('meeting_uuid', '')
                    session.join_url = result['join_url']
                    session.start_url = result['start_url']
                    session.password = result.get('password', '')
                    session.save()
                else:
                    # Log error but don't fail
                    session.metadata = session.metadata or {}
                    session.metadata['zoom_error'] = result.get('error', 'Unknown error')
                    session.save()
                    
            except Exception as e:
                # Log error but continue
                session.metadata = session.metadata or {}
                session.metadata['zoom_error'] = str(e)
                session.save()
        
        # If recurring, create child sessions
        if session.is_recurring and session.recurrence_pattern != 'none':
            self._create_recurring_sessions(session)
        
        return Response(
            LivestreamSessionSerializer(session, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )
    
    def _create_recurring_sessions(self, parent_session):
        """Create child sessions for recurring pattern"""
        # Implementation for creating recurring session instances
        # This would generate individual sessions based on pattern
        pass
    
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
        
        # Update on Zoom if meeting exists
        if instance.zoom_meeting_id and instance.platform == 'zoom':
            try:
                zoom_service = ZoomService()
                zoom_service.update_meeting(
                    instance.zoom_meeting_id,
                    {
                        'topic': serializer.validated_data.get('title', instance.title),
                        'agenda': serializer.validated_data.get('description', instance.description),
                        'start_time': serializer.validated_data.get('start_time', instance.start_time),
                        'duration': serializer.validated_data.get('duration_minutes', instance.duration_minutes),
                    }
                )
            except Exception as e:
                # Log error but continue
                instance.metadata = instance.metadata or {}
                instance.metadata['zoom_update_error'] = str(e)
        
        self.perform_update(serializer)
        
        return Response(
            LivestreamSessionSerializer(instance, context={'request': request}).data
        )
    
    @extend_schema(
        summary='Delete session',
        description='Delete a livestream session (also deletes Zoom meeting)'
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Delete from Zoom
        if instance.zoom_meeting_id and instance.platform == 'zoom':
            try:
                zoom_service = ZoomService()
                zoom_service.delete_meeting(instance.zoom_meeting_id)
            except Exception as e:
                # Log error but continue
                pass
        
        return super().destroy(request, *args, **kwargs)
    
    @extend_schema(
        summary='Take action on session',
        description='Start, end, cancel, or send reminders for a session',
        request=LivestreamActionSerializer,
        responses={200: LivestreamSessionSerializer}
    )
    @action(detail=True, methods=['post'])
    def action(self, request, pk=None):
        """Take action on a session (start/end/cancel/remind)"""
        session = self.get_object()
        serializer = LivestreamActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action = serializer.validated_data['action']
        reason = serializer.validated_data.get('reason', '')
        
        if action == 'start':
            if session.status != 'scheduled':
                return Response(
                    {'error': 'Only scheduled sessions can be started'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            session.start_session()
            
        elif action == 'end':
            if session.status != 'live':
                return Response(
                    {'error': 'Only live sessions can be ended'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            session.end_session()
            
        elif action == 'cancel':
            if session.status in ['ended', 'cancelled']:
                return Response(
                    {'error': 'Session already ended or cancelled'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            session.cancel_session(reason)
            
        elif action == 'remind':
            # Send reminder to enrolled learners
            self._send_reminder(session)
            session.reminder_sent_15m = True
            session.save()
            
        elif action == 'send_recording':
            # Send recording link to learners
            self._send_recording_link(session)
        
        return Response(
            LivestreamSessionSerializer(session, context={'request': request}).data
        )
    
    # def _send_reminder(self, session):
    #     """Send reminder to enrolled learners"""
    #     # Implement email/notification sending
    #     from .tasks import send_session_reminder
    #     send_session_reminder.delay(session.id)
    
    # def _send_recording_link(self, session):
    #     """Send recording link to enrolled learners"""
    #     from ..tasks import send_recording_link
    #     send_recording_link.delay(session.id)
    
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
        if request.user != session.instructor and not request.user.role in ['admin', 'super_admin']:
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
        if request.user != session.instructor and not request.user.role in ['admin', 'super_admin']:
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
        ).aggregate(avg=models.Avg('duration_seconds'))['avg'] or 0
        
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
        if user.role in ['admin', 'super_admin']:
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
        if not user.role in ['instructor', 'admin', 'super_admin']:
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


@extend_schema(tags=['Livestream - Webhooks'])
class LivestreamWebhookView(viewsets.GenericViewSet):
    """
    Handle Zoom webhooks for livestream sessions.
    Updates session status, attendance, and recordings automatically.
    """
    
    permission_classes = [AllowAny]
    
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
        summary='Validate webhook',
        description='Validate Zoom webhook signature',
        parameters=[
            OpenApiParameter(name='x-zm-signature', location=OpenApiParameter.HEADER),
            OpenApiParameter(name='x-zm-request-timestamp', location=OpenApiParameter.HEADER),
        ]
    )
    @action(detail=False, methods=['get'], url_path='validate')
    def validate_webhook(self, request):
        """Validate webhook endpoint"""
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