"""
Google Meet integration service for livestream sessions.
Creates Google Meet meetings via the Google Calendar API using a service account.
"""
import logging
import os
import traceback
import json
from datetime import datetime, timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from typing import Dict, Any, Optional, List, Union
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleMeetServiceError(Exception):
    """Custom exception for Google Meet service errors."""
    pass


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
        
        # Validate configuration on initialization
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """
        Validate that all required configuration is present and valid.
        
        Raises:
            GoogleMeetServiceError: If configuration is invalid
        """
        errors = []
        
        # Check service account file path
        if not self.service_account_file:
            errors.append("GOOGLE_MEET_SERVICE_ACCOUNT_FILE is not set in settings")
        else:
            # Check if file exists
            if not os.path.exists(self.service_account_file):
                # Try to resolve relative path from project root
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                abs_path = os.path.join(project_root, self.service_account_file)
                
                if os.path.exists(abs_path):
                    self.service_account_file = abs_path
                    logger.info(f"Resolved service account file to absolute path: {abs_path}")
                else:
                    errors.append(
                        f"Service account file not found at: {self.service_account_file}\n"
                        f"Also checked: {abs_path}\n"
                        f"Please ensure the file exists and the path is correct."
                    )
        
        # Check delegated user
        if not self.delegated_user:
            errors.append("GOOGLE_MEET_DELEGATED_USER is not set in settings")
        elif '@' not in self.delegated_user:
            errors.append(f"GOOGLE_MEET_DELEGATED_USER should be an email address: {self.delegated_user}")
        
        # Log warnings but don't raise during initialization
        if errors:
            for error in errors:
                logger.warning(f"Configuration warning: {error}")
            # Don't raise here - allow initialization for debugging, but methods will fail

    def _get_credentials(self):
        """
        Load service account credentials with domain-wide delegation.

        Returns:
            google.oauth2.service_account.Credentials

        Raises:
            GoogleMeetServiceError: If credentials cannot be loaded
        """
        try:
            from google.oauth2 import service_account
            from google.auth.exceptions import GoogleAuthError
        except ImportError as e:
            logger.error(f"Failed to import Google libraries: {e}")
            raise GoogleMeetServiceError(
                "Google libraries not installed. Run: pip install google-auth-httplib2 google-auth-oauthlib google-api-python-client"
            ) from e

        # Validate file exists (double-check)
        if not os.path.exists(self.service_account_file):
            raise GoogleMeetServiceError(
                f"Service account file does not exist: {self.service_account_file}\n"
                f"Please check the path and ensure the file is present."
            )

        SCOPES = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/calendar.events',
        ]

        try:
            # Load credentials from file
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=SCOPES,
            )
            
            # Apply domain-wide delegation if delegated user is provided
            if self.delegated_user:
                credentials = credentials.with_subject(self.delegated_user)
                logger.debug(f"Using delegated user: {self.delegated_user}")
            
            return credentials

        except FileNotFoundError as e:
            logger.error(f"Service account file not found: {e}")
            raise GoogleMeetServiceError(
                f"Service account file not found: {self.service_account_file}"
            ) from e
        except ValueError as e:
            logger.error(f"Invalid service account file format: {e}")
            raise GoogleMeetServiceError(
                f"Invalid service account JSON file: {e}"
            ) from e
        except GoogleAuthError as e:
            logger.error(f"Google authentication error: {e}")
            raise GoogleMeetServiceError(
                f"Google authentication failed: {e}"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error loading credentials: {e}")
            logger.error(traceback.format_exc())
            raise GoogleMeetServiceError(
                f"Failed to load credentials: {str(e)}"
            ) from e

    def _build_calendar_service(self):
        """
        Build and cache the Google Calendar API service object.

        Returns:
            googleapiclient.discovery.Resource

        Raises:
            GoogleMeetServiceError: If service cannot be built
        """
        if self._service is not None:
            return self._service

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
            from google.auth.transport.requests import Request
        except ImportError as e:
            logger.error(f"Failed to import Google API client: {e}")
            raise GoogleMeetServiceError(
                "Google API client not installed. Run: pip install google-api-python-client"
            ) from e

        try:
            credentials = self._get_credentials()
            
            # Refresh credentials if needed
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                logger.debug("Refreshed expired credentials")
            
            self._service = build('calendar', 'v3', credentials=credentials)
            logger.debug("Google Calendar service built successfully")
            return self._service

        except HttpError as e:
            logger.error(f"Google API HTTP error: {e}")
            status_code = e.resp.status if hasattr(e, 'resp') else 500
            error_details = e.error_details if hasattr(e, 'error_details') else str(e)
            
            if status_code == 403:
                raise GoogleMeetServiceError(
                    f"Permission denied: Service account may not have access to calendar. "
                    f"Ensure domain-wide delegation is enabled and calendar is shared with {self.delegated_user}"
                ) from e
            elif status_code == 404:
                raise GoogleMeetServiceError(
                    f"Calendar not found: {self.calendar_id}. "
                    f"Check GOOGLE_MEET_CALENDAR_ID setting."
                ) from e
            else:
                raise GoogleMeetServiceError(
                    f"Google API error (HTTP {status_code}): {error_details}"
                ) from e
        except Exception as e:
            logger.error(f"Failed to build calendar service: {e}")
            logger.error(traceback.format_exc())
            raise GoogleMeetServiceError(
                f"Failed to build calendar service: {str(e)}"
            ) from e

    def check_calendar_conference_support(self) -> Dict[str, Any]:
        """
        Check if the calendar supports Google Meet conferences.
        
        Returns:
            dict: Calendar information and supported conference types
            
        Raises:
            GoogleMeetServiceError: If check fails
        """
        try:
            service = self._build_calendar_service()
            
            # Get calendar details
            calendar = service.calendars().get(calendarId=self.calendar_id).execute()
            
            # Get conference properties
            conference_props = calendar.get('conferenceProperties', {})
            allowed_types = conference_props.get('allowedConferenceSolutionTypes', [])
            
            result = {
                'calendar_id': self.calendar_id,
                'calendar_summary': calendar.get('summary', 'Unknown'),
                'calendar_description': calendar.get('description', ''),
                'time_zone': calendar.get('timeZone', 'UTC'),
                'allowed_conference_types': allowed_types,
                'supports_meet': 'hangoutsMeet' in allowed_types,
                'access_role': calendar.get('accessRole', 'unknown'),
                'success': True
            }
            
            logger.info(f"Calendar '{result['calendar_summary']}' supports: {allowed_types}")
            
            if not result['supports_meet']:
                logger.warning(
                    f"⚠️ Calendar does NOT support Google Meet conferences!\n"
                    f"This usually means you're using a free Gmail account.\n"
                    f"You need a Google Workspace account with Meet enabled."
                )
            
            return result
            
        except HttpError as e:
            logger.error(f"Failed to check calendar: {e}")
            status_code = e.resp.status if hasattr(e, 'resp') else 500
            
            if status_code == 404:
                raise GoogleMeetServiceError(
                    f"Calendar not found: {self.calendar_id}. "
                    f"Please check that this calendar exists and is shared with the service account."
                ) from e
            elif status_code == 403:
                raise GoogleMeetServiceError(
                    f"Permission denied accessing calendar: {self.calendar_id}. "
                    f"Ensure the calendar is shared with the service account email: {self._get_service_account_email()}"
                ) from e
            else:
                raise GoogleMeetServiceError(
                    f"Failed to check calendar (HTTP {status_code}): {e}"
                ) from e
        except Exception as e:
            logger.error(f"Unexpected error checking calendar: {e}")
            logger.error(traceback.format_exc())
            raise GoogleMeetServiceError(
                f"Failed to check calendar: {str(e)}"
            ) from e

    def _get_service_account_email(self) -> str:
        """Extract service account email from credentials file."""
        try:
            with open(self.service_account_file, 'r') as f:
                data = json.load(f)
                return data.get('client_email', 'unknown')
        except:
            return 'unknown'

    def diagnose_calendar_access(self) -> Dict[str, Any]:
        """
        Comprehensive diagnostic of calendar access and permissions.
        
        Returns:
            dict: Detailed diagnostic information
        """
        diagnostics = {
            'configuration': {
                'service_account_file': self.service_account_file,
                'file_exists': os.path.exists(self.service_account_file),
                'delegated_user': self.delegated_user,
                'calendar_id': self.calendar_id,
            },
            'checks': {},
            'errors': []
        }
        
        # Check file exists
        if not diagnostics['configuration']['file_exists']:
            diagnostics['errors'].append("Service account file not found")
        
        # Try to load credentials
        try:
            credentials = self._get_credentials()
            diagnostics['checks']['credentials_loaded'] = True
            diagnostics['checks']['service_account_email'] = self._get_service_account_email()
        except Exception as e:
            diagnostics['checks']['credentials_loaded'] = False
            diagnostics['errors'].append(f"Failed to load credentials: {str(e)}")
            return diagnostics
        
        # Try to build service
        try:
            service = self._build_calendar_service()
            diagnostics['checks']['service_built'] = True
        except Exception as e:
            diagnostics['checks']['service_built'] = False
            diagnostics['errors'].append(f"Failed to build service: {str(e)}")
            return diagnostics
        
        # Check calendar access
        try:
            calendar_info = self.check_calendar_conference_support()
            diagnostics['checks']['calendar_access'] = True
            diagnostics['calendar_info'] = calendar_info
        except Exception as e:
            diagnostics['checks']['calendar_access'] = False
            diagnostics['errors'].append(f"Failed to access calendar: {str(e)}")
        
        # Try to list upcoming events (tests read permission)
        try:
            now = datetime.utcnow().isoformat() + 'Z'
            events = service.events().list(
                calendarId=self.calendar_id,
                timeMin=now,
                maxResults=5,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            diagnostics['checks']['can_list_events'] = True
            diagnostics['sample_events'] = len(events.get('items', []))
        except Exception as e:
            diagnostics['checks']['can_list_events'] = False
            diagnostics['errors'].append(f"Cannot list events: {str(e)}")
        
        return diagnostics

    def _validate_session_data(self, session_data: Dict[str, Any]) -> None:
        """
        Validate session data before creating/updating a meeting.

        Args:
            session_data: Dictionary with meeting details

        Raises:
            GoogleMeetServiceError: If validation fails
        """
        required_fields = ['topic', 'start_time']
        missing_fields = [field for field in required_fields if field not in session_data]
        
        if missing_fields:
            raise GoogleMeetServiceError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        # Validate start_time is datetime
        start_time = session_data['start_time']
        if not isinstance(start_time, datetime):
            raise GoogleMeetServiceError(
                f"start_time must be a datetime object, got {type(start_time)}"
            )

        # Validate duration if provided
        duration = session_data.get('duration', 60)
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise GoogleMeetServiceError(
                f"duration must be a positive number, got {duration}"
            )
        if duration > 480:  # 8 hours max
            raise GoogleMeetServiceError(
                f"duration cannot exceed 480 minutes (8 hours), got {duration}"
            )

        # Validate start_time is not too far in the past
        if start_time < timezone.now() - timedelta(minutes=5):
            logger.warning(f"Creating meeting with start time in the past: {start_time}")

        # Validate attendee emails if provided
        attendee_emails = session_data.get('attendee_emails', [])
        for email in attendee_emails:
            if not isinstance(email, str) or '@' not in email:
                raise GoogleMeetServiceError(
                    f"Invalid email format: {email}"
                )

    def create_meeting(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a Google Calendar event with an auto-generated Google Meet link.

        Args:
            session_data: dict with keys:
                - topic: str (meeting title)
                - agenda: str (meeting description) - optional
                - start_time: datetime
                - duration: int (minutes) - default 60
                - timezone: str (e.g. 'Africa/Kampala') - default 'UTC'
                - attendee_emails: list[str] (optional)

        Returns:
            dict: {
                'event_id': str,
                'conference_id': str,
                'meet_uri': str,
                'calendar_link': str,
                'html_link': str,
                'success': bool
            }

        Raises:
            GoogleMeetServiceError: If meeting creation fails
        """
        try:
            # Validate input data
            self._validate_session_data(session_data)
            
            # Build service
            service = self._build_calendar_service()

            # Calculate times
            start_time = session_data['start_time']
            duration = session_data.get('duration', 60)
            end_time = start_time + timedelta(minutes=duration)
            tz = session_data.get('timezone', 'UTC')

            # Ensure timezone awareness
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
                logger.debug(f"Made start_time timezone-aware: {start_time}")
            if timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)

            # Generate unique request ID
            import uuid
            request_id = str(uuid.uuid4())  # Using UUID for guaranteed uniqueness
            
            event_body = {
                'summary': session_data.get('topic', 'Livestream Session')[:200],
                'description': session_data.get('agenda', '')[:2000],
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
                        'requestId': request_id,
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
                logger.debug(f"Added {len(attendee_emails)} attendees")

            # Create the event
            logger.info(f"Creating Google Calendar event: {event_body['summary']} at {start_time}")

            logger.info("=" * 50)
            logger.info("DEBUG: Conference Data Structure")
            logger.info(f"Request ID: {request_id}")
            logger.info(f"ConferenceSolutionKey type: {event_body['conferenceData']['createRequest']['conferenceSolutionKey']['type']}")
            logger.info("=" * 50)

            event = service.events().insert(
                calendarId=self.calendar_id,
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates='all' if attendee_emails else 'none',
            ).execute()

            # Extract Meet URI
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
                'success': True
            }

            logger.info(
                f"✅ Google Meet meeting created: {result['conference_id']} "
                f"for event {result['event_id']}"
            )
            return result

        except GoogleMeetServiceError:
            # Re-raise custom errors
            raise
        except Exception as e:
            logger.error(f"❌ Failed to create Google Meet meeting: {e}")
            logger.error(traceback.format_exc())
            raise GoogleMeetServiceError(
                f"Failed to create Google Meet meeting: {str(e)}"
            ) from e

    def update_meeting(self, event_id: str, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing Google Calendar event.

        Args:
            event_id: str - Google Calendar event ID
            session_data: dict with updated fields (topic, agenda, start_time, duration, timezone)

        Returns:
            dict: Updated event data with success flag

        Raises:
            GoogleMeetServiceError: If update fails
        """
        if not event_id:
            raise GoogleMeetServiceError("event_id is required for update")

        try:
            service = self._build_calendar_service()

            # Fetch existing event first
            try:
                existing = service.events().get(
                    calendarId=self.calendar_id,
                    eventId=event_id,
                ).execute()
            except Exception as e:
                logger.error(f"Failed to fetch event {event_id} for update: {e}")
                raise GoogleMeetServiceError(f"Event not found: {event_id}") from e

            # Apply updates
            if 'topic' in session_data:
                existing['summary'] = session_data['topic'][:200]
            if 'agenda' in session_data:
                existing['description'] = session_data['agenda'][:2000]
            if 'start_time' in session_data:
                tz = session_data.get('timezone', existing['start'].get('timeZone', 'UTC'))
                duration = session_data.get('duration', 60)
                start_time = session_data['start_time']
                end_time = start_time + timedelta(minutes=duration)
                
                # Ensure timezone awareness
                if timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)
                if timezone.is_naive(end_time):
                    end_time = timezone.make_aware(end_time)
                
                existing['start'] = {'dateTime': start_time.isoformat(), 'timeZone': tz}
                existing['end'] = {'dateTime': end_time.isoformat(), 'timeZone': tz}

            # Update attendees if provided
            if 'attendee_emails' in session_data:
                attendee_emails = session_data['attendee_emails']
                existing['attendees'] = [
                    {'email': email} for email in attendee_emails
                ]

            # Update the event
            updated = service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=existing,
                conferenceDataVersion=1,
                sendUpdates='all' if existing.get('attendees') else 'none',
            ).execute()

            result = {
                'event_id': updated.get('id', ''),
                'html_link': updated.get('htmlLink', ''),
                'success': True
            }

            logger.info(f"✅ Google Meet event updated: {event_id}")
            return result

        except GoogleMeetServiceError:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to update Google Meet event {event_id}: {e}")
            logger.error(traceback.format_exc())
            raise GoogleMeetServiceError(
                f"Failed to update Google Meet event: {str(e)}"
            ) from e

    def delete_meeting(self, event_id: str) -> bool:
        """
        Delete a Google Calendar event (and its associated Meet link).

        Args:
            event_id: str - Google Calendar event ID

        Returns:
            bool: True if deleted successfully

        Raises:
            GoogleMeetServiceError: If deletion fails
        """
        if not event_id:
            raise GoogleMeetServiceError("event_id is required for delete")

        try:
            service = self._build_calendar_service()

            service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
                sendUpdates='all',
            ).execute()

            logger.info(f"✅ Google Meet event deleted: {event_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete Google Meet event {event_id}: {e}")
            logger.error(traceback.format_exc())
            raise GoogleMeetServiceError(
                f"Failed to delete Google Meet event: {str(e)}"
            ) from e

    def get_meeting(self, event_id: str) -> Dict[str, Any]:
        """
        Get details of a Google Calendar event.

        Args:
            event_id: str - Google Calendar event ID

        Returns:
            dict: Event details including conference data

        Raises:
            GoogleMeetServiceError: If fetch fails
        """
        if not event_id:
            raise GoogleMeetServiceError("event_id is required for get")

        try:
            service = self._build_calendar_service()

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

            result = {
                'event_id': event.get('id', ''),
                'conference_id': conference_data.get('conferenceId', ''),
                'meet_uri': meet_uri,
                'status': event.get('status', ''),
                'html_link': event.get('htmlLink', ''),
                'start': event.get('start', {}),
                'end': event.get('end', {}),
                'attendees': event.get('attendees', []),
                'summary': event.get('summary', ''),
                'description': event.get('description', ''),
                'success': True
            }

            logger.debug(f"Retrieved Google Meet event: {event_id}")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to get Google Meet event {event_id}: {e}")
            logger.error(traceback.format_exc())
            raise GoogleMeetServiceError(
                f"Failed to get Google Meet event: {str(e)}"
            ) from e


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
            dict: Processing result with status
        """
        try:
            channel_id = request.headers.get('X-Goog-Channel-ID', '')
            resource_id = request.headers.get('X-Goog-Resource-ID', '')
            resource_state = request.headers.get('X-Goog-Resource-State', '')
            resource_uri = request.headers.get('X-Goog-Resource-URI', '')

            logger.info(
                f"📩 Google Calendar webhook received: "
                f"channel={channel_id}, resource={resource_id}, "
                f"state={resource_state}, uri={resource_uri}"
            )

            if not channel_id or not resource_id:
                logger.warning("Missing required webhook headers")
                return {'status': 'error', 'message': 'Missing required headers'}

            if resource_state == 'sync':
                # Initial sync notification — just acknowledge
                logger.info(f"Sync notification for channel {channel_id}")
                return {'status': 'sync_acknowledged', 'channel_id': channel_id}

            if resource_state == 'exists':
                return self._handle_event_updated(channel_id, resource_id, resource_uri)

            if resource_state == 'not_exists':
                return self._handle_event_deleted(channel_id, resource_id)

            logger.info(f"Unhandled resource state: {resource_state}")
            return {'status': 'unhandled', 'state': resource_state}

        except Exception as e:
            logger.error(f"Error handling Google Calendar webhook: {e}")
            logger.error(traceback.format_exc())
            return {'status': 'error', 'message': str(e)}

    def _handle_event_updated(self, channel_id: str, resource_id: str, resource_uri: str) -> Dict[str, Any]:
        """
        Handle event update notification.
        Re-fetches the event to determine what changed and updates session accordingly.

        Args:
            channel_id: str - The watch channel ID (maps to our session)
            resource_id: str - The resource ID
            resource_uri: str - The resource URI

        Returns:
            dict: Processing result
        """
        try:
            from apps.livestream.models import LivestreamSession

            # Try to find session by channel ID
            session = LivestreamSession.objects.filter(
                calendar_channel_id=channel_id,
                platform='google_meet',
            ).first()

            if not session:
                # Try to find by resource ID stored in calendar_event_id
                session = LivestreamSession.objects.filter(
                    google_meet_event_id=resource_id,
                    platform='google_meet',
                ).first()

            if not session:
                logger.warning(f"No session found for channel {channel_id} or resource {resource_id}")
                return {'status': 'session_not_found', 'channel_id': channel_id}

            # Re-fetch event details
            try:
                event_data = self.meet_service.get_meeting(session.google_meet_event_id)
            except Exception as e:
                logger.error(f"Failed to fetch event details for {session.id}: {e}")
                return {'status': 'fetch_failed', 'session_id': str(session.id), 'error': str(e)}

            # Update session based on event status
            event_status = event_data.get('status', '')
            updates = {}

            if event_status == 'cancelled':
                session.status = 'cancelled'
                updates['status'] = 'cancelled'
            elif event_status == 'confirmed':
                if session.status == 'scheduled':
                    # Event is confirmed - could update times if needed
                    start = event_data.get('start', {}).get('dateTime')
                    end = event_data.get('end', {}).get('dateTime')
                    if start and end:
                        # Parse ISO format times
                        try:
                            from dateutil import parser
                            new_start = parser.parse(start)
                            new_end = parser.parse(end)
                            
                            if abs((new_start - session.start_time).total_seconds()) > 60:
                                session.start_time = new_start
                                updates['start_time'] = new_start
                            if abs((new_end - session.end_time).total_seconds()) > 60:
                                session.end_time = new_end
                                updates['end_time'] = new_end
                        except Exception as e:
                            logger.warning(f"Failed to parse event times: {e}")

            if updates:
                session.save(update_fields=list(updates.keys()) + ['updated_at'])
                logger.info(f"Updated session {session.id} from webhook: {updates}")

            return {
                'status': 'processed',
                'session_id': str(session.id),
                'event_status': event_status,
                'updates': updates
            }

        except Exception as e:
            logger.error(f"Error processing event update: {e}")
            logger.error(traceback.format_exc())
            return {'status': 'error', 'message': str(e), 'channel_id': channel_id}

    def _handle_event_deleted(self, channel_id: str, resource_id: str) -> Dict[str, Any]:
        """
        Handle event deletion notification.

        Args:
            channel_id: str - The watch channel ID
            resource_id: str - The resource ID

        Returns:
            dict: Processing result
        """
        try:
            from apps.livestream.models import LivestreamSession

            # Find session by channel ID or resource ID
            session = LivestreamSession.objects.filter(
                models.Q(calendar_channel_id=channel_id) |
                models.Q(google_meet_event_id=resource_id),
                platform='google_meet',
            ).first()

            if session:
                session.status = 'cancelled'
                session.save(update_fields=['status', 'updated_at'])
                logger.info(f"Session {session.id} marked as cancelled due to deletion")
                return {
                    'status': 'deleted',
                    'session_id': str(session.id)
                }

            logger.info(f"Deletion notification for unknown resource {resource_id}")
            return {'status': 'deletion_noted', 'channel_id': channel_id, 'resource_id': resource_id}

        except Exception as e:
            logger.error(f"Error handling deletion: {e}")
            return {'status': 'error', 'message': str(e)}