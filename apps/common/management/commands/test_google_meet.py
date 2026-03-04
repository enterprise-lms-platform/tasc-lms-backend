from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from ....livestream.services.google_meet_service import GoogleMeetService


class Command(BaseCommand):
    help = 'Test Google Meet integration'
    
    def handle(self, *args, **options):
        self.stdout.write("Testing Google Meet integration...")
        
        service = GoogleMeetService()
        
        # Create a test meeting starting in 1 hour
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)
        
        result = service.create_meeting({
            'topic': 'Test Livestream Session',
            'description': 'This is a test meeting from LMS',
            'start_time': start_time,
            'end_time': end_time,
            'timezone': 'UTC',
            'attendees': ['test@example.com']  # Optional
        })
        
        if result['success']:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Meeting created successfully!\n"
                f"   Join URL: {result['join_url']}\n"
                f"   Meeting ID: {result['meeting_id']}"
            ))
            
            # Test retrieval
            get_result = service.get_meeting(result['meeting_id'])
            if get_result['success']:
                self.stdout.write(self.style.SUCCESS("✅ Meeting retrieval successful"))
            
            # Clean up - delete test meeting
            # delete_result = service.delete_meeting(result['meeting_id'])
            # if delete_result['success']:
            #     self.stdout.write(self.style.SUCCESS("✅ Test meeting deleted"))
            
        else:
            self.stdout.write(self.style.ERROR(
                f"❌ Failed to create meeting: {result.get('error')}"
            ))