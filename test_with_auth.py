import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def test_with_oauth():
    """Test Meet creation with OAuth 2.0"""
    creds = None
    
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Download OAuth 2.0 credentials from Google Cloud Console
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    service = build('calendar', 'v3', credentials=creds)
    
    # Try to create Meet event
    from datetime import datetime, timedelta
    import uuid
    
    event = {
        'summary': 'OAuth Test Meeting',
        'start': {
            'dateTime': (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z',
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': (datetime.utcnow() + timedelta(hours=2)).isoformat() + 'Z',
            'timeZone': 'UTC',
        },
        'conferenceData': {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {
                    'type': 'hangoutsMeet'
                }
            }
        }
    }
    
    event = service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1
    ).execute()
    
    print(f"✅ Meeting created: {event.get('hangoutLink')}")