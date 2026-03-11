"""
Microsoft Teams integration service for livestream sessions.
Creates Teams online meetings via the Microsoft Graph API using application credentials.
"""
import logging
from datetime import timedelta
from django.conf import settings

logger = logging.getLogger(__name__)


class TeamsService:
    """
    Service class for Microsoft Teams integration via Microsoft Graph API.

    Requires:
      - An Azure AD app registration with application permissions
      - API permissions: OnlineMeetings.ReadWrite.All (application)
      - TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET in settings
      - TEAMS_ORGANIZER_USER_ID: the object-ID of the user who will own meetings

    Methods mirror ZoomService / GoogleMeetService for consistency.
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        self.tenant_id = getattr(settings, 'TEAMS_TENANT_ID', '')
        self.client_id = getattr(settings, 'TEAMS_CLIENT_ID', '')
        self.client_secret = getattr(settings, 'TEAMS_CLIENT_SECRET', '')
        self.organizer_user_id = getattr(settings, 'TEAMS_ORGANIZER_USER_ID', '')
        self._access_token = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_access_token(self):
        """
        Obtain an OAuth 2.0 client-credentials token from Azure AD.

        Returns:
            str: Bearer access token
        """
        if self._access_token:
            return self._access_token

        import requests

        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }

        response = requests.post(token_url, data=payload, timeout=30)
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def _headers(self):
        """Return authorised request headers."""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Meeting lifecycle
    # ------------------------------------------------------------------

    def create_meeting(self, session_data):
        """
        Create a Microsoft Teams online meeting.

        Args:
            session_data: dict with keys:
                - topic: str
                - agenda: str (optional)
                - start_time: datetime
                - duration: int (minutes)
                - timezone: str (optional, currently informational only)
                - attendee_emails: list[str] (optional)

        Returns:
            dict: {
                'meeting_id': str,
                'join_url': str,
                'thread_id': str,
            }

        Raises:
            Exception: If Microsoft Graph API call fails
        """
        import requests

        start_time = session_data["start_time"]
        duration = session_data.get("duration", 60)
        end_time = start_time + timedelta(minutes=duration)

        body = {
            "subject": session_data.get("topic", "Livestream Session"),
            "startDateTime": start_time.isoformat(),
            "endDateTime": end_time.isoformat(),
            "lobbyBypassSettings": {
                "scope": "organization",
                "isDialInBypassEnabled": True,
            },
        }

        # Optional participants
        attendee_emails = session_data.get("attendee_emails", [])
        if attendee_emails:
            body["participants"] = {
                "attendees": [
                    {
                        "upn": email,
                        "role": "attendee",
                    }
                    for email in attendee_emails
                ]
            }

        url = (
            f"{self.GRAPH_BASE_URL}/users/{self.organizer_user_id}/onlineMeetings"
        )

        try:
            resp = requests.post(
                url, json=body, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            result = {
                "meeting_id": data.get("id", ""),
                "join_url": data.get("joinWebUrl", ""),
                "thread_id": data.get("chatInfo", {}).get("threadId", ""),
            }

            logger.info(
                f"Teams meeting created: {result['meeting_id']} "
                f"join_url={result['join_url']}"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to create Teams meeting: {e}")
            raise

    def update_meeting(self, meeting_id, session_data):
        """
        Update an existing Teams online meeting.

        Args:
            meeting_id: str – Graph onlineMeeting ID
            session_data: dict with updated fields

        Returns:
            dict: Updated meeting data

        Raises:
            Exception: If Microsoft Graph API call fails
        """
        import requests

        body = {}
        if "topic" in session_data:
            body["subject"] = session_data["topic"]
        if "start_time" in session_data:
            body["startDateTime"] = session_data["start_time"].isoformat()
            duration = session_data.get("duration", 60)
            body["endDateTime"] = (
                session_data["start_time"] + timedelta(minutes=duration)
            ).isoformat()

        url = (
            f"{self.GRAPH_BASE_URL}/users/{self.organizer_user_id}"
            f"/onlineMeetings/{meeting_id}"
        )

        try:
            resp = requests.patch(
                url, json=body, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            logger.info(f"Teams meeting updated: {meeting_id}")
            return {
                "meeting_id": data.get("id", ""),
                "join_url": data.get("joinWebUrl", ""),
            }

        except Exception as e:
            logger.error(f"Failed to update Teams meeting {meeting_id}: {e}")
            raise

    def delete_meeting(self, meeting_id):
        """
        Delete (cancel) a Teams online meeting.

        Args:
            meeting_id: str – Graph onlineMeeting ID

        Returns:
            bool: True if deleted successfully

        Raises:
            Exception: If Microsoft Graph API call fails
        """
        import requests

        url = (
            f"{self.GRAPH_BASE_URL}/users/{self.organizer_user_id}"
            f"/onlineMeetings/{meeting_id}"
        )

        try:
            resp = requests.delete(
                url, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            logger.info(f"Teams meeting deleted: {meeting_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete Teams meeting {meeting_id}: {e}")
            raise

    def get_meeting(self, meeting_id):
        """
        Get details of a Teams online meeting.

        Args:
            meeting_id: str – Graph onlineMeeting ID

        Returns:
            dict: Meeting details

        Raises:
            Exception: If Microsoft Graph API call fails
        """
        import requests

        url = (
            f"{self.GRAPH_BASE_URL}/users/{self.organizer_user_id}"
            f"/onlineMeetings/{meeting_id}"
        )

        try:
            resp = requests.get(
                url, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            return {
                "meeting_id": data.get("id", ""),
                "join_url": data.get("joinWebUrl", ""),
                "thread_id": data.get("chatInfo", {}).get("threadId", ""),
                "subject": data.get("subject", ""),
                "start": data.get("startDateTime", ""),
                "end": data.get("endDateTime", ""),
            }

        except Exception as e:
            logger.error(f"Failed to get Teams meeting {meeting_id}: {e}")
            raise


class TeamsWebhookHandler:
    """
    Handle Microsoft Teams / Graph change-notification webhooks.

    Microsoft Graph uses subscriptions that POST change notifications.
    The initial POST is a validation request containing a `validationToken`
    query parameter — we must echo it back immediately.
    """

    def __init__(self):
        self.teams_service = TeamsService()

    def handle_webhook(self, request):
        """
        Process an incoming Graph change notification.

        Validation flow:
            Microsoft first sends a POST with ?validationToken=<token>.
            We must respond with 200 and the token as plain text.

        Notification flow:
            Subsequent POSTs contain a JSON body with `value` list.

        Args:
            request: Django request object

        Returns:
            dict | str: Processing result or validation token
        """
        # Validation handshake
        validation_token = request.GET.get("validationToken")
        if validation_token:
            logger.info("Teams webhook validation handshake received")
            return {"validation_token": validation_token}

        # Real notification
        import json

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, Exception):
            return {"status": "invalid_payload"}

        notifications = body.get("value", [])
        results = []

        for notification in notifications:
            resource = notification.get("resource", "")
            change_type = notification.get("changeType", "")

            logger.info(
                f"Teams webhook notification: changeType={change_type}, "
                f"resource={resource}"
            )

            result = self._process_notification(change_type, resource)
            results.append(result)

        return {"status": "processed", "count": len(results), "results": results}

    def _process_notification(self, change_type, resource):
        """
        Process a single Graph change notification.

        Args:
            change_type: str – 'created' | 'updated' | 'deleted'
            resource: str – Microsoft Graph resource path

        Returns:
            dict: Processing result
        """
        from apps.livestream.models import LivestreamSession

        # Extract meeting ID from the resource path if possible
        # Resource format: /users/{user-id}/onlineMeetings/{meeting-id}
        parts = resource.rstrip("/").split("/")
        meeting_id = parts[-1] if parts else ""

        if not meeting_id:
            return {"status": "no_meeting_id"}

        try:
            session = LivestreamSession.objects.filter(
                teams_meeting_id=meeting_id,
                platform="ms_teams",
            ).first()

            if not session:
                logger.warning(f"No session found for Teams meeting {meeting_id}")
                return {"status": "session_not_found", "meeting_id": meeting_id}

            if change_type == "deleted":
                session.status = "cancelled"
                session.save(update_fields=["status"])
                logger.info(f"Session {session.id} cancelled via Teams webhook")
                return {"status": "cancelled", "session_id": str(session.id)}

            if change_type == "updated":
                # Re-fetch and sync
                meeting_data = self.teams_service.get_meeting(meeting_id)
                session.teams_join_url = meeting_data.get("join_url", session.teams_join_url)
                session.join_url = session.teams_join_url
                session.save(update_fields=["teams_join_url", "join_url"])
                return {"status": "updated", "session_id": str(session.id)}

            return {"status": "unhandled", "change_type": change_type}

        except Exception as e:
            logger.error(f"Error processing Teams webhook: {e}")
            return {"status": "error", "message": str(e)}
