"""
Zoom API integration service for livestream sessions.
Handles automatic meeting creation, management, and webhooks.
"""
import requests
import base64
import json
import time
import hashlib
import hmac
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
import jwt


class ZoomService:
    """
    Service class for Zoom API integration.
    Handles meeting creation, updates, deletions, and webhooks.
    """

    def __init__(self):
        self.api_key = settings.ZOOM_API_KEY
        self.api_secret = settings.ZOOM_API_SECRET
        self.account_id = settings.ZOOM_ACCOUNT_ID
        self.base_url = "https://api.zoom.us/v2"
        self.webhook_secret = settings.ZOOM_WEBHOOK_SECRET
        self._access_token = None
        self._token_expiry = 0

    def _get_access_token(self):
        """
        Get OAuth access token for Zoom API using Server-to-Server OAuth.
        """
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={self.account_id}"

        auth_string = f"{self.api_key}:{self.api_secret}"
        base64_auth = base64.b64encode(auth_string.encode()).decode()

        headers = {
            "Authorization": f"Basic {base64_auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        response = requests.post(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            self._access_token = data['access_token']
            self._token_expiry = time.time() + data['expires_in'] - 60
            return self._access_token
        else:
            raise Exception(f"Failed to get Zoom access token: {response.text}")

    def _get_headers(self):
        """Get headers with authorization"""
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def create_meeting(self, session_data):
        """
        Create a Zoom meeting from session data.

        Args:
            session_data: Dict with meeting details
                - topic: Meeting title
                - agenda: Meeting description
                - start_time: Datetime object
                - duration: Minutes
                - timezone: Timezone string
                - settings: Meeting settings dict

        Returns:
            dict: Zoom meeting details
        """
        headers = self._get_headers()

        start_time = session_data['start_time']
        if isinstance(start_time, datetime):
            start_time = start_time.strftime('%Y-%m-%dT%H:%M:%S')

        meeting_data = {
            "topic": session_data['topic'][:200],
            "type": 2,
            "start_time": start_time,
            "duration": session_data['duration'],
            "timezone": session_data.get('timezone', 'UTC'),
            "agenda": session_data.get('agenda', '')[:2000],
            "settings": {
                "host_video": session_data.get('host_video', True),
                "participant_video": session_data.get('participant_video', False),
                "join_before_host": session_data.get('join_before_host', False),
                "mute_upon_entry": session_data.get('mute_upon_entry', True),
                "waiting_room": session_data.get('waiting_room', True),
                "audio": "both",
                "auto_recording": session_data.get('auto_recording', 'cloud'),
                "approval_type": 2,
                "registration_type": 1,
                "enforce_login": False,
                "alternative_hosts": "",
                "global_dial_in_countries": ["US"],
            }
        }

        if session_data.get('recurrence'):
            meeting_data["type"] = 8
            meeting_data["recurrence"] = session_data['recurrence']

        response = requests.post(
            f"{self.base_url}/users/me/meetings",
            headers=headers,
            json=meeting_data
        )

        if response.status_code == 201:
            data = response.json()
            return {
                'success': True,
                'meeting_id': str(data['id']),
                'meeting_uuid': data['uuid'],
                'join_url': data['join_url'],
                'start_url': data['start_url'],
                'password': data.get('password', ''),
                'host_email': data.get('host_email', ''),
                'settings': data.get('settings', {}),
                'raw_data': data
            }
        else:
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }

    def update_meeting(self, meeting_id, session_data):
        """
        Update an existing Zoom meeting.
        """
        headers = self._get_headers()

        meeting_data = {
            "topic": session_data['topic'][:200],
            "agenda": session_data.get('agenda', '')[:2000],
        }

        if 'start_time' in session_data:
            start_time = session_data['start_time']
            if isinstance(start_time, datetime):
                start_time = start_time.strftime('%Y-%m-%dT%H:%M:%S')
            meeting_data["start_time"] = start_time

        if 'duration' in session_data:
            meeting_data["duration"] = session_data['duration']

        if 'settings' in session_data:
            meeting_data["settings"] = session_data['settings']

        response = requests.patch(
            f"{self.base_url}/meetings/{meeting_id}",
            headers=headers,
            json=meeting_data
        )

        if response.status_code == 204:
            return {'success': True}
        else:
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }

    def delete_meeting(self, meeting_id):
        """
        Delete a Zoom meeting.
        """
        headers = self._get_headers()

        response = requests.delete(
            f"{self.base_url}/meetings/{meeting_id}",
            headers=headers
        )

        if response.status_code == 204:
            return {'success': True}
        else:
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }

    def get_meeting(self, meeting_id):
        """
        Get meeting details from Zoom.
        """
        headers = self._get_headers()

        response = requests.get(
            f"{self.base_url}/meetings/{meeting_id}",
            headers=headers
        )

        if response.status_code == 200:
            return {'success': True, 'data': response.json()}
        else:
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }

    def get_meeting_recordings(self, meeting_id):
        """
        Get cloud recordings for a meeting.
        """
        headers = self._get_headers()

        response = requests.get(
            f"{self.base_url}/meetings/{meeting_id}/recordings",
            headers=headers
        )

        if response.status_code == 200:
            return {'success': True, 'data': response.json()}
        else:
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }

    def get_meeting_participants(self, meeting_id):
        """
        Get participants of a completed meeting.
        """
        headers = self._get_headers()

        response = requests.get(
            f"{self.base_url}/report/meetings/{meeting_id}/participants",
            headers=headers
        )

        if response.status_code == 200:
            return {'success': True, 'data': response.json()}
        else:
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }

    def verify_webhook(self, request):
        """
        Verify Zoom webhook signature.
        """
        signature = request.headers.get('x-zm-signature', '')
        timestamp = request.headers.get('x-zm-request-timestamp', '')
        payload = request.body

        message = f"v0:{timestamp}:{payload.decode('utf-8')}"

        expected = hmac.new(
            self.webhook_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(f"v0={expected}", signature)

    def create_recurring_meeting(self, session_data, recurrence_pattern, recurrence_end):
        """
        Create a recurring meeting series.
        """
        recurrence_map = {
            'daily': {'type': 1, 'repeat_interval': 1},
            'weekly': {'type': 2, 'repeat_interval': 1},
            'biweekly': {'type': 2, 'repeat_interval': 2},
            'monthly': {'type': 3, 'repeat_interval': 1},
        }

        recurrence = recurrence_map.get(recurrence_pattern, {'type': 1, 'repeat_interval': 1})

        if recurrence_end:
            recurrence['end_date_time'] = recurrence_end.strftime('%Y-%m-%dT%H:%M:%SZ')

        if recurrence_pattern in ['weekly', 'biweekly'] and session_data.get('weekly_days'):
            recurrence['weekly_days'] = session_data['weekly_days']

        session_data['recurrence'] = recurrence
        return self.create_meeting(session_data)


class ZoomWebhookHandler:
    """
    Handle Zoom webhook events.
    Updates session status, attendance, and recordings.
    """

    def __init__(self):
        self.zoom_service = ZoomService()

    def handle_webhook(self, request):
        """
        Handle incoming Zoom webhook.
        """
        if not self.zoom_service.verify_webhook(request):
            return {'success': False, 'error': 'Invalid signature'}

        data = json.loads(request.body)
        event = data.get('event')
        payload = data.get('payload', {})

        if event == 'meeting.started':
            return self._handle_meeting_started(payload)
        elif event == 'meeting.ended':
            return self._handle_meeting_ended(payload)
        elif event == 'meeting.participant_joined':
            return self._handle_participant_joined(payload)
        elif event == 'meeting.participant_left':
            return self._handle_participant_left(payload)
        elif event == 'recording.completed':
            return self._handle_recording_completed(payload)
        elif event == 'recording.transcript_completed':
            return self._handle_transcript_completed(payload)
        else:
            return {'success': True, 'message': f'Event {event} received'}

    def _handle_meeting_started(self, payload):
        """Handle meeting.started webhook"""
        from apps.livestream.models import LivestreamSession

        meeting_id = payload.get('object', {}).get('id')
        if not meeting_id:
            return {'success': False, 'error': 'No meeting ID'}

        try:
            session = LivestreamSession.objects.get(zoom_meeting_id=str(meeting_id))
            session.start_session()
            return {'success': True, 'session_id': str(session.id)}
        except LivestreamSession.DoesNotExist:
            return {'success': False, 'error': 'Session not found'}

    def _handle_meeting_ended(self, payload):
        """Handle meeting.ended webhook"""
        from apps.livestream.models import LivestreamSession

        meeting_id = payload.get('object', {}).get('id')
        if not meeting_id:
            return {'success': False, 'error': 'No meeting ID'}

        try:
            session = LivestreamSession.objects.get(zoom_meeting_id=str(meeting_id))
            session.end_session()
            return {'success': True, 'session_id': str(session.id)}
        except LivestreamSession.DoesNotExist:
            return {'success': False, 'error': 'Session not found'}

    def _handle_participant_joined(self, payload):
        """Handle meeting.participant_joined webhook"""
        from apps.livestream.models import LivestreamSession, LivestreamAttendance

        meeting_id = payload.get('object', {}).get('id')
        participant = payload.get('object', {}).get('participant', {})

        if not meeting_id or not participant:
            return {'success': False, 'error': 'Missing data'}

        try:
            session = LivestreamSession.objects.get(zoom_meeting_id=str(meeting_id))

            email = participant.get('email')
            if not email:
                return {'success': False, 'error': 'No email'}

            from django.contrib.auth import get_user_model
            User = get_user_model()

            try:
                user = User.objects.get(email=email)
                attendance, _ = LivestreamAttendance.objects.get_or_create(
                    session=session,
                    learner=user
                )
                attendance.mark_joined({
                    'participant_id': participant.get('participant_id'),
                    'device': participant.get('device', '')
                })
                return {'success': True, 'attendance_id': str(attendance.id)}
            except User.DoesNotExist:
                return {'success': False, 'error': 'User not found'}

        except LivestreamSession.DoesNotExist:
            return {'success': False, 'error': 'Session not found'}

    def _handle_participant_left(self, payload):
        """Handle meeting.participant_left webhook"""
        from apps.livestream.models import LivestreamSession, LivestreamAttendance

        meeting_id = payload.get('object', {}).get('id')
        participant = payload.get('object', {}).get('participant', {})

        if not meeting_id or not participant:
            return {'success': False, 'error': 'Missing data'}

        try:
            session = LivestreamSession.objects.get(zoom_meeting_id=str(meeting_id))

            email = participant.get('email')
            if not email:
                return {'success': False, 'error': 'No email'}

            from django.contrib.auth import get_user_model
            User = get_user_model()

            try:
                user = User.objects.get(email=email)
                attendance = LivestreamAttendance.objects.get(
                    session=session,
                    learner=user
                )
                attendance.mark_left()
                return {'success': True, 'attendance_id': str(attendance.id)}
            except (User.DoesNotExist, LivestreamAttendance.DoesNotExist):
                return {'success': False, 'error': 'Attendance not found'}

        except LivestreamSession.DoesNotExist:
            return {'success': False, 'error': 'Session not found'}

    def _handle_recording_completed(self, payload):
        """Handle recording.completed webhook"""
        from apps.livestream.models import LivestreamSession, LivestreamRecording

        meeting_id = payload.get('object', {}).get('id')
        recording_files = payload.get('object', {}).get('recording_files', [])

        if not meeting_id:
            return {'success': False, 'error': 'No meeting ID'}

        try:
            session = LivestreamSession.objects.get(zoom_meeting_id=str(meeting_id))

            for file in recording_files:
                recording, created = LivestreamRecording.objects.get_or_create(
                    zoom_recording_id=file['id'],
                    defaults={
                        'session': session,
                        'zoom_meeting_id': meeting_id,
                        'recording_type': file.get('recording_type', 'unknown'),
                        'file_url': file.get('play_url', ''),
                        'download_url': file.get('download_url', ''),
                        'file_size': file.get('file_size', 0),
                        'file_extension': file.get('file_extension', 'mp4'),
                        'recording_start': file.get('recording_start'),
                        'recording_end': file.get('recording_end'),
                        'duration_seconds': file.get('duration', 0),
                    }
                )

            if recording_files:
                main_recording = recording_files[0]
                session.update_recording({
                    'share_url': main_recording.get('play_url', ''),
                    'recording_start': main_recording.get('recording_start'),
                    'recording_end': main_recording.get('recording_end'),
                    'duration': main_recording.get('duration', 0),
                    'download_url': main_recording.get('download_url', '')
                })

            return {'success': True, 'session_id': str(session.id)}

        except LivestreamSession.DoesNotExist:
            return {'success': False, 'error': 'Session not found'}

    def _handle_transcript_completed(self, payload):
        """Handle recording.transcript_completed webhook"""
        return {'success': True, 'message': 'Transcript received'}
