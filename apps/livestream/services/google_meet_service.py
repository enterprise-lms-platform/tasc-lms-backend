"""
Google Meet integration service for livestream sessions.
Creates Google Meet meetings via the Google Calendar API using a service account.
"""
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class GoogleMeetService:
    """
    Service class for Google Meet integration via Google Calendar API.

    Requires:
      - A Google Workspace service account JSON key file
      - Domain-wide delegation enabled for the service account
      - GOOGLE_MEET_SERVICE_ACCOUNT_FILE, GOOGLE_MEET_DELEGATED_USER in settings

    Methods mirror ZoomService for consistency.
    """

    def __init__(self):
        self.service_account_file = getattr(settings, 'GOOGLE_MEET_SERVICE_ACCOUNT_FILE', '')
        self.delegated_user = getattr(settings, 'GOOGLE_MEET_DELEGATED_USER', '')
        self.calendar_id = getattr(settings, 'GOOGLE_MEET_CALENDAR_ID', 'primary')
        self._service = None

    def _get_credentials(self):
        """
        Load service account credentials with domain-wide delegation.

        Returns:
            google.oauth2.service_account.Credentials
        """
        from apps.accounts.google_auth_views import service_account

        SCOPES = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/calendar.events',
        ]

        credentials = service_account.Credentials.from_service_account_file(
            self.service_account_file,
            scopes=SCOPES,
        )

        if self.delegated_user:
            credentials = credentials.with_subject(self.delegated_user)

        return credentials

    def _build_calendar_service(self):
        """
        Build and cache the Google Calendar API service object.

        Returns:
            googleapiclient.discovery.Resource
        """
        if self._service is None:
            from googleapiclient.discovery import build

            credentials = self._get_credentials()
            self._service = build('calendar', 'v3', credentials=credentials)

        return self._service

    def create_meeting(self, session_data):
        """
        Create a Google Calendar event with an auto-generated Google Meet link.

        Args:
            session_data: dict with keys:
                - topic: str (meeting title)
                - agenda: str (meeting description)
                - start_time: datetime
                - duration: int (minutes)
                - timezone: str (e.g. 'Africa/Kampala')
                - attendee_emails: list[str] (optional)

        Returns:
            dict: {
                'event_id': str,
                'conference_id': str,
                'meet_uri': str,
                'calendar_link': str,
                'html_link': str,
            }

        Raises:
            Exception: If Google Calendar API call fails
        """
        service = self._build_calendar_service()

        start_time = session_data['start_time']
        duration = session_data.get('duration', 60)
        end_time = start_time + timedelta(minutes=duration)
        tz = session_data.get('timezone', 'UTC')

        event_body = {
            'summary': session_data.get('topic', 'Livestream Session'),
            'description': session_data.get('agenda', ''),
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': tz,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': tz,
            },
            'conferenceData': {
                'createRequest': {
                    'requestId': f"tasc-lms-{start_time.strftime('%Y%m%d%H%M%S')}",
                    'conferenceSolutionKey': {
                        'type': 'hangoutsMeet',
                    },
                },
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 15},
                    {'method': 'email', 'minutes': 60},
                ],
            },
        }

        # Add attendees if provided
        attendee_emails = session_data.get('attendee_emails', [])
        if attendee_emails:
            event_body['attendees'] = [
                {'email': email} for email in attendee_emails
            ]

        try:
            event = service.events().insert(
                calendarId=self.calendar_id,
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates='all' if attendee_emails else 'none',
            ).execute()

            conference_data = event.get('conferenceData', {})
            entry_points = conference_data.get('entryPoints', [])
            meet_uri = ''
            for ep in entry_points:
                if ep.get('entryPointType') == 'video':
                    meet_uri = ep.get('uri', '')
                    break

            result = {
                'event_id': event.get('id', ''),
                'conference_id': conference_data.get('conferenceId', ''),
                'meet_uri': meet_uri,
                'calendar_link': event.get('htmlLink', ''),
                'html_link': event.get('htmlLink', ''),
            }

            logger.info(
                f"Google Meet meeting created: {result['conference_id']} "
                f"for event {result['event_id']}"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to create Google Meet meeting: {e}")
            raise

    def update_meeting(self, event_id, session_data):
        """
        Update an existing Google Calendar event.

        Args:
            event_id: str - Google Calendar event ID
            session_data: dict with updated fields (topic, agenda, start_time, duration, timezone)

        Returns:
            dict: Updated event data

        Raises:
            Exception: If Google Calendar API call fails
        """
        service = self._build_calendar_service()

        # Fetch existing event first
        try:
            existing = service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()
        except Exception as e:
            logger.error(f"Failed to fetch event {event_id} for update: {e}")
            raise

        # Apply updates
        if 'topic' in session_data:
            existing['summary'] = session_data['topic']
        if 'agenda' in session_data:
            existing['description'] = session_data['agenda']
        if 'start_time' in session_data:
            tz = session_data.get('timezone', existing['start'].get('timeZone', 'UTC'))
            duration = session_data.get('duration', 60)
            start_time = session_data['start_time']
            end_time = start_time + timedelta(minutes=duration)
            existing['start'] = {'dateTime': start_time.isoformat(), 'timeZone': tz}
            existing['end'] = {'dateTime': end_time.isoformat(), 'timeZone': tz}

        try:
            updated = service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=existing,
                conferenceDataVersion=1,
            ).execute()

            logger.info(f"Google Meet event updated: {event_id}")
            return {
                'event_id': updated.get('id', ''),
                'html_link': updated.get('htmlLink', ''),
            }

        except Exception as e:
            logger.error(f"Failed to update Google Meet event {event_id}: {e}")
            raise

    def delete_meeting(self, event_id):
        """
        Delete a Google Calendar event (and its associated Meet link).

        Args:
            event_id: str - Google Calendar event ID

        Returns:
            bool: True if deleted successfully

        Raises:
            Exception: If Google Calendar API call fails
        """
        service = self._build_calendar_service()

        try:
            service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
                sendUpdates='all',
            ).execute()

            logger.info(f"Google Meet event deleted: {event_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete Google Meet event {event_id}: {e}")
            raise

    def get_meeting(self, event_id):
        """
        Get details of a Google Calendar event.

        Args:
            event_id: str - Google Calendar event ID

        Returns:
            dict: Event details including conference data

        Raises:
            Exception: If Google Calendar API call fails
        """
        service = self._build_calendar_service()

        try:
            event = service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()

            conference_data = event.get('conferenceData', {})
            entry_points = conference_data.get('entryPoints', [])
            meet_uri = ''
            for ep in entry_points:
                if ep.get('entryPointType') == 'video':
                    meet_uri = ep.get('uri', '')
                    break

            return {
                'event_id': event.get('id', ''),
                'conference_id': conference_data.get('conferenceId', ''),
                'meet_uri': meet_uri,
                'status': event.get('status', ''),
                'html_link': event.get('htmlLink', ''),
                'start': event.get('start', {}),
                'end': event.get('end', {}),
                'attendees': event.get('attendees', []),
            }

        except Exception as e:
            logger.error(f"Failed to get Google Meet event {event_id}: {e}")
            raise


