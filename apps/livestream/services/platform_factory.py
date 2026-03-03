from .google_meet_service import GoogleMeetService
from .teams_service import TeamsService
from .zoom_service import ZoomService

class LivestreamPlatformFactory:
    """Factory to create appropriate livestream platform service."""
    
    @staticmethod
    def get_platform(platform_name):
        platforms = {
            'zoom': ZoomService,
            'google_meet': GoogleMeetService, 
            'teams': TeamsService,
        }
        
        platform_class = platforms.get(platform_name.lower())
        if not platform_class:
            raise ValueError(f"Unsupported platform: {platform_name}")
        
        return platform_class()