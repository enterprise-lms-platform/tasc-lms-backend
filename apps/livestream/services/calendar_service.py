"""
Calendar integration service for livestream sessions.
Handles generation of calendar files and links for multiple calendar providers.
"""
from django.utils import timezone
from django.urls import reverse
from icalendar import Calendar, Event, Alarm
from datetime import timedelta
import uuid
from urllib.parse import urlencode


class CalendarService:
    """
    Service for calendar integration.
    Generates calendar files and links for Google, Outlook, Apple Calendar.
    Also handles timezone conversion for learners.
    """

    @staticmethod
    def generate_ics_file(session, user=None, user_timezone='UTC'):
        """
        Generate .ics file content for calendar import.

        Args:
            session: LivestreamSession instance
            user: User instance (for personalized links)
            user_timezone: User's preferred timezone

        Returns:
            str: ICS file content
        """
        cal = Calendar()
        cal.add('prodid', '-//LMS Livestream//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'PUBLISH')
        cal.add('x-wr-calname', f"{session.course.title}: {session.title}")
        cal.add('x-wr-timezone', user_timezone)

        event = Event()

        event.add('summary', f"{session.course.title}: {session.title}")
        event.add('description', CalendarService._build_description(session, user))
        event.add('location', session.join_url or 'Online')

        start_time = session.start_time
        end_time = session.end_time

        if user_timezone != 'UTC':
            import pytz
            try:
                user_tz = pytz.timezone(user_timezone)
                start_time = start_time.astimezone(user_tz)
                end_time = end_time.astimezone(user_tz)
            except Exception:
                pass

        event.add('dtstart', start_time)
        event.add('dtend', end_time)
        event.add('dtstamp', timezone.now())
        event.add('uid', f"livestream-{session.id}@lms.com")

        event.add('organizer', session.instructor.email)

        if user:
            event.add('attendee', user.email, parameters={
                'CN': user.get_full_name() or user.email,
                'ROLE': 'REQ-PARTICIPANT',
                'PARTSTAT': 'NEEDS-ACTION',
                'RSVP': 'TRUE'
            })

        alarm = Alarm()
        alarm.add('action', 'DISPLAY')
        alarm.add('description', f'Reminder: {session.title} starts in 15 minutes')
        alarm.add('trigger', timedelta(minutes=-15))
        event.add_component(alarm)

        alarm2 = Alarm()
        alarm2.add('action', 'DISPLAY')
        alarm2.add('description', f'Reminder: {session.title} starts in 1 hour')
        alarm2.add('trigger', timedelta(hours=-1))
        event.add_component(alarm2)

        event.add('url', session.join_url)

        cal.add_component(event)
        return cal.to_ical().decode('utf-8')

    @staticmethod
    def _build_description(session, user=None):
        """Build rich description for calendar event"""
        description = []
        description.append(session.description or '')
        description.append('')
        description.append('=' * 40)
        description.append('LIVESTREAM SESSION DETAILS')
        description.append('=' * 40)
        description.append(f"Course: {session.course.title}")
        description.append(f"Instructor: {session.instructor.get_full_name() or session.instructor.email}")
        description.append(f"Duration: {session.duration_minutes} minutes")
        description.append('')
        description.append('HOW TO JOIN:')
        description.append('-' * 20)
        description.append(f"Join URL: {session.join_url}")
        if session.password:
            description.append(f"Password: {session.password}")
        description.append('')
        description.append('REQUIREMENTS:')
        description.append('-' * 20)
        description.append('- Stable internet connection')
        description.append('- Zoom app installed (or join via browser)')
        description.append('- Microphone and camera (optional)')
        description.append('')
        description.append('This session will be recorded and available for later viewing.')

        return '\n'.join(description)

    @staticmethod
    def get_google_calendar_url(session, user=None):
        """
        Generate Google Calendar URL for adding event.

        Args:
            session: LivestreamSession instance
            user: User instance (for personalized links)

        Returns:
            str: Google Calendar URL
        """
        base_url = "https://www.google.com/calendar/render"

        start_str = session.start_time.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        end_str = session.end_time.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

        params = {
            'action': 'TEMPLATE',
            'text': f"{session.course.title}: {session.title}",
            'details': CalendarService._build_description(session, user),
            'location': session.join_url,
            'dates': f"{start_str}/{end_str}",
            'ctz': 'UTC',
        }

        if user:
            params['add'] = user.email

        return f"{base_url}?{urlencode(params)}"

    @staticmethod
    def get_outlook_calendar_url(session, user=None):
        """
        Generate Outlook Calendar URL for adding event.

        Args:
            session: LivestreamSession instance
            user: User instance (for personalized links)

        Returns:
            str: Outlook Calendar URL
        """
        base_url = "https://outlook.live.com/calendar/0/deeplink/compose"

        params = {
            'path': '/calendar/action/compose',
            'rru': 'addevent',
            'startdt': session.start_time.isoformat(),
            'enddt': session.end_time.isoformat(),
            'subject': f"{session.course.title}: {session.title}",
            'body': CalendarService._build_description(session, user),
            'location': session.join_url,
        }

        return f"{base_url}?{urlencode(params)}"

    @staticmethod
    def get_apple_calendar_url(session, user=None):
        """
        Generate Apple Calendar URL (uses webcal protocol).

        Args:
            session: LivestreamSession instance
            user: User instance (for personalized links)

        Returns:
            str: webcal URL for Apple Calendar
        """
        from django.conf import settings as django_settings
        base_url = "webcal://" + django_settings.SITE_DOMAIN
        path = reverse('livestream-ics', kwargs={'pk': session.id})
        return f"{base_url}{path}"

    @staticmethod
    def get_yahoo_calendar_url(session, user=None):
        """
        Generate Yahoo Calendar URL.

        Args:
            session: LivestreamSession instance
            user: User instance (for personalized links)

        Returns:
            str: Yahoo Calendar URL
        """
        base_url = "https://calendar.yahoo.com"

        params = {
            'v': 60,
            'view': 'd',
            'type': 20,
            'title': f"{session.course.title}: {session.title}",
            'st': session.start_time.strftime('%Y%m%dT%H%M%S'),
            'et': session.end_time.strftime('%Y%m%dT%H%M%S'),
            'desc': CalendarService._build_description(session, user),
            'in_loc': session.join_url,
        }

        return f"{base_url}/?{urlencode(params)}"

    @staticmethod
    def get_all_calendar_links(session, request, user=None):
        """
        Get all calendar links for a session.

        Args:
            session: LivestreamSession instance
            request: Django request object
            user: User instance (optional)

        Returns:
            dict: All calendar links
        """
        return {
            'google': CalendarService.get_google_calendar_url(session, user),
            'outlook': CalendarService.get_outlook_calendar_url(session, user),
            'yahoo': CalendarService.get_yahoo_calendar_url(session, user),
            'apple': CalendarService.get_apple_calendar_url(session, user),
            'ics': request.build_absolute_uri(
                reverse('livestream-ics', kwargs={'pk': session.id})
            ),
            'download': request.build_absolute_uri(
                reverse('livestream-ics-download', kwargs={'pk': session.id})
            ),
        }

    @staticmethod
    def get_timezone_converter():
        """
        Get timezone conversion helper.
        Returns list of common timezones for user selection.
        """
        import pytz
        return {
            'common': [
                'UTC', 'America/New_York', 'America/Chicago', 'America/Denver',
                'America/Los_Angeles', 'Europe/London', 'Europe/Paris',
                'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Dubai', 'Australia/Sydney',
                'Africa/Nairobi', 'Africa/Lagos', 'Africa/Johannesburg', 'Africa/Cairo'
            ],
            'all': pytz.common_timezones
        }


class TimezoneService:
    """
    Service for timezone conversion and display.
    """

    @staticmethod
    def convert_to_user_timezone(dt, user_timezone):
        """
        Convert datetime to user's timezone.

        Args:
            dt: Datetime object (aware)
            user_timezone: User's timezone string

        Returns:
            datetime: Converted datetime
        """
        import pytz
        try:
            user_tz = pytz.timezone(user_timezone)
            return dt.astimezone(user_tz)
        except Exception:
            return dt

    @staticmethod
    def format_for_user(dt, user_timezone, format='%Y-%m-%d %H:%M %Z'):
        """
        Format datetime for display in user's timezone.

        Args:
            dt: Datetime object
            user_timezone: User's timezone string
            format: strftime format

        Returns:
            str: Formatted datetime string
        """
        converted = TimezoneService.convert_to_user_timezone(dt, user_timezone)
        return converted.strftime(format)

    @staticmethod
    def get_timezone_options():
        """
        Get list of timezone choices for forms.
        """
        import pytz
        return [(tz, tz.replace('_', ' ')) for tz in pytz.common_timezones]