class GoogleMeetWebhookHandler:
    """
    Handle Google Calendar push notification webhooks.

    Google Calendar uses push notifications (watch channels) that notify
    when a resource changes. Unlike Zoom, the notification doesn't contain
    the change details — we must re-fetch the event to determine what changed.
    """

    def __init__(self):
        self.meet_service = GoogleMeetService()

    def handle_webhook(self, request):
        """
        Process incoming Google Calendar push notification.

        Google sends headers:
            X-Goog-Channel-ID: channel ID
            X-Goog-Resource-ID: resource ID
            X-Goog-Resource-State: sync | exists | not_exists
            X-Goog-Resource-URI: the resource URI

        Args:
            request: Django request object

        Returns:
            dict: Processing result
        """
        channel_id = request.headers.get('X-Goog-Channel-ID', '')
        resource_state = request.headers.get('X-Goog-Resource-State', '')
        resource_uri = request.headers.get('X-Goog-Resource-URI', '')

        logger.info(
            f"Google Calendar webhook received: channel={channel_id}, "
            f"state={resource_state}, uri={resource_uri}"
        )

        if resource_state == 'sync':
            # Initial sync notification — just acknowledge
            return {'status': 'sync_acknowledged'}

        if resource_state == 'exists':
            return self._handle_event_updated(channel_id, resource_uri)

        if resource_state == 'not_exists':
            return self._handle_event_deleted(channel_id)

        return {'status': 'unhandled', 'state': resource_state}

    def _handle_event_updated(self, channel_id, resource_uri):
        """
        Handle event update notification.
        Re-fetches the event to determine what changed and updates session accordingly.

        Args:
            channel_id: str - The watch channel ID (maps to our session)
            resource_uri: str - The resource URI

        Returns:
            dict: Processing result
        """
        from apps.livestream.models import LivestreamSession

        try:
            # Find session by channel ID (stored in calendar_event_id or a dedicated field)
            session = LivestreamSession.objects.filter(
                google_meet_event_id__isnull=False,
                platform='google_meet',
            ).first()

            if not session:
                logger.warning(f"No session found for channel {channel_id}")
                return {'status': 'session_not_found'}

            # Re-fetch event details
            event_data = self.meet_service.get_meeting(session.google_meet_event_id)

            # Update session status based on event status
            event_status = event_data.get('status', '')
            if event_status == 'cancelled':
                session.status = 'cancelled'
                session.save(update_fields=['status'])
                logger.info(f"Session {session.id} cancelled via Google Calendar")

            return {
                'status': 'processed',
                'session_id': str(session.id),
                'event_status': event_status,
            }

        except Exception as e:
            logger.error(f"Error handling Google Calendar webhook: {e}")
            return {'status': 'error', 'message': str(e)}

    def _handle_event_deleted(self, channel_id):
        """
        Handle event deletion notification.

        Args:
            channel_id: str - The watch channel ID

        Returns:
            dict: Processing result
        """
        logger.info(f"Google Calendar event deleted for channel {channel_id}")
        return {'status': 'deletion_noted', 'channel_id': channel_id}
